# -*- coding: utf-8 -*-
"""Mapas coropléticos interactivos (Plotly + MapLibre, sin token)."""
from __future__ import annotations

import geopandas as gpd
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from observatorio.config import NARINO
from observatorio.data.geo import to_geojson

CENTER = {"lat": 4.3, "lon": -73.5}
LISA_COLORS = {"Alto-Alto": "#d7191c", "Bajo-Bajo": "#2c7bb6", "Alto-Bajo": "#fdae61",
               "Bajo-Alto": "#abd9e9", "No significativo": "#e6e6e6"}


def _highlight(fig: go.Figure, gdf: gpd.GeoDataFrame, code: str = NARINO) -> go.Figure:
    """Contorno grueso del departamento foco (Nariño por defecto)."""
    sel = gdf[gdf.codigo_divipola == code]
    if sel.empty:
        return fig
    for geom in getattr(sel.geometry.iloc[0], "geoms", [sel.geometry.iloc[0]]):
        lon, lat = geom.exterior.coords.xy
        fig.add_trace(go.Scattermap(lon=list(lon), lat=list(lat), mode="lines",
                                    line={"width": 3, "color": "#111"}, hoverinfo="skip", showlegend=False))
    return fig


def _layout(fig: go.Figure, title: str, height: int) -> go.Figure:
    fig.update_layout(title=title, height=height, margin={"l": 0, "r": 0, "t": 40, "b": 0},
                      map={"style": "carto-positron", "center": CENTER, "zoom": 4.1})
    return fig


def choropleth(gdf: gpd.GeoDataFrame, values: pd.DataFrame, value_col: str, title: str = "",
               unit: str = "", scale: str = "Viridis", diverging: bool = False, height: int = 620,
               highlight: str | None = NARINO) -> go.Figure:
    """values: DataFrame con 'codigo_divipola' y value_col. Departamentos sin dato quedan en gris."""
    data = gdf[["codigo_divipola", "departamento"]].merge(values[["codigo_divipola", value_col]],
                                                          on="codigo_divipola", how="left")
    kw = {}
    if diverging:
        m = data[value_col].abs().max()
        kw = {"color_continuous_scale": "RdBu_r", "range_color": (-m, m)}
    else:
        kw = {"color_continuous_scale": scale}
    fig = px.choropleth_map(data, geojson=to_geojson(gdf), locations="codigo_divipola", color=value_col,
                            hover_name="departamento", hover_data={"codigo_divipola": False, value_col: ":,.3f"},
                            opacity=.8, labels={value_col: unit or value_col}, **kw)
    missing = data[data[value_col].isna()]
    if not missing.empty:
        fig.add_trace(go.Choroplethmap(geojson=to_geojson(gdf), locations=missing.codigo_divipola,
                                       z=[0] * len(missing), colorscale=[[0, "#cccccc"], [1, "#cccccc"]],
                                       showscale=False, text=missing.departamento,
                                       hovertemplate="%{text}: sin dato<extra></extra>"))
    if highlight:
        _highlight(fig, gdf, highlight)
    return _layout(fig, title, height)


def lisa_map(gdf: gpd.GeoDataFrame, lisa: pd.DataFrame, title: str = "Clústeres LISA", height: int = 620) -> go.Figure:
    """gdf y lisa en el mismo orden (salida de spatial.align + spatial.local_moran)."""
    data = gdf[["codigo_divipola", "departamento"]].assign(Cuadrante=lisa["Cuadrante"].values,
                                                           p=lisa["p"].values)
    fig = px.choropleth_map(data, geojson=to_geojson(gdf), locations="codigo_divipola", color="Cuadrante",
                            color_discrete_map=LISA_COLORS, hover_name="departamento",
                            hover_data={"codigo_divipola": False, "p": ":.3f"}, opacity=.85,
                            category_orders={"Cuadrante": list(LISA_COLORS)})
    _highlight(fig, gdf)
    return _layout(fig, title, height)


def moran_scatter(lisa: pd.DataFrame, names: pd.Series, I: float) -> go.Figure:
    df = lisa.assign(Departamento=names.values)
    fig = px.scatter(df, x="z", y="Wz", color="Cuadrante", color_discrete_map=LISA_COLORS,
                     hover_name="Departamento", template="plotly_white",
                     labels={"z": "Valor estandarizado", "Wz": "Rezago espacial"},
                     title=f"Diagrama de Moran (I = {I:.3f})", trendline=None)
    lim = max(df.z.abs().max(), df.Wz.abs().max()) * 1.1
    fig.add_trace(go.Scatter(x=[-lim, lim], y=[-lim * I, lim * I], mode="lines",
                             line={"dash": "dash", "color": "#555"}, name="Pendiente = I"))
    fig.add_hline(y=0, line_color="#aaa")
    fig.add_vline(x=0, line_color="#aaa")
    return fig
