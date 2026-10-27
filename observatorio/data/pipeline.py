# -*- coding: utf-8 -*-
"""Orquestación de la carga. Sin Streamlit: se usa igual en Colab y en la app."""
from __future__ import annotations

import pandas as pd

from observatorio.core.http import DataSourceError
from observatorio.data import loaders as L


def load_all() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Devuelve (master largo, reporte de calidad). Fail-fast ante cualquier fuente caída."""
    quality: list[dict] = []
    population = L.load_population(quality)
    parts: list[pd.DataFrame] = []
    parts += L.load_gdp(population, quality)
    parts += L.load_homicides(population, quality)
    parts += L.load_finance(population, quality)
    parts += L.load_poverty_gini(quality)
    parts += L.load_education(quality)
    parts += L.load_ctei(quality)
    master = pd.concat(parts, ignore_index=True)
    master["anio"] = pd.to_numeric(master["anio"], errors="coerce")
    master["valor"] = pd.to_numeric(master["valor"], errors="coerce")
    master = master.dropna(subset=["departamento", "codigo_divipola", "anio", "valor"])
    master["anio"] = master["anio"].astype(int)
    if master.empty:
        raise DataSourceError("FALLÓ EL PIPELINE: cero indicadores válidos. Revisa las fuentes y sus campos.")
    master = master.sort_values(["categoria", "indicador", "departamento", "anio"])
    return master.reset_index(drop=True), pd.DataFrame(quality)
