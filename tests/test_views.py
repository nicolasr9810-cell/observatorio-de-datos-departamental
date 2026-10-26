# -*- coding: utf-8 -*-
"""Humo de UI: cada vista corre de principio a fin con datos de prueba inyectados."""
import os
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from observatorio.ui import state

ROOT = Path(__file__).resolve().parents[1]
VIEWS = ["panorama", "eda", "ml", "pca", "timeseries", "spatial", "simulation", "quality"]


@pytest.fixture(autouse=True)
def inject(master, grid, monkeypatch):
    os.chdir(ROOT)
    q = pd.DataFrame([{"Indicador": "test", "Filas válidas": len(master)}])
    monkeypatch.setattr(state, "_master", lambda: (master, q))
    monkeypatch.setattr(state, "_geo", lambda: grid)


@pytest.mark.parametrize("view", VIEWS)
def test_view_runs(view):
    at = AppTest.from_file(str(ROOT / "views" / f"{view}.py"), default_timeout=300).run()
    assert not at.exception, [e.message for e in at.exception]
    assert not at.error, [e.value for e in at.error]


def test_simulation_chain():
    """Espacial → simulación y VAR → simulación comparten estado de sesión."""
    at = AppTest.from_file(str(ROOT / "views" / "timeseries.py"), default_timeout=300).run()
    assert "ts_last" in at.session_state
    ts = at.session_state["ts_last"]
    at2 = AppTest.from_file(str(ROOT / "views" / "simulation.py"), default_timeout=300)
    at2.session_state["ts_last"] = ts
    at2.run()
    at2.radio[0].set_value("VAR/VECM: choque dinámico").run()
    assert not at2.exception, [e.message for e in at2.exception]


def test_spatial_simulation_sar(grid):
    import numpy as np
    from observatorio.analytics import spatial
    rng = np.random.default_rng(1)
    gdf = grid.copy()
    w = spatial.build_weights(gdf)
    x1 = rng.normal(size=w.n)
    gdf["y"] = np.linalg.solve(np.eye(w.n) - 0.7 * w.full()[0], 1 + 2 * x1 + rng.normal(0, .3, w.n))
    gdf["x1"], gdf["x2"] = x1, rng.normal(size=w.n)
    fit = spatial.fit_spatial(gdf, "y", ["x1", "x2"], w)
    assert fit.rho is not None
    at = AppTest.from_file(str(ROOT / "views" / "simulation.py"), default_timeout=300)
    at.session_state["sp_last"] = {"fit": fit, "gdf": gdf, "w": w, "feats": ["x1", "x2"], "target": "y", "year": 2020}
    at.run()
    assert not at.exception, [e.message for e in at.exception]
    assert not at.info  # no pidió estimar primero: simuló
