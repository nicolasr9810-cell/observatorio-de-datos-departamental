# -*- coding: utf-8 -*-
"""Vista 2 · EDA automatizado."""
import plotly.express as px
import streamlit as st

from observatorio.analytics import eda
from observatorio.core import panel
from observatorio.ui import components as ui, state
from observatorio.viz import charts

master, quality = state.master()
ui.header("📊 Análisis exploratorio automatizado",
          "Perfil estadístico, normalidad, atípicos, correlaciones y multicolinealidad sobre casos completos.",
          "Resume los datos antes de modelar. Una correlación muestra que dos medidas se mueven juntas; "
          "no demuestra que una cause a la otra.")

with st.expander("¿Qué significa cada análisis?"):
    st.markdown(
        "- **Perfil:** resume valores típicos y cuánto varían los datos.\n"
        "- **Normalidad:** revisa si la forma de la distribución se parece a una campana; no califica "
        "si una variable es buena o mala.\n"
        "- **Atípicos:** señala valores alejados del resto; pueden ser casos reales o errores que conviene revisar.\n"
        "- **Correlación:** muestra si dos indicadores cambian en la misma dirección o en direcciones opuestas.\n"
        "- **Valor p:** indica cuánta evidencia hay contra una relación nula; no mide el tamaño ni la importancia "
        "práctica de la relación.\n"
        "- **VIF:** muestra cuánto se repite la información de una variable en las demás."
    )

with st.expander("Cobertura de datos (departamentos con dato por indicador y año)", expanded=False):
    st.plotly_chart(charts.heatmap(eda.coverage(master), "Cobertura", zmid=None, fmt="d"), width="stretch")
    st.caption("Cada celda cuenta cuántos departamentos tienen ese indicador en ese año; los espacios vacíos no se imputan.")

with st.sidebar:
    ind = ui.pick_indicators(master, key="eda_ind", default_n=5)
    years = sorted(master.anio.unique())
    yr = st.slider("Años", int(min(years)), int(max(years)), (int(min(years)), int(max(years))))
    method = st.radio("Correlación", ["spearman", "pearson"], horizontal=True)

m = state.run(panel.panel, master, ind, yr, min_rows=10)
ui.dropped(m)
w = m.data
prof = eda.profile(w)
r, p = eda.correlations(w, method)

st.subheader("Hallazgos automáticos")
for msg in eda.auto_insights(prof, r):
    st.markdown(f"- {msg}")

t1, t2, t3, t4 = st.tabs(["Perfil", "Distribuciones", "Correlaciones", "Multicolinealidad"])
with t1:
    ui.fmt_table(prof.set_index("Variable"))
    ui.download(prof, "perfil_eda")
with t2:
    var = st.selectbox("Variable", ind)
    long = w.reset_index()
    c1, c2 = st.columns(2)
    c1.plotly_chart(px.histogram(long, x=var, marginal="box", template="plotly_white", nbins=30),
                    width="stretch")
    c2.plotly_chart(px.box(long, x="anio", y=var, template="plotly_white", points="outliers",
                           hover_name="departamento", title="Distribución por año"), width="stretch")
with t3:
    st.plotly_chart(charts.heatmap(r, f"Correlación de {method.title()}"), width="stretch")
    st.caption("La correlación va de −1 a 1: cerca de 1 indica que ambas medidas tienden a subir juntas; cerca de −1, que una sube cuando la otra baja. Las celdas con p ≥ 0.05 no son estadísticamente distintas de cero.")
    ui.fmt_table(p)
with t4:
    v = eda.vif(w)
    ui.fmt_table(v.set_index("Variable"), 2)
    st.caption("VIF mide cuánto se solapa una variable con las demás. Un valor mayor que 10 suele indicar solapamiento fuerte; Ridge, Lasso o PCA pueden ayudar a resumirlo.")
