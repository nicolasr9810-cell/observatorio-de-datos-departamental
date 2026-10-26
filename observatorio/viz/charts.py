# -*- coding: utf-8 -*-
"""Gráficos reutilizables: SHAP, PCA, correlaciones, IRF, pronósticos."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from observatorio.analytics.explain import ShapResult

T = "plotly_white"


def heatmap(mat: pd.DataFrame, title: str, zmid: float | None = 0, fmt: str = ".2f") -> go.Figure:
    fig = px.imshow(mat, text_auto=fmt, color_continuous_scale="RdBu_r" if zmid is not None else "Blues",
                    zmin=-1 if zmid is not None else None, zmax=1 if zmid is not None else None,
                    aspect="auto", title=title, template=T)
    return fig.update_layout(height=max(380, 45 * len(mat)))


def shap_bar(res: ShapResult) -> go.Figure:
    imp = res.global_importance()
    return px.bar(imp, orientation="h", template=T, title="Importancia global (media |SHAP|)",
                  labels={"value": "Media |SHAP| (unidades de y)", "index": ""}).update_layout(showlegend=False)


def shap_beeswarm(res: ShapResult) -> go.Figure:
    """Cada punto = una observación; color = valor de la variable (bajo→alto)."""
    order = res.global_importance().index.tolist()
    fig = go.Figure()
    rng = np.random.default_rng(0)
    for i, col in enumerate(order):
        x = res.data[col]
        c = (x - x.min()) / (x.max() - x.min() + 1e-12)
        labels = [" · ".join(map(str, k[1:])) if isinstance(k, tuple) else str(k) for k in res.values.index]
        fig.add_trace(go.Scatter(
            x=res.values[col], y=i + rng.uniform(-.25, .25, len(x)), mode="markers",
            marker={"color": c, "colorscale": "RdBu_r", "size": 7, "opacity": .8,
                    "colorbar": {"title": "Valor<br>de X", "tickvals": [0, 1], "ticktext": ["Bajo", "Alto"]}
                    if i == 0 else None, "showscale": i == 0},
            text=labels, customdata=x, name=col, showlegend=False,
            hovertemplate=f"<b>%{{text}}</b><br>{col} = %{{customdata:,.2f}}<br>SHAP = %{{x:,.3f}}<extra></extra>"))
    fig.update_layout(template=T, title="Resumen SHAP (dirección y magnitud)", height=120 + 60 * len(order),
                      yaxis={"tickvals": list(range(len(order))), "ticktext": order}, xaxis_title="Valor SHAP")
    return fig.add_vline(x=0, line_color="#888")


def shap_waterfall(res: ShapResult, row, top: int = 8) -> go.Figure:
    v = res.values.loc[row].sort_values(key=np.abs, ascending=False)
    head, rest = v.head(top), v.iloc[top:].sum()
    labels = [f"{k} = {res.data.loc[row, k]:,.2f}" for k in head.index] + (["Otras"] if len(v) > top else [])
    vals = list(head.values) + ([rest] if len(v) > top else [])
    fig = go.Figure(go.Waterfall(orientation="h", y=["Valor base"] + labels + ["Predicción"],
                                 x=[res.base_value] + vals + [0],
                                 measure=["absolute"] + ["relative"] * len(vals) + ["total"],
                                 decreasing={"marker": {"color": "#2c7bb6"}},
                                 increasing={"marker": {"color": "#d7191c"}}))
    return fig.update_layout(template=T, title="Descomposición SHAP de una predicción",
                             yaxis={"autorange": "reversed"}, height=140 + 40 * len(labels))


def pca_biplot(scores: pd.DataFrame, loadings: pd.DataFrame, names: pd.Series, color=None) -> go.Figure:
    df = scores[["CP1", "CP2"]].assign(Departamento=names.values)
    if color is not None:
        df["Grupo"] = color.values
    fig = px.scatter(df, x="CP1", y="CP2", text="Departamento", color="Grupo" if color is not None else None,
                     template=T, title="Biplot PCA")
    fig.update_traces(textposition="top center", textfont_size=9)
    k = np.abs(scores[["CP1", "CP2"]]).max().max() / np.abs(loadings[["CP1", "CP2"]]).max().max() * .8
    for var, r in loadings.iterrows():
        fig.add_annotation(x=r.CP1 * k, y=r.CP2 * k, ax=0, ay=0, xref="x", yref="y", axref="x", ayref="y",
                           showarrow=True, arrowhead=2, arrowcolor="#c0392b", text=var, font={"color": "#c0392b"})
    return fig


def forecast(hist: pd.DataFrame, fc: pd.DataFrame, lo: pd.DataFrame, up: pd.DataFrame, var: str) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=hist.index, y=hist[var], name="Observado", mode="lines+markers"))
    fig.add_trace(go.Scatter(x=list(up.index) + list(lo.index[::-1]), y=list(up[var]) + list(lo[var][::-1]),
                             fill="toself", fillcolor="rgba(44,123,182,.2)", line={"width": 0}, name="IC 95%"))
    fig.add_trace(go.Scatter(x=fc.index, y=fc[var], name="Pronóstico", mode="lines+markers",
                             line={"dash": "dash"}))
    return fig.update_layout(template=T, title=f"Pronóstico: {var}", xaxis_title="Año")


def irf(table: pd.DataFrame, impulse: str) -> go.Figure:
    long = table.reset_index().melt("Horizonte", var_name="Respuesta", value_name="Efecto")
    fig = px.line(long, x="Horizonte", y="Efecto", facet_col="Respuesta", facet_col_wrap=3, markers=True,
                  template=T, title=f"Funciones impulso-respuesta: choque en {impulse}")
    fig.update_yaxes(matches=None)
    return fig.add_hline(y=0, line_color="#888")
