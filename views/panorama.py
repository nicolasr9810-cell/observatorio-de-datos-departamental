# -*- coding: utf-8 -*-
"""Vista 1 · Panorama: tablero original (KPIs, tendencias, ranking, dispersión) + mapa."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from observatorio.core.normalize import norm
from observatorio.ui import state
from observatorio.viz import maps

def show_value(value: float, unit: str) -> str:
    if pd.isna(value):
        return "Sin dato"
    if unit == "Porcentaje":
        return f"{value:,.1f}%"
    if unit.startswith("Coeficiente"):
        return f"{value:.3f}"
    if unit == "Grupos (conteo)" or unit == "Víctimas":
        return f"{value:,.0f}"
    return f"{value:,.2f}"


def reference(master: pd.DataFrame, indicator: str, year: int) -> tuple[float | None,str]:
    data = master[(master.indicador==indicator)&(master.anio==year)].copy()
    data["key"] = data.departamento.map(norm)
    national = data[data.key.isin({"colombia","nacional","total nacional"})]
    if not national.empty:
        return float(national.valor.iloc[0]),"Dato nacional publicado"
    other = data[data.departamento!="Nariño"].drop_duplicates("codigo_divipola")
    return (float(other.valor.mean()),"Promedio simple de otros departamentos") if not other.empty else (None,"Sin referencia")


def latest(master: pd.DataFrame, indicator: str) -> pd.Series | None:
    data = master[(master.indicador==indicator)&(master.departamento=="Nariño")].sort_values("anio")
    return None if data.empty else data.iloc[-1]


def pending() -> list[dict[str,str]]:
    return [
        {"Dimensión":"Mercado laboral GEIH","Estado":"Pendiente",
         "Nota":"Integrar anexos DANE y validar periodos, cobertura y comparabilidad.",
         "Fuente":"https://www.dane.gov.co/index.php/estadisticas-por-tema/mercado-laboral/mercado-laboral-por-departamentos/mercado-laboral-por-departamento-historicos"},
        {"Dimensión":"IDC","Estado":"Pendiente",
         "Nota":"Conectar la serie anual del Índice Departamental de Competitividad.",
         "Fuente":"https://compite.com.co/"},
        {"Dimensión":"Saber 11","Estado":"Pendiente",
         "Nota":"Se incluye cobertura MEN, no resultados departamentales de Saber 11.",
         "Fuente":"https://www.datos.gov.co/"},
        {"Dimensión":"Salud","Estado":"Pendiente",
         "Nota":"Faltan series departamentales con definición y denominador comprobados.",
         "Fuente":"https://www.dane.gov.co/index.php/estadisticas-por-tema/salud"},
        {"Dimensión":"Deforestación","Estado":"Pendiente",
         "Nota":"Confirmar campos, periodo y nivel geográfico del dataset IDEAM.",
         "Fuente":"https://www.datos.gov.co/Ambiente-y-Desarrollo-Sostenible/Monitoreo-de-bosques/pb29-gexz"},
        {"Dimensión":"CTeI - inversión I+D","Estado":"Parcial",
         "Nota":"Grupos reconocidos miden capacidad científica, no gasto en I+D.",
         "Fuente":"https://minciencias.gov.co/ciudadano/datosabiertos"},
    ]


master, quality = state.master()
st.title("🇨🇴 Observatorio Socioeconómico y de Competitividad")
st.subheader("Colombia con énfasis analítico en Nariño")
st.caption("Fuentes oficiales/públicas, sin datos sintéticos. La cobertura varía por indicador.")
st.info(
    "**Explora los datos:** elige una dimensión, un indicador, los departamentos y los años en el panel lateral. "
    "Después puedes consultar su tendencia, mapa, ranking y tabla descargable."
)

with st.sidebar:
    st.header("Ajusta tu exploración")
    mode = st.radio(
        "Enfoque", ["Vista Nacional General", "Vista de Análisis Profundo: Nariño"], index=1,
        help="La vista de Nariño sugiere compararlo con Cauca, Valle del Cauca y Putumayo.",
    )
    categories = sorted(master.categoria.unique())
    category = st.selectbox("Dimensión", categories, help="Área temática del indicador.")
    cat = master[master.categoria==category]
    indicator = st.selectbox(
        "Indicador", sorted(cat.indicador.unique()),
        help="Una medida concreta. La unidad y el año aparecen en los gráficos.",
    )
    depts = sorted(master.departamento.unique())
    defaults = [d for d in ["Nariño","Cauca","Valle del Cauca","Putumayo"] if d in depts] if mode.endswith("Nariño") else depts
    chosen_depts = st.multiselect("Departamentos", depts, default=defaults,
                                  help="Elige uno o varios territorios para compararlos.")
    years = sorted(master.loc[master.indicador==indicator,"anio"].unique())
    ymin,ymax = int(min(years)),int(max(years))
    period = st.slider("Rango de años", ymin, ymax, (ymin, ymax),
                       help="Los años dependen de la cobertura disponible para este indicador.") if ymin<ymax else (ymin,ymax)

view = master[(master.categoria==category)&(master.indicador==indicator)&master.anio.between(*period)]
if chosen_depts:
    view = view[view.departamento.isin(chosen_depts)]

st.markdown("### Indicadores clave de Nariño")
kpis = [x for x in ["PIB por habitante","Homicidios por 100.000 habitantes","Pobreza monetaria","Coeficiente de Gini"] if x in set(master.indicador)]
for col,name in zip(st.columns(max(1,len(kpis))),kpis):
    row = latest(master,name)
    if row is None:
        col.metric(name,"Sin dato")
    else:
        ref,ref_name = reference(master,name,int(row.anio))
        delta = None if ref is None else f"{row.valor-ref:+,.2f} vs ref."
        col.metric(f"{name} · {int(row.anio)}",show_value(row.valor,row.unidad),delta,
                   help=f"{ref_name}: {show_value(ref,row.unidad)}" if ref is not None else "Sin referencia")
st.caption("Si no hay dato nacional publicado, la referencia es la media simple de otros departamentos, no un agregado ponderado nacional.")

st.markdown("### Comparativa territorial")
if view.empty:
    st.info("No hay registros para estos filtros.")
else:
    trend = master[master.indicador==indicator]
    regional = trend[trend.departamento.isin(chosen_depts)][["anio","departamento","valor"]].copy()
    national = trend[trend.departamento.map(norm).isin({"colombia","nacional","total nacional"})]
    if national.empty:
        refline = trend[trend.departamento!="Nariño"].groupby("anio",as_index=False).valor.mean()
        refline["departamento"] = "Promedio simple de otros departamentos"
    else:
        refline = national[["anio","valor"]].copy()
        refline["departamento"] = "Colombia (dato publicado)"
    chart = pd.concat([regional,refline],ignore_index=True)
    chart = chart[chart.anio.between(*period)]
    fig = px.line(chart,x="anio",y="valor",color="departamento",markers=True,
                  title=f"Evolución: {indicator}",template="plotly_white",
                  labels={"anio":"Año","valor":view.unidad.iloc[0],"departamento":"Territorio"})
    fig.update_layout(hovermode="x unified",legend_title_text="")
    st.plotly_chart(fig,width="stretch")

tab0,tab1,tab2,tab3 = st.tabs(["Mapa","Ranking","Dispersión","Datos y calidad"])
with tab0:
    gdf = state.departments()
    myears = sorted(master.loc[master.indicador==indicator,"anio"].unique())
    myear = st.select_slider("Vigencia del mapa",myears,value=myears[-1],key="map_year") if len(myears) > 1 else myears[0]
    vals = master[(master.indicador==indicator)&(master.anio==myear)]
    st.plotly_chart(maps.choropleth(gdf,vals,"valor",f"{indicator} · {myear}",vals.unidad.iloc[0] if len(vals) else ""),width="stretch")
with tab1:
    choices = sorted(master.loc[master.indicador==indicator,"anio"].unique())
    year = st.selectbox("Vigencia",choices,index=len(choices)-1,key="rank_year")
    rank = master[(master.indicador==indicator)&(master.anio==year)].nlargest(15,"valor").sort_values("valor")
    fig = px.bar(rank,x="valor",y="departamento",orientation="h",color="valor",
                 color_continuous_scale="Blues",template="plotly_white",
                 title=f"Mayores valores · {year}")
    fig.update_layout(yaxis={"categoryorder":"total ascending"})
    st.plotly_chart(fig,width="stretch")
with tab2:
    all_ind = sorted(master.indicador.unique())
    xcol,ycol,yrc = st.columns([2,2,1])
    xind = xcol.selectbox("Eje X",all_ind,key="xind")
    yind = ycol.selectbox("Eje Y",all_ind,index=all_ind.index(indicator),key="yind")
    common = sorted(set(master.loc[master.indicador==xind,"anio"]) & set(master.loc[master.indicador==yind,"anio"]))
    if common:
        y = yrc.selectbox("Año",common,index=len(common)-1,key="scatter_year")
        xdf = master[(master.indicador==xind)&(master.anio==y)][["departamento","valor"]].rename(columns={"valor":"x"})
        ydf = master[(master.indicador==yind)&(master.anio==y)][["departamento","valor"]].rename(columns={"valor":"y"})
        scatter = xdf.merge(ydf,on="departamento")
        fig = px.scatter(scatter,x="x",y="y",text="departamento",hover_name="departamento",
                         template="plotly_white",title=f"{yind} vs {xind} · {y}")
        fig.update_traces(textposition="top center")
        st.plotly_chart(fig,width="stretch")
    else:
        st.info("Los indicadores no comparten vigencia.")
with tab3:
    st.dataframe(view.sort_values(["departamento","anio"]),width="stretch",hide_index=True)
    st.download_button("Descargar CSV",view.to_csv(index=False).encode("utf-8-sig"),
                       "observatorio_narino.csv","text/csv")
    st.markdown("#### Calidad de los datos")
    st.dataframe(quality,width="stretch",hide_index=True)

with st.expander("Cobertura, límites y fuentes"):
    st.markdown("Integrados: PIB, homicidios/tasa, recursos DNP, pobreza y Gini, coberturas/deserción MEN, grupos de investigación MinCiencias.")
    st.markdown("El PIB integrado procede de un dataset publicado por Gobernación de Caldas en datos.gov.co, no de una API directa DANE. Los grupos MinCiencias son capacidad científica, no inversión en I+D.")
    st.dataframe(pd.DataFrame(pending()),width="stretch",hide_index=True)
    st.markdown("Las fuentes activas son obligatorias: una caída o cambio de esquema detiene la carga y muestra error técnico y recomendación.")
st.caption("Caché de seis horas. Los datos se consultan desde las fuentes enlazadas al cargar.");
