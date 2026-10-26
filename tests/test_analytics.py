# -*- coding: utf-8 -*-
import numpy as np
import pandas as pd
import pytest

from observatorio.analytics import dimred, eda, explain, ml, policy, spatial, timeseries
from observatorio.core import panel
from observatorio.core.http import InsufficientDataError
from observatorio.core.normalize import norm_code, norm_dept, to_number
from observatorio.data.geo import to_geojson
from observatorio.viz import maps

from conftest import IND


def test_normalize():
    assert norm_dept("NARIÑO") == ("Nariño", "52")
    assert norm_code("52.0") == "52"
    assert to_number(__import__("pandas").Series(["1.234,5"])).iloc[0] == 1234.5


def test_panel_no_imputation(master):
    m = master.drop(master.index[:10])
    mat = panel.panel(m, IND)
    assert mat.data.notna().all().all() and mat.dropped > 0


def test_cross_section_coverage_reports_complete_cases(master):
    sparse = master[~((master.codigo_divipola == "52") & (master.anio == 2020) &
                      (master.indicador == IND[0]))]
    coverage = panel.cross_section_coverage(sparse, IND)
    count = coverage.loc[coverage["Año"] == 2020, "Departamentos completos"].iloc[0]
    assert count == master.codigo_divipola.nunique() - 1


def test_eda(master):
    w = panel.panel(master, IND).data
    prof = eda.profile(w)
    r, _ = eda.correlations(w)
    assert len(prof) == 4 and r.shape == (4, 4)
    assert eda.vif(w)["VIF"].notna().all()
    assert eda.auto_insights(prof, r)


@pytest.mark.parametrize("kind", ml.MODELS)
def test_ml_and_shap(master, kind):
    w = panel.panel(master, IND).data
    X, y, g = ml.supervised_frame(w, IND[1], [IND[0], IND[3]], lag=1)
    res = ml.fit_evaluate(X, y, g, kind)
    assert res.oof_pred.notna().all()
    sh = explain.shap_explain(res.pipeline, X, max_background=20, max_explain=30)
    row = sh.values.index[0]
    pred = res.pipeline.predict(sh.data.loc[[row]])[0]
    assert np.isclose(sh.base_value + sh.values.loc[row].sum(), pred, atol=1e-6)  # aditividad SHAP
    assert explain.narrative(sh, row)
    cf = policy.ml_counterfactual(res.pipeline, X.iloc[[0]], {X.columns[0]: 10})
    assert np.isfinite(cf["Cambio"])


def test_pca(master):
    cs = panel.cross_section(master, IND, 2020).data
    r = dimred.run_pca(cs, orient_by="PIB por habitante")
    assert r.explained["Acumulada"].iloc[-1] == pytest.approx(1)
    assert r.loadings.loc["PIB por habitante", "CP1"] > 0
    lab, sil = dimred.cluster(r.scores.iloc[:, :2])
    assert lab.nunique() >= 2


def test_timeseries(master):
    s = panel.territory_series(master, IND[:3], "52").data
    st_tab = timeseries.stationarity(s)
    assert set(st_tab["Orden sugerido"]) <= {"I(0)", "I(1)", "I(2)?"}
    v = timeseries.fit_var(s, diff=True)
    assert len(v.forecast) == 3 and v.granger.shape == (3, 3)
    rank, jt = timeseries.johansen(s)
    vecm = timeseries.fit_vecm(s, 1)
    assert vecm.forecast.notna().all().all()
    for ts in (v, vecm):
        irf = timeseries.irf_table(ts, IND[0])
        assert irf.shape[1] == 3
        assert len(policy.var_policy(ts, IND[0], 1.0)) == 7
    auto, *_ = timeseries.auto_model(s)
    assert auto.model_type


def test_gap_detection(master):
    m = master[~((master.codigo_divipola == "52") & (master.anio == 2010))]
    with pytest.raises(InsufficientDataError):
        panel.territory_series(m, IND[:2], "52")


def test_spatial(master, grid):
    cs = panel.cross_section(master, IND, 2020).data
    gdf = spatial.align(grid, cs)
    w = spatial.build_weights(gdf)
    assert w.n == len(gdf) and not w.islands
    y = gdf[IND[1]].to_numpy()
    assert -1 < spatial.global_moran(y, w, 99)["I de Moran"] < 1
    lisa = spatial.local_moran(y, w, permutations=99)
    assert len(lisa) == len(gdf)
    fit = spatial.fit_spatial(gdf, IND[1], [IND[0], IND[3]], w)
    assert fit.recommended in {"OLS", "SAR", "SEM"}
    imp = spatial.sar_impacts(fit.coefs["Coeficiente"].iloc[1:3], 0.4, w)
    assert np.allclose(imp["Total"], imp["Directo"] + imp["Indirecto (derrame)"])
    assert np.allclose(imp["Total"], fit.coefs["Coeficiente"].iloc[1:3].values / 0.6)  # β/(1-ρ), W por filas
    sim = policy.spatial_policy(gdf, w, 0.4, -0.8, 1.0, ["52"])
    assert (sim["Tipo"] == "Intervenido").sum() == 1 and (sim["Tipo"] == "Derrame").any()
    assert len(spatial.build_weights(gdf, "KNN", 4).neighbors) == len(gdf)


def test_map_geojson_joins_by_department_code(grid):
    geojson = to_geojson(grid)
    feature = geojson["features"][0]
    assert feature["id"] == feature["properties"]["codigo_divipola"] == grid.codigo_divipola.iloc[0]
    values = grid.iloc[:-1][["codigo_divipola"]].assign(valor=np.arange(len(grid) - 1, dtype=float))
    fig = maps.choropleth(grid, values, "valor")
    trace = fig.data[0]
    assert trace.featureidkey == "properties.codigo_divipola"
    assert set(trace.locations) == set(grid.codigo_divipola)
    assert pd.isna(dict(zip(trace.locations, trace.z))[grid.codigo_divipola.iloc[-1]])
    missing_layer = next(trace for trace in fig.data if trace.type == "choroplethmap" and trace.showscale is False)
    assert missing_layer.featureidkey == "properties.codigo_divipola"
    assert list(missing_layer.locations) == [grid.codigo_divipola.iloc[-1]]
    lisa = pd.DataFrame({"Cuadrante": ["No significativo"] * len(grid), "p": [1.0] * len(grid)})
    assert maps.lisa_map(grid, lisa).data[0].featureidkey == "properties.codigo_divipola"


def test_sar_branch(grid):
    rng = np.random.default_rng(1)
    gdf = grid.copy()
    w = spatial.build_weights(gdf)
    x1, x2 = rng.normal(size=w.n), rng.normal(size=w.n)
    y = np.linalg.solve(np.eye(w.n) - 0.7 * w.full()[0], 1 + 2 * x1 - x2 + rng.normal(0, .3, w.n))
    gdf["y"], gdf["x1"], gdf["x2"] = y, x1, x2
    fit = spatial.fit_spatial(gdf, "y", ["x1", "x2"], w)
    assert fit.recommended in {"SAR", "SEM"}
    if fit.recommended == "SAR":
        assert 0.3 < fit.rho < 0.95 and fit.impacts is not None
    scenario = spatial.fit_sar(gdf, "y", ["x1", "x2"], w)
    assert 0.3 < scenario.rho < 0.95 and scenario.impacts is not None
