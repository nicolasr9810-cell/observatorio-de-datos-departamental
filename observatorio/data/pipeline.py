# -*- coding: utf-8 -*-
"""Orquestación de la carga. Sin Streamlit: se usa igual en Colab y en la app."""
from __future__ import annotations

import logging

import pandas as pd

from observatorio.core.http import DataSourceError
from observatorio.data import loaders as L


def _unavailable(quality: list[dict], indicator: str, source: str, exc: Exception):
    logging.warning("Fuente no disponible (%s): %s", source, exc)
    quality.append({
        "Indicador": indicator,
        "Estado": "No disponible",
        "Filas válidas": 0,
        "Detalle": "No se pudo consultar en esta carga. Revisa la conexión e inténtalo de nuevo.",
        "Fuente": source,
    })


def _try_load(parts: list[pd.DataFrame], quality: list[dict], indicator: str,
              source: str, loader, *args):
    try:
        parts.extend(loader(*args))
        return True
    except (DataSourceError, ValueError) as exc:
        _unavailable(quality, indicator, source, exc)
        return False


def load_all() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Devuelve (master largo, calidad); una fuente caída no bloquea las demás."""
    quality: list[dict] = []
    parts: list[pd.DataFrame] = []

    try:
        population = L.load_population(quality)
    except (DataSourceError, ValueError) as exc:
        population = None
        _unavailable(quality, "Población de referencia", "DANE - proyecciones de población", exc)

    if population is not None:
        _try_load(parts, quality, "PIB departamental y por habitante", "PIB departamental + población DANE",
                  L.load_gdp, population, quality)
        _try_load(parts, quality, "Homicidios y tasa por 100.000 habitantes",
                  "Ministerio de Defensa + población DANE", L.load_homicides, population, quality)
        _try_load(parts, quality, "Recursos DNP y recursos por habitante",
                  "DNP-RecursosEntidad + población DANE", L.load_finance, population, quality)
    else:
        for indicator, source in [
            ("PIB y PIB por habitante", "PIB departamental + población DANE"),
            ("Homicidios y tasa por 100.000 habitantes", "Ministerio de Defensa + población DANE"),
            ("Recursos DNP y recursos por habitante", "DNP-RecursosEntidad + población DANE"),
        ]:
            _unavailable(quality, indicator, source,
                         DataSourceError("No consultado: depende de las proyecciones de población."))

    _try_load(parts, quality, "Pobreza monetaria y coeficiente de Gini", "DANE - pobreza y desigualdad",
              L.load_poverty_gini, quality)
    _try_load(parts, quality, "Cobertura y deserción escolar", "MEN - estadísticas de educación",
              L.load_education, quality)
    _try_load(parts, quality, "Grupos de investigación reconocidos", "MinCiencias - grupos reconocidos",
              L.load_ctei, quality)

    if not parts:
        raise DataSourceError("FALLÓ EL PIPELINE: no quedaron indicadores válidos. Revisa las fuentes y vuelve a intentar.")
    master = pd.concat(parts, ignore_index=True)
    master["anio"] = pd.to_numeric(master["anio"], errors="coerce")
    master["valor"] = pd.to_numeric(master["valor"], errors="coerce")
    master = master.dropna(subset=["departamento", "codigo_divipola", "anio", "valor"])
    master["anio"] = master["anio"].astype(int)
    if master.empty:
        raise DataSourceError("FALLÓ EL PIPELINE: cero indicadores válidos. Revisa las fuentes y sus campos.")
    master = master.sort_values(["categoria", "indicador", "departamento", "anio"])
    return master.reset_index(drop=True), pd.DataFrame(quality)
