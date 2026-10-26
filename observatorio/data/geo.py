# -*- coding: utf-8 -*-
"""Geometrías departamentales oficiales (DANE) para mapas y pesos espaciales."""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd

from observatorio.config import DIVIPOLA, GEO_LOCAL, GEO_QUERY
from observatorio.core.http import get_json, source_error
from observatorio.core.normalize import norm_code

SOURCE = "DANE geoportal - límites departamentales (servicio de pobreza 2012-2020)"


def load_departments(simplify_deg: float = 0.01) -> gpd.GeoDataFrame:
    """GeoDataFrame EPSG:4326 con columnas codigo_divipola, departamento, geometry.

    Prioriza un GeoJSON local (MGN DANE) si existe; si no, consulta el servicio ArcGIS
    con geometría simplificada en el servidor (maxAllowableOffset) para aligerar la carga.
    """
    local = Path(GEO_LOCAL)
    if local.exists():
        gdf = gpd.read_file(local)
        code_col = next((c for c in gdf.columns if c.upper() in {"DPTO_CCDGO", "DPTO", "COD_DPTO"}), None)
        if code_col is None:
            raise source_error(SOURCE, str(local), ValueError(f"sin columna de código: {list(gdf.columns)}"),
                               "el GeoJSON debe traer DPTO_CCDGO o equivalente.")
    else:
        payload = get_json(SOURCE, GEO_QUERY, {
            "where": "1=1", "outFields": "DPTO_CCDGO,DPTO_CNMBR", "returnGeometry": "true",
            "outSR": "4326", "maxAllowableOffset": simplify_deg, "f": "geojson",
        })
        feats = payload.get("features") if isinstance(payload, dict) else None
        if not feats:
            raise source_error(SOURCE, GEO_QUERY, ValueError("GeoJSON sin entidades"),
                               "revisa que la capa acepte f=geojson o descarga el MGN a data/departamentos.geojson.")
        gdf = gpd.GeoDataFrame.from_features(feats, crs="EPSG:4326")
        code_col = "DPTO_CCDGO"
    gdf["codigo_divipola"] = gdf[code_col].map(norm_code)
    gdf = gdf.dropna(subset=["codigo_divipola"]).dissolve(by="codigo_divipola", as_index=False)
    gdf["departamento"] = gdf["codigo_divipola"].map(DIVIPOLA)
    gdf["geometry"] = gdf.geometry.make_valid()
    if len(gdf) < 30:
        raise source_error(SOURCE, GEO_QUERY, ValueError(f"solo {len(gdf)} departamentos con geometría"),
                           "verifica la capa; se esperan 33 entidades (32 + Bogotá).")
    return gdf[["codigo_divipola", "departamento", "geometry"]].sort_values("codigo_divipola").reset_index(drop=True)


def to_geojson(gdf: gpd.GeoDataFrame) -> dict:
    """GeoJSON con el código DIVIPOLA en id y properties para enlazar mapas.

    Plotly y MapLibre no siempre tratan el índice de un GeoDataFrame como `id`.
    Guardar el código en ambos lugares hace explícita y estable la unión espacial.
    """
    features = []
    for code, geometry in gdf[["codigo_divipola", "geometry"]].itertuples(index=False, name=None):
        code = str(code)
        features.append({
            "type": "Feature",
            "id": code,
            "properties": {"codigo_divipola": code},
            "geometry": geometry.__geo_interface__,
        })
    return {"type": "FeatureCollection", "features": features}
