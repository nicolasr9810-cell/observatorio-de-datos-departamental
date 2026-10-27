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
from scipy.optimize import minimize_scalar
from scipy.stats import norm
from esda.moran import Moran, Moran_Local
from libpysal.weights import KNN, Queen
from libpysal.weights.util import attach_islands
from types import SimpleNamespace

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
    notes: list[str] = field(default_factory=list)


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


def _sar_coefs_original_scale(beta_std, rho, covariance, x_mean, x_scale, y_mean, y_scale, names):
    """Convierte parámetros y covarianza del SAR estandarizado a las unidades originales."""
    n_features = len(x_mean)
    p = n_features + 1
    beta_std = np.asarray(beta_std, dtype=float).reshape(-1)
    beta = beta_std[1:p] * y_scale / x_scale
    intercept = (1.0 - rho) * y_mean + y_scale * beta_std[0] - float(x_mean @ beta)
    values = np.r_[intercept, beta, rho]

    transform = np.zeros((p + 1, p + 1), dtype=float)
    transform[0, 0] = y_scale
    transform[0, 1:p] = -x_mean * y_scale / x_scale
    transform[0, p] = -y_mean
    for j in range(n_features):
        transform[j + 1, j + 1] = y_scale / x_scale[j]
    transform[p, p] = 1.0
    cov = transform @ np.asarray(covariance, dtype=float) @ transform.T
    errors = np.sqrt(np.maximum(np.diag(cov), 0.0))
    z = np.divide(values, errors, out=np.full_like(values, np.nan), where=errors > 0)
    p_values = 2.0 * norm.sf(np.abs(z))
    return pd.DataFrame(
        {"Coeficiente": values, "Error est.": errors, "z": z, "p": p_values},
        index=[*names, "ρ (rezago espacial)"],
    ), beta


def _fit_sar_profile(y, x, w, target, features, x_mean, x_scale, y_mean, y_scale):
    """Fallback SAR por máxima verosimilitud perfilada y solución matricial exacta.

    Evita la serie geométrica de PySAL cuando rho queda demasiado cerca del límite
    de convergencia. El análisis se restringe a |rho| < 0.95, donde la serie es estable.
    """
    n = len(y)
    W = np.asarray(w.full()[0], dtype=float)
    y_std = (y - y_mean) / y_scale
    x_std = (x - x_mean) / x_scale
    X = np.column_stack((np.ones(n), x_std))
    Wy = W @ y_std
    identity = np.eye(n)

    def profile(rho):
        A = identity - rho * W
        sign, logdet = np.linalg.slogdet(A)
        if sign <= 0 or not np.isfinite(logdet):
            return np.inf
        transformed_y = y_std - rho * Wy
        beta = np.linalg.lstsq(X, transformed_y, rcond=None)[0]
        residual = transformed_y - X @ beta
        sigma2 = float(residual.T @ residual) / n
        if not np.isfinite(sigma2) or sigma2 <= 0:
            return np.inf
        return 0.5 * n * np.log(sigma2) - logdet

    optimum = minimize_scalar(profile, bounds=(-0.95, 0.95), method="bounded", options={"xatol": 1e-6})
    rho = float(optimum.x)
    if not optimum.success or not np.isfinite(optimum.fun) or abs(rho) >= 0.94:
        raise ValueError(
            "El SAR no identifica un ρ estable dentro de (-0.95, 0.95). "
            "Usa otro escenario o cambia los indicadores seleccionados."
        )

    transformed_y = y_std - rho * Wy
    beta_std = np.linalg.lstsq(X, transformed_y, rcond=None)[0]
    residual = transformed_y - X @ beta_std
    sigma2 = float(residual.T @ residual) / n
    cov_std = sigma2 * np.linalg.inv(X.T @ X)
    conditional_cov = np.zeros((len(beta_std) + 1, len(beta_std) + 1), dtype=float)
    conditional_cov[:-1, :-1] = cov_std
    h = 1e-4
    curvature = (profile(rho + h) - 2 * profile(rho) + profile(rho - h)) / (h * h)
    if curvature > 0 and np.isfinite(curvature):
        conditional_cov[-1, -1] = 1.0 / curvature

    table, beta = _sar_coefs_original_scale(
        beta_std, rho, conditional_cov, x_mean, x_scale, y_mean, y_scale,
        ["CONSTANTE", *features],
    )
    model = SimpleNamespace(rho=rho, betas=np.r_[table["Coeficiente"].iloc[:-1], rho], method="profile exacto")
    impacts = sar_impacts(pd.Series(beta, index=features), rho, w)
    notes = [
        "La expansión de PySAL no convergió; el SAR se estimó con máxima verosimilitud perfilada y solución matricial exacta.",
        "Los errores estándar de β se calculan condicionados a ρ y deben leerse como aproximados.",
    ]
    return SARFit(model, rho, table, impacts, notes)


def fit_sar(df: gpd.GeoDataFrame, target: str, features: list[str], w) -> SARFit:
    """Ajusta un SAR explícito para simulación, aunque no sea el modelo recomendado por LM."""
    y = df[[target]].to_numpy(float)
    x = df[features].to_numpy(float)
    y_mean = float(y.mean())
    y_scale = float(y.std())
    x_mean = x.mean(axis=0)
    x_scale = x.std(axis=0)
    if not np.isfinite(y_scale) or y_scale <= 0 or not np.isfinite(x_scale).all() or (x_scale <= 0).any():
        raise ValueError("El SAR necesita variación en Y y en cada indicador explicativo (X).")

    y_std = (y - y_mean) / y_scale
    x_std = (x - x_mean) / x_scale
    try:
        model = spreg.ML_Lag(
            y_std, x_std, w=w, name_y=target, name_x=features,
            epsilon=1e-5, spat_impacts=None,
        )
    except Exception as exc:  # noqa: BLE001
        if "power expansion will not converge" not in str(exc).lower():
            raise
        return _fit_sar_profile(y, x, w, target, features, x_mean, x_scale, y_mean, y_scale)

    rho = float(model.rho)
    coefs, beta = _sar_coefs_original_scale(
        np.ravel(model.betas)[:-1], rho, model.vm, x_mean, x_scale, y_mean, y_scale,
        ["CONSTANTE", *features],
    )
    return SARFit(model, rho, coefs, sar_impacts(pd.Series(beta, index=features), rho, w),
                  ["Y y X se estandarizan internamente para mejorar la estabilidad numérica; la tabla se expresa en unidades originales."])


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
        fit.notes.extend(sar.notes)
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
