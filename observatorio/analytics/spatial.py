# -*- coding: utf-8 -*-
"""Econometría espacial con PySAL: pesos, Moran global, LISA y modelos SAR/SEM.

Decisión de especificación (Anselin, 2005): OLS -> pruebas LM. Si solo LM-lag (o
LM-lag robusto) es significativo -> SAR (ML_Lag); si solo LM-error -> SEM (ML_Error).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import geopandas as gpd
import numpy as np
import pandas as pd
import spreg
from esda.moran import Moran, Moran_Local
from libpysal.weights import KNN, Queen
from libpysal.weights.util import attach_islands

from observatorio.core.http import InsufficientDataError
from observatorio.data.geo import polygonal_geometry

PROJECTED = "EPSG:9377"   # MAGNA-SIRGAS Origen Nacional (distancias en metros)
MIN_SPATIAL_N = 20
QUAD = {1: "Alto-Alto", 2: "Bajo-Alto", 3: "Bajo-Bajo", 4: "Alto-Bajo"}


def align(gdf: gpd.GeoDataFrame, cs: pd.DataFrame) -> gpd.GeoDataFrame:
    """Une el corte transversal (índice KEYS) con las geometrías, en el mismo orden."""
    data = cs.reset_index().drop(columns=["departamento", "anio"], errors="ignore")
    out = gdf.merge(data, on="codigo_divipola", how="inner").reset_index(drop=True)
    if len(out) < MIN_SPATIAL_N:
        raise InsufficientDataError(
            f"Solo {len(out)} departamentos con dato y geometría (mínimo {MIN_SPATIAL_N})."
        )
    return out


def build_weights(gdf: gpd.GeoDataFrame, kind: str = "Reina (contigüidad)", k: int = 4):
    """Pesos estandarizados por fila. Islas (San Andrés) se conectan a su vecino más cercano."""
    proj = gdf.to_crs(PROJECTED).copy()
    polygonal = proj.geometry.map(polygonal_geometry)
    invalid = [i for i, geom in enumerate(polygonal) if geom is None or geom.is_empty]
    if invalid:
        details = []
        for i in invalid:
            name = proj["departamento"].iloc[i] if "departamento" in proj else f"fila {i + 1}"
            original = proj.geometry.iloc[i]
            kind_name = getattr(original, "geom_type", "geometría nula")
            details.append(f"{name} ({kind_name})")
        raise ValueError(
            "La contigüidad requiere un Polygon o MultiPolygon válido; "
            f"no hay un área poligonal utilizable para: {', '.join(details)}."
        )
    proj = proj.set_geometry(polygonal)
    if kind.startswith("Reina"):
        w = Queen.from_dataframe(proj, use_index=False, silence_warnings=True)
        if w.islands:
            w = attach_islands(w, KNN.from_dataframe(proj, k=1, use_index=False))
    else:
        w = KNN.from_dataframe(proj, k=k, use_index=False)
    w.transform = "r"
    return w


def global_moran(y: np.ndarray, w, permutations: int = 999) -> dict:
    m = Moran(y, w, permutations=permutations)
    return {"I de Moran": m.I, "E[I]": m.EI, "z": m.z_sim, "p (permutación)": m.p_sim,
            "Lectura": ("Autocorrelación positiva: valores similares se agrupan" if m.I > m.EI and m.p_sim < .05
                        else "Autocorrelación negativa: vecinos disímiles" if m.p_sim < .05
                        else "Sin evidencia de dependencia espacial (5%)")}


def local_moran(y: np.ndarray, w, alpha: float = .05, permutations: int = 999) -> pd.DataFrame:
    lm = Moran_Local(y, w, permutations=permutations, seed=42)
    lab = [QUAD[q] if p < alpha else "No significativo" for q, p in zip(lm.q, lm.p_sim)]
    z = (y - y.mean()) / y.std()
    return pd.DataFrame({"Ii": lm.Is, "p": lm.p_sim, "Cuadrante": lab, "z": z, "Wz": w.sparse @ z})


@dataclass
class SpatialFit:
    ols: object
    diagnostics: pd.DataFrame
    recommended: str
    model: object | None = None
    coefs: pd.DataFrame | None = None
    impacts: pd.DataFrame | None = None
    rho: float | None = None
    notes: list[str] = field(default_factory=list)


@dataclass
class SARFit:
    """Ajuste SAR utilizable para calcular escenarios con derrames espaciales."""
    model: object
    rho: float
    coefs: pd.DataFrame
    impacts: pd.DataFrame


def _coef_table(m, names) -> pd.DataFrame:
    z = np.array(getattr(m, "z_stat", None) or m.t_stat)   # OLS reporta t; ML reporta z
    k = len(names)
    return pd.DataFrame({"Coeficiente": np.ravel(m.betas)[:k], "Error est.": np.ravel(m.std_err)[:k],
                         "z": z[:k, 0], "p": z[:k, 1]}, index=names)


def sar_impacts(beta: pd.Series, rho: float, w) -> pd.DataFrame:
    """Efectos directos, indirectos (spillovers) y totales de LeSage & Pace (2009)."""
    n = w.n
    S = np.linalg.inv(np.eye(n) - rho * w.full()[0])
    rows = []
    for name, b in beta.items():
        Sk = S * b
        direct = np.trace(Sk) / n
        total = Sk.sum() / n
        rows.append({"Variable": name, "Directo": direct, "Indirecto (derrame)": total - direct, "Total": total})
    return pd.DataFrame(rows).set_index("Variable")


def fit_sar(df: gpd.GeoDataFrame, target: str, features: list[str], w) -> SARFit:
    """Ajusta un SAR explícito para simulación, aunque no sea el modelo recomendado por LM."""
    y = df[[target]].to_numpy(float)
    X = df[features].to_numpy(float)
    names = ["CONSTANTE"] + features
    model = spreg.ML_Lag(y, X, w=w, name_y=target, name_x=features)
    rho = float(model.rho)
    coefs = _coef_table(model, names)
    coefs.loc["ρ (rezago espacial)"] = [
        rho, np.ravel(model.std_err)[-1], *np.array(model.z_stat)[-1]
    ]
    beta = pd.Series(np.ravel(model.betas)[1:len(names)], index=features)
    return SARFit(model, rho, coefs, sar_impacts(beta, rho, w))


def fit_spatial(df: gpd.GeoDataFrame, target: str, features: list[str], w, alpha: float = .05) -> SpatialFit:
    y = df[[target]].to_numpy(float)
    X = df[features].to_numpy(float)
    names = ["CONSTANTE"] + features
    ols = spreg.OLS(y, X, w=w, spat_diag=True, moran=True, name_y=target, name_x=features)
    diag = pd.DataFrame({
        "Prueba": ["LM-lag", "LM-lag robusto", "LM-error", "LM-error robusto", "Moran residuos (z)"],
        "Estadístico": [ols.lm_lag[0], ols.rlm_lag[0], ols.lm_error[0], ols.rlm_error[0], ols.moran_res[1]],
        "p": [ols.lm_lag[1], ols.rlm_lag[1], ols.lm_error[1], ols.rlm_error[1], ols.moran_res[2]],
    })
    lag_sig, err_sig = ols.lm_lag[1] < alpha, ols.lm_error[1] < alpha
    if lag_sig and err_sig:
        rec = "SAR" if ols.rlm_lag[1] < ols.rlm_error[1] else "SEM"
    elif lag_sig:
        rec = "SAR"
    elif err_sig:
        rec = "SEM"
    else:
        rec = "OLS"
    fit = SpatialFit(ols, diag, rec, coefs=_coef_table(ols, names))
    if rec == "SAR":
        sar = fit_sar(df, target, features, w)
        fit.model, fit.rho, fit.coefs, fit.impacts = sar.model, sar.rho, sar.coefs, sar.impacts
        fit.notes.append(f"SAR: ρ={sar.rho:.3f}. Los coeficientes no son efectos marginales; "
                         "usa la tabla de impactos directos/indirectos.")
    elif rec == "SEM":
        m = spreg.ML_Error(y, X, w=w, name_y=target, name_x=features)
        fit.model, fit.coefs = m, _coef_table(m, names)
        fit.coefs.loc["λ (error espacial)"] = [m.lam, np.ravel(m.std_err)[-1], *np.array(m.z_stat)[-1]]
        fit.notes.append(f"SEM: λ={m.lam:.3f}. La dependencia está en choques no observados; "
                         "los β se interpretan como en OLS.")
    else:
        fit.notes.append("Las pruebas LM no rechazan independencia espacial: OLS es adecuado.")
    if len(df) < 40:
        fit.notes.append(f"n={len(df)} departamentos: potencia limitada de las pruebas LM.")
    return fit
