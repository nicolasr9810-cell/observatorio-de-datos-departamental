# -*- coding: utf-8 -*-
"""Datos de PRUEBA para tests unitarios. Nunca se usan en la app."""
from __future__ import annotations

import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import box

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from observatorio.config import DIVIPOLA  # noqa: E402

CODES = sorted(DIVIPOLA)
YEARS = list(range(2005, 2024))
IND = ["PIB por habitante", "Pobreza monetaria", "Coeficiente de Gini", "Cobertura neta educación"]


@pytest.fixture(scope="session")
def grid() -> gpd.GeoDataFrame:
    cells = [box(i % 6, i // 6, i % 6 + 1, i // 6 + 1) for i in range(len(CODES))]
    g = gpd.GeoDataFrame({"codigo_divipola": CODES, "departamento": [DIVIPOLA[c] for c in CODES]},
                         geometry=cells, crs="EPSG:4326")
    g["geometry"] = g.translate(-77, 1)   # sobre Colombia, para la proyección 9377
    return g


@pytest.fixture(scope="session")
def master(grid) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    x = grid.geometry.centroid.x.to_numpy()
    rows = []
    for j, c in enumerate(CODES):
        trend = np.cumsum(rng.normal(.5, 1, len(YEARS)))
        for t, y in enumerate(YEARS):
            pib = 20 + x[j] + trend[t] + rng.normal(0, .3)
            pov = 60 - 0.8 * pib + rng.normal(0, 1)
            vals = [pib, pov, 0.4 + pov / 300 + rng.normal(0, .01), 70 + 0.3 * pib + rng.normal(0, 1)]
            for ind, v in zip(IND, vals):
                rows.append({"departamento": DIVIPOLA[c], "codigo_divipola": c, "anio": y, "indicador": ind,
                             "categoria": "Prueba", "valor": v, "unidad": "u", "fuente": "test", "fuente_url": ""})
    return pd.DataFrame(rows)
