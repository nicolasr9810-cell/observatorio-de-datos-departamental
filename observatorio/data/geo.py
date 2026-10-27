# -*- coding: utf-8 -*-
"""Geometrías departamentales oficiales (DANE) para mapas y pesos espaciales."""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
from shapely.ops import unary_union

from observatorio.config import DIVIPOLA, GEO_LOCAL, GEO_QUERY
from observatorio.core.http import get_json, source_error
from observatorio.core.normalize import norm_code

SOURCE = "DANE Geoportal - capa de límites departamentales"


def _polygon_parts(geometry) -> list:
    """Extrae polígonos de geometrías mixtas; líneas y puntos no definen áreas."""
    if geometry is None or not hasattr(geometry, "geom_type") or geometry.is_empty:
        return []
    kind = geometry.geom_type
    if kind == "Polygon":
        return [geometry]
    if kind == "MultiPolygon":
        return list(geometry.geoms)
    if kind == "GeometryCollection":
        return [part for child in geometry.geoms for part in _polygon_parts(child)]
    return []


def polygonal_geometry(geometry):
    """Devuelve Polygon/MultiPolygon válido o None si no hay un área utilizable.

    make_valid puede devolver una GeometryCollection con polígonos y líneas.
    Libpysal requiere geometrías poligonales para pesos de contigüidad.
    """
    if geometry is None or not hasattr(geometry, "geom_type") or geometry.is_empty:
        return None
    valid = geometry if geometry.is_valid else geometry.make_valid()
    parts = _polygon_parts(valid)
    if not parts:
        return None
    merged = unary_union(parts)
    return merged if merged.geom_type in {"Polygon", "MultiPolygon"} and not merged.is_empty else None


def load_departments() -> gpd.GeoDataFrame:
    """GeoDataFrame EPSG:4326 con columnas codigo_divipola, departamento, geometry.

    Prioriza un GeoJSON local (MGN DANE) si existe; si no, consulta el servicio ArcGIS
    de la capa administrativa "Departamentos". Se descarga la geometría completa para
    conservar las fronteras compartidas que necesita la contigüidad Reina.
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
            "outSR": "4326", "f": "geojson",
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
    polygonal = gdf.geometry.map(polygonal_geometry)
    unusable = polygonal.map(lambda geom: geom is None or geom.is_empty)
    if unusable.any():
        codes = gdf.loc[unusable, "codigo_divipola"].tolist()
        endpoint = str(local) if local.exists() else GEO_QUERY
        raise source_error(
            SOURCE, endpoint, ValueError(f"geometrías sin polígonos válidos para DIVIPOLA: {codes}"),
            "vuelve a descargar los límites departamentales; cada departamento debe tener un Polygon o MultiPolygon.",
        )
    gdf = gdf.set_geometry(polygonal)
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
