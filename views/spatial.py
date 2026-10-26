# -*- coding: utf-8 -*-
"""Vista 6 · Econometría espacial: Moran, LISA y modelos SAR/SEM."""
import streamlit as st

from observatorio.analytics import spatial
from observatorio.core import panel
from observatorio.ui import components as ui, state
from observatorio.viz import maps

master, quality = state.master()
ui.header("🗺️ Econometría espacial", "Dependencia espacial entre departamentos: I de Moran, clústeres LISA y "
          "selección OLS → SAR/SEM por pruebas de multiplicadores de Lagrange.")

with st.sidebar:
    ind = ui.pick_indicators(master, "Variables (y + regresores)", key="sp_ind", default_n=3)
    target = st.selectbox("Variable dependiente", ind, index=1)
    feats = [c for c in ind if c != target]
    year = ui.pick_year(master, ind, "sp_year")
    wkind = st.radio("Matriz de pesos W", ["Reina (contigüidad)", "KNN"])
    k = st.slider("k vecinos", 2, 8, 4) if wkind == "KNN" else 4

m = state.run(panel.cross_section, master, ind, year)
ui.dropped(m)
gdf = state.run(spatial.align, state.departments(), m.data)
w = state.weights(gdf, (tuple(gdf.codigo_divipola), wkind, k), wkind, k)
y = gdf[target].to_numpy(float)
mor = spatial.global_moran(y, w)
lisa = spatial.local_moran(y, w)

c = st.columns(4)
c[0].metric("I de Moran", f"{mor['I de Moran']:.3f}")
c[1].metric("E[I]", f"{mor['E[I]']:.3f}")
c[2].metric("p (999 perm.)", f"{mor['p (permutación)']:.3f}")
c[3].metric("Departamentos", len(gdf))
st.info(mor["Lectura"])

t1, t2, t3 = st.tabs(["Mapa de la variable", "Clústeres LISA", "Modelo espacial"])
with t1:
    st.plotly_chart(maps.choropleth(gdf, gdf, target, f"{target} · {year}"), width="stretch")
with t2:
    a, b = st.columns([3, 2])
    a.plotly_chart(maps.lisa_map(gdf, lisa), width="stretch")
    b.plotly_chart(maps.moran_scatter(lisa, gdf.departamento, mor["I de Moran"]), width="stretch")
with t3:
    fit = spatial.fit_spatial(gdf, target, feats, w)
    st.success(f"Especificación recomendada: **{fit.recommended}**")
    ui.notes(fit.notes)
    ui.fmt_table(fit.diagnostics.set_index("Prueba"))
    ui.fmt_table(fit.coefs)
    if fit.impacts is not None:
        st.markdown("**Impactos (LeSage & Pace):** el derrame es el efecto sobre los demás departamentos.")
        ui.fmt_table(fit.impacts)
    st.session_state["sp_last"] = {"fit": fit, "gdf": gdf, "w": w, "feats": feats, "target": target, "year": year}
