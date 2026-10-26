# -*- coding: utf-8 -*-
"""Series de tiempo multivariadas: estacionariedad, VAR, Johansen y VECM.

Flujo econométrico:
1. ADF + KPSS en niveles y diferencias -> orden de integración I(0)/I(1).
2. Si todas son I(1): Johansen. Rango r>0 -> VECM; r=0 -> VAR en diferencias.
3. Si son I(0): VAR en niveles.
Con series anuales (T≈10–20) los grados de libertad son escasos: el módulo acota
los rezagos y advierte; series mensuales (p.ej. homicidios) permiten modelos más ricos.
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from statsmodels.tsa.api import VAR
from statsmodels.tsa.stattools import adfuller, kpss
from statsmodels.tsa.vector_ar.vecm import VECM, coint_johansen

from observatorio.core.http import InsufficientDataError


def max_safe_lags(T: int, k: int) -> int:
    """Mayor p con T - p > k·p + 1 (ecuaciones identificadas con al menos 1 g.l.)."""
    return max(1, (T - 2) // (k + 1))


def _adf_kpss(s: pd.Series) -> tuple[float, float]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        adf_p = adfuller(s, autolag="AIC", maxlag=min(2, len(s) // 4))[1]
        kpss_p = kpss(s, regression="c", nlags="auto")[1]
    return adf_p, kpss_p


def stationarity(df: pd.DataFrame, alpha: float = .05) -> pd.DataFrame:
    rows = []
    for c in df.columns:
        a0, k0 = _adf_kpss(df[c])
        a1, k1 = _adf_kpss(df[c].diff().dropna())
        level_ok = a0 < alpha and k0 >= alpha
        diff_ok = a1 < alpha or k1 >= alpha
        order = "I(0)" if level_ok else "I(1)" if diff_ok else "I(2)?"
        rows.append({"Variable": c, "ADF p (nivel)": a0, "KPSS p (nivel)": k0,
                     "ADF p (Δ)": a1, "KPSS p (Δ)": k1, "Orden sugerido": order})
    return pd.DataFrame(rows)


def johansen(df: pd.DataFrame, k_ar_diff: int = 1, det_order: int = 0) -> tuple[int, pd.DataFrame]:
    res = coint_johansen(df, det_order, k_ar_diff)
    tab = pd.DataFrame({"H0: rango ≤": range(df.shape[1]), "Traza": res.lr1,
                        "Crítico 95%": res.cvt[:, 1], "Máx. autovalor": res.lr2, "Crítico 95% (máx)": res.cvm[:, 1]})
    tab["Rechaza H0"] = tab["Traza"] > tab["Crítico 95%"]
    rank = int(tab["Rechaza H0"].cumprod().sum())
    return rank, tab


@dataclass
class TSResult:
    model_type: str              # "VAR (niveles)" | "VAR (diferencias)" | "VECM"
    results: object
    data: pd.DataFrame
    lags: int
    forecast: pd.DataFrame
    lower: pd.DataFrame
    upper: pd.DataFrame
    granger: pd.DataFrame | None = None
    notes: list[str] = field(default_factory=list)


def _future_index(df: pd.DataFrame, steps: int) -> pd.Index:
    return pd.Index(range(int(df.index.max()) + 1, int(df.index.max()) + 1 + steps), name=df.index.name)


def fit_var(df: pd.DataFrame, maxlags: int = 2, diff: bool = False, steps: int = 3, ic: str = "aic") -> TSResult:
    data = df.diff().dropna() if diff else df
    T, k = data.shape
    pmax = min(maxlags, max_safe_lags(T, k))
    if T - pmax <= k * pmax + 1:
        raise InsufficientDataError(f"T={T} con k={k} variables no identifica ni un VAR(1). Reduce variables.")
    model = VAR(data)
    try:
        p = int(model.select_order(pmax).selected_orders[ic]) or 1
    except Exception:  # noqa: BLE001 - select_order falla con T muy pequeño
        p = 1
    res = model.fit(p)
    point, lo, up = res.forecast_interval(data.values[-p:], steps=steps, alpha=.05)
    idx = _future_index(df, steps)
    mk = lambda a: pd.DataFrame(a, index=idx, columns=df.columns)  # noqa: E731
    fc, lo, up = mk(point), mk(lo), mk(up)
    if diff:  # reintegrar a niveles para el pronóstico
        last = df.iloc[-1]
        fc, lo, up = fc.cumsum() + last, lo.cumsum() + last, up.cumsum() + last
    g = pd.DataFrame(index=df.columns, columns=df.columns, dtype=float)
    for caused in df.columns:
        for causing in df.columns:
            if caused != causing:
                g.loc[caused, causing] = res.test_causality(caused, [causing], kind="f").pvalue
    notes = [f"Rezagos elegidos por {ic.upper()}: {p} (máximo seguro {pmax} con T={T}, k={k})."]
    if not res.is_stable():
        notes.append("⚠️ El VAR no es estable (raíces fuera del círculo unitario): IRF no confiables.")
    if T < 20:
        notes.append(f"⚠️ T={T} observaciones: inferencia de baja potencia. Úsese como exploratorio.")
    return TSResult("VAR (diferencias)" if diff else "VAR (niveles)", res, data, p, fc, lo, up, g, notes)


def fit_vecm(df: pd.DataFrame, rank: int, k_ar_diff: int = 1, steps: int = 3) -> TSResult:
    T, k = df.shape
    if rank < 1 or rank >= k:
        raise ValueError("El rango de cointegración debe estar entre 1 y k-1 para un VECM.")
    res = VECM(df, k_ar_diff=k_ar_diff, coint_rank=rank, deterministic="ci").fit()
    point, lo, up = res.predict(steps=steps, alpha=.05)
    idx = _future_index(df, steps)
    mk = lambda a: pd.DataFrame(a, index=idx, columns=df.columns)  # noqa: E731
    notes = [f"VECM con rango {rank} y {k_ar_diff} rezagos en diferencias; constante dentro de la cointegración."]
    alpha = pd.DataFrame(res.alpha, index=df.columns, columns=[f"EC{i+1}" for i in range(rank)])
    slow = alpha.index[(alpha.abs() < 1e-3).all(axis=1)].tolist()
    if slow:
        notes.append(f"Variables con ajuste casi nulo al equilibrio (débilmente exógenas): {slow}.")
    if T < 20:
        notes.append(f"⚠️ T={T}: Johansen tiene sesgo de tamaño en muestras pequeñas.")
    return TSResult("VECM", res, df, k_ar_diff, mk(point), mk(lo), mk(up), None, notes)


def auto_model(df: pd.DataFrame, maxlags: int = 2, steps: int = 3) -> tuple[TSResult, pd.DataFrame, pd.DataFrame | None]:
    """Selección automática VAR/VECM según integración y cointegración."""
    st_tab = stationarity(df)
    if (st_tab["Orden sugerido"] == "I(0)").all():
        return fit_var(df, maxlags, diff=False, steps=steps), st_tab, None
    rank, jt = johansen(df, k_ar_diff=1)
    if 0 < rank < df.shape[1]:
        return fit_vecm(df, rank, 1, steps), st_tab, jt
    return fit_var(df, maxlags, diff=True, steps=steps), st_tab, jt


def irf_table(ts: TSResult, impulse: str, periods: int = 6, orth: bool = True) -> pd.DataFrame:
    """Respuesta de cada variable a un choque de 1 unidad (o 1 d.e. si orth) en 'impulse'."""
    irf = ts.results.irf(periods)
    j = list(ts.data.columns).index(impulse)
    arr = irf.orth_irfs if orth and hasattr(irf, "orth_irfs") else irf.irfs
    if ts.model_type == "VAR (diferencias)":
        arr = np.cumsum(arr, axis=0)   # efecto acumulado = efecto en niveles
    return pd.DataFrame(arr[:, :, j], columns=ts.data.columns).rename_axis("Horizonte")
