# -*- coding: utf-8 -*-
"""Vista 4 · PCA, índice sintético y clustering no supervisado."""
import plotly.express as px
import streamlit as st

from observatorio.analytics import dimred
from observatorio.core import panel
from observatorio.ui import components as ui, state
from observatorio.viz import charts, maps

master, quality = state.master()
ui.header("🧭 Componentes principales y tipologías territoriales",
          "Reduce indicadores correlacionados a pocos factores, construye un índice sintético y agrupa departamentos.",
          "PCA resume varias medidas en pocos componentes y el agrupamiento junta departamentos con perfiles "
          "parecidos. El índice depende de las variables elegidas y los grupos no son categorías oficiales.")

with st.expander("Cómo leer los resultados"):
    st.markdown(
        "- **Componente principal (CP):** combinación de varios indicadores que resume parte de sus diferencias.\n"
        "- **Varianza explicada:** proporción de las diferencias entre departamentos que recoge cada CP.\n"
        "- **Carga:** señala qué tan relacionado está un indicador con un componente.\n"
        "- **Clúster K-means:** grupo de departamentos con perfiles parecidos en los indicadores elegidos.\n"
        "- **Silueta:** resume qué tan separados están los grupos; valores mayores suelen indicar grupos más definidos.\n"
        "- El índice 0–100 reescala el primer componente para comparar los departamentos incluidos; "
        "no es un puntaje oficial ni una medida absoluta de bienestar."
    )

with st.sidebar:
    ind = ui.pick_indicators(master, key="pca_ind", default_n=5, min_n=3)
    year = ui.pick_year(master, ind, "pca_year")
    orient = st.selectbox("Orientar CP1 hacia (carga positiva)", ind)

m = state.run(panel.cross_section, master, ind, year)
ui.dropped(m)
res = state.pca(m.data, orient)
names = m.data.index.get_level_values("departamento").to_series()
codes = m.data.index.get_level_values("codigo_divipola")

st.info(res.kmo_note)
c1, c2 = st.columns(2)
c1.plotly_chart(px.bar(res.explained, x="Componente", y="Varianza explicada", template="plotly_white",
                       title="Varianza explicada").add_scatter(x=res.explained.Componente, y=res.explained.Acumulada,
                                                               name="Acumulada"), width="stretch")
c2.plotly_chart(charts.heatmap(res.loadings, "Cargas factoriales (correlación variable–componente)"),
                width="stretch")

labels, sil = dimred.cluster(res.scores.iloc[:, :max(2, int((res.explained.Autovalor > 1).sum()))])
st.plotly_chart(charts.pca_biplot(res.scores, res.loadings, names, labels), width="stretch")

gdf = state.departments()
t1, t2 = st.tabs(["Mapa del índice sintético", "Mapa de clústeres"])
with t1:
    vals = res.index.reset_index()[["codigo_divipola", res.index.name]]
    st.plotly_chart(maps.choropleth(gdf, vals, res.index.name, f"Índice sintético CP1 · {year}", "0–100"),
                    width="stretch")
    st.caption("El índice es CP1 reescalado; su lectura depende de la orientación elegida y de los indicadores.")
with t2:
    cl = labels.reset_index()[["codigo_divipola", "Clúster"]]
    fig = px.choropleth_map(gdf.merge(cl, on="codigo_divipola"), geojson=maps.to_geojson(gdf),
                            featureidkey="properties.codigo_divipola", locations="codigo_divipola",
                            color="Clúster", hover_name="departamento",
                            map_style="carto-positron", center=maps.CENTER, zoom=4.1, opacity=.8, height=620)
    st.plotly_chart(fig, width="stretch")
    st.caption(f"K-means con k = {labels.nunique()} elegido por silueta máxima ({sil.Silueta.max():.2f}).")
ui.download(res.scores.join(res.index).join(labels), f"pca_{year}")
