# -*- coding: utf-8 -*-
"""Única capa que conoce Streamlit + caché. Los módulos analíticos quedan puros.

- st.cache_data     -> datos (DataFrames serializables): master, geometrías, tablas.
- st.cache_resource -> modelos ajustados (objetos pesados que no conviene copiar).
"""
from __future__ import annotations

import logging

import streamlit as st

from observatorio.analytics import dimred, explain, ml, spatial, timeseries
from observatorio.config import GEO_CACHE_VERSION
from observatorio.core.http import DataSourceError, InsufficientDataError
from observatorio.data import geo
from observatorio.data.pipeline import load_all

TTL = 21600  # 6 h, igual que la versión original


@st.cache_data(ttl=TTL, show_spinner="Consultando fuentes oficiales y preparando indicadores…")
def _master():
    return load_all()


@st.cache_data(ttl=TTL * 4, show_spinner="Descargando límites departamentales DANE…")
def _geo(cache_version: str):
    # La versión cambia con la capa fuente para no reutilizar geometrías antiguas.
    return geo.load_departments()


def run(fn, *args, **kwargs):
    """Ejecuta con la política fail-fast: error técnico visible y detención de la vista."""
    try:
        return fn(*args, **kwargs)
    except DataSourceError as exc:
        logging.error("%s", exc)
        st.error("La carga se detuvo porque falló una fuente requerida.")
        st.code(str(exc), language="text")
    except InsufficientDataError as exc:
        st.warning(f"Datos insuficientes para estimar con rigor: {exc}")
    except Exception as exc:  # noqa: BLE001
        logging.exception("Falla de procesamiento")
        st.error("Error inesperado; no se muestran resultados parciales.")
        st.code(f"{type(exc).__name__}: {exc}", language="text")
    st.stop()


def master():
    result = run(_master)
    _, quality = result
    if "Estado" in quality:
        unavailable = quality[quality["Estado"] == "No disponible"]
        if not unavailable.empty:
            names = unavailable["Indicador"].dropna().astype(str).drop_duplicates().tolist()
            shown = ", ".join(names[:3])
            more = f" y {len(names) - 3} más" if len(names) > 3 else ""
            st.warning(
                f"Algunas fuentes no respondieron; el resto de los indicadores sigue disponible. "
                f"No se cargó: {shown}{more}. Revisa **Datos y calidad** para ver el estado."
            )
            if st.button("Reintentar carga de datos", key="retry_data_sources",
                         help="Vuelve a consultar las fuentes públicas; puede tardar un poco."):
                _master.clear()
                st.rerun()
    return result


def departments():
    return run(_geo, GEO_CACHE_VERSION)


# ---------- modelos cacheados (la clave incluye los datos y parámetros) ----------
@st.cache_resource(show_spinner="Entrenando y validando modelo…", max_entries=32)
def fit_ml(X, y, groups, kind: str, scheme: str):
    return ml.fit_evaluate(X, y, groups, kind, scheme)


@st.cache_resource(show_spinner="Comparando modelos…", max_entries=16)
def compare_ml(X, y, groups, scheme: str):
    return ml.compare(X, y, groups, scheme)


@st.cache_resource(show_spinner="Calculando valores SHAP…", max_entries=16)
def shap_for(_fit, key: tuple):
    """'_fit' no se hashea (objeto pesado); 'key' identifica unívocamente el ajuste."""
    return explain.shap_explain(_fit.pipeline, _fit.X)


@st.cache_data(show_spinner=False)
def pca(cs, orient_by):
    return dimred.run_pca(cs, orient_by=orient_by)


@st.cache_resource(show_spinner="Estimando modelo multivariado…", max_entries=16)
def ts_model(df, mode: str, maxlags: int, steps: int, rank: int = 1):
    if mode == "Automático":
        return timeseries.auto_model(df, maxlags, steps)
    st_tab = timeseries.stationarity(df)
    if mode == "VECM":
        r, jt = timeseries.johansen(df)
        return timeseries.fit_vecm(df, rank, 1, steps), st_tab, jt
    return timeseries.fit_var(df, maxlags, diff=(mode == "VAR en diferencias"), steps=steps), st_tab, None


@st.cache_resource(show_spinner="Construyendo matriz de pesos espaciales…", max_entries=16)
def weights(_gdf, key: tuple, kind: str, k: int):
    return spatial.build_weights(_gdf, kind, k)


@st.cache_resource(show_spinner="Estimando SAR para el escenario…", max_entries=16)
def sar_model(_gdf, _w, key: tuple, target: str, features: tuple[str, ...]):
    """Ajuste SAR alternativo cacheado para simulación de derrames."""
    return spatial.fit_sar(_gdf, target, list(features), _w)
