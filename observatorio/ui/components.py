# -*- coding: utf-8 -*-
"""Widgets compartidos entre vistas."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from observatorio.core import panel

FOCUS = ["Nariño", "Cauca", "Valle del Cauca", "Putumayo"]


def header(title: str, help_text: str, plain_language: str | None = None):
    st.title(title)
    st.caption(help_text)
    if plain_language:
        st.info(f"**En palabras sencillas:** {plain_language}")


def pick_indicators(master: pd.DataFrame, label: str = "Indicadores", key: str = "ind",
                    default_n: int = 4, min_n: int = 2) -> list[str]:
    """Selector de indicadores ordenado por cobertura (departamento-año con dato)."""
    cov = master.groupby("indicador").size().sort_values(ascending=False)
    opts = cov.index.tolist()
    sel = st.multiselect(label, opts, default=opts[:default_n], key=key,
                         help="Ordenados por cobertura. Solo se usan casos completos: no hay imputación.")
    if len(sel) < min_n:
        st.info(f"Elige al menos {min_n} indicadores.")
        st.stop()
    return sel


def pick_year(master: pd.DataFrame, indicators: list[str], key: str) -> int:
    years = panel.common_years(master, indicators)
    if not years:
        st.warning("Los indicadores elegidos no comparten ningún año.")
        st.stop()
    best = max(years, key=lambda y: master[(master.anio == y) & master.indicador.isin(indicators)]
               .codigo_divipola.nunique())
    return st.select_slider("Año del corte transversal", years, value=best, key=key)


def notes(items: list[str]):
    for n in items:
        (st.warning if n.startswith("⚠️") else st.info)(n)


def dropped(m: panel.Matrix):
    if m.dropped:
        st.caption(f"Casos completos: {len(m.data)} · descartados por faltantes: {m.dropped} (sin imputación).")


def download(df: pd.DataFrame, name: str, label: str = "Descargar CSV"):
    st.download_button(label, df.to_csv().encode("utf-8-sig"), f"{name}.csv", "text/csv", key=f"dl_{name}")


def fmt_table(df: pd.DataFrame, digits: int = 3):
    num = df.select_dtypes("number").columns
    st.dataframe(df.style.format({c: f"{{:,.{digits}f}}" for c in num}), width="stretch")
