# -*- coding: utf-8 -*-
"""Simulación de políticas económicas sobre los modelos estimados.

Tres motores, cada uno con su supuesto explícito:
1. Espacial (SAR): Δy = (I − ρW)⁻¹ β_k Δx_k  -> efecto en el territorio intervenido y derrames.
2. VAR/VECM: choque en una variable y su propagación dinámica (IRF escalada).
3. Contrafactual ML: cambia X en un territorio y compara predicciones (asociacional, no causal).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from observatorio.analytics.timeseries import TSResult, irf_table


def spatial_policy(df, w, rho: float, beta_k: float, delta: float, targets: list[str]) -> pd.DataFrame:
    """Δx = delta en los departamentos 'targets' (códigos DIVIPOLA); devuelve Δy en todos."""
    n = w.n
    dx = np.where(df["codigo_divipola"].isin(targets), delta, 0.0)
    dy = np.linalg.solve(np.eye(n) - rho * w.full()[0], beta_k * dx)
    out = df[["codigo_divipola", "departamento"]].copy()
    out["Δx"] = dx
    out["Δy simulado"] = dy
    out["Tipo"] = np.where(out["Δx"] != 0, "Intervenido", np.where(np.abs(dy) > 1e-9, "Derrame", "Sin efecto"))
    return out


def var_policy(ts: TSResult, impulse: str, shock: float, periods: int = 6) -> pd.DataFrame:
    """Choque de 'shock' unidades en 'impulse' (IRF no ortogonal: unidad = 1 en la innovación)."""
    path = irf_table(ts, impulse, periods, orth=False) * shock
    path.index = path.index + int(ts.data.index.max()) + 1
    return path.rename_axis("Año")


def ml_counterfactual(pipeline, x_row: pd.DataFrame, changes: dict[str, float], pct: bool = True) -> dict:
    """x_row: una fila de X. changes: {variable: % (o unidades)}."""
    new = x_row.copy()
    for var, d in changes.items():
        new[var] = new[var] * (1 + d / 100) if pct else new[var] + d
    base, sim = float(pipeline.predict(x_row)[0]), float(pipeline.predict(new)[0])
    return {"Predicción base": base, "Predicción simulada": sim, "Cambio": sim - base,
            "Cambio %": 100 * (sim - base) / base if base else np.nan, "X simulado": new}
