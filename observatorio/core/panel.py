# -*- coding: utf-8 -*-
"""Puente entre el contrato largo y las matrices que piden los modelos.

Regla del observatorio: no se imputa. Todo modelo trabaja con casos completos y
el número de filas descartadas viaja con el resultado.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from observatorio.core.http import InsufficientDataError

KEYS = ["codigo_divipola", "departamento", "anio"]


@dataclass
class Matrix:
    data: pd.DataFrame                 # índice: KEYS (o anio), columnas: indicadores
    dropped: int = 0
    notes: list[str] = field(default_factory=list)


def to_wide(master: pd.DataFrame, indicators: list[str]) -> pd.DataFrame:
    sub = master[master.indicador.isin(indicators)]
    dup = sub.duplicated(KEYS + ["indicador"], keep=False)
    if dup.any():
        raise ValueError(f"duplicados territorio-año-indicador: {sub.loc[dup, 'indicador'].unique()[:5]}")
    wide = sub.pivot_table(index=KEYS, columns="indicador", values="valor", aggfunc="first")
    return wide.reindex(columns=indicators)


def complete(wide: pd.DataFrame, min_rows: int, what: str) -> Matrix:
    clean = wide.dropna()
    dropped = len(wide) - len(clean)
    if len(clean) < min_rows:
        raise InsufficientDataError(
            f"{what}: {len(clean)} casos completos (< {min_rows}). "
            f"Se descartaron {dropped} filas con faltantes; elige indicadores con más cobertura común."
        )
    return Matrix(clean, dropped)


def panel(master: pd.DataFrame, indicators: list[str], years: tuple[int, int] | None = None,
          min_rows: int = 30) -> Matrix:
    """Panel departamento × año (para ML)."""
    wide = to_wide(master, indicators)
    if years:
        wide = wide[wide.index.get_level_values("anio").to_series().between(*years).values]
    return complete(wide, min_rows, "Panel")


def cross_section(master: pd.DataFrame, indicators: list[str], year: int, min_rows: int = 20) -> Matrix:
    """Corte transversal de un año (PCA, econometría espacial)."""
    wide = to_wide(master, indicators)
    wide = wide[wide.index.get_level_values("anio") == year]
    return complete(wide, min_rows, f"Corte {year}")


def territory_series(master: pd.DataFrame, indicators: list[str], code: str, min_rows: int = 12) -> Matrix:
    """Serie anual de un territorio (VAR/VECM). Exige años consecutivos."""
    wide = to_wide(master, indicators)
    wide = wide[wide.index.get_level_values("codigo_divipola") == code].droplevel([0, 1])
    m = complete(wide.sort_index(), min_rows, "Serie territorial")
    years = m.data.index.to_numpy()
    if (pd.Series(years).diff().dropna() != 1).any():
        raise InsufficientDataError(
            f"La serie tiene huecos ({years.min()}–{years.max()}, {len(years)} años). "
            "VAR/VECM requieren periodicidad regular; acota el rango o cambia indicadores."
        )
    return m


def common_years(master: pd.DataFrame, indicators: list[str]) -> list[int]:
    sets = [set(master.loc[master.indicador == i, "anio"]) for i in indicators]
    return sorted(set.intersection(*sets)) if sets else []
