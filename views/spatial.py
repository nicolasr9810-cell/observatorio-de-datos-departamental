# -*- coding: utf-8 -*-
"""Vista · Econometría espacial: Moran, LISA y modelos SAR/SEM."""
import streamlit as st

from observatorio.analytics import spatial
from observatorio.config import GEO_CACHE_VERSION
from observatorio.core import panel
from observatorio.ui import components as ui, state
from observatorio.viz import maps

master, quality = state.master()
ui.header("🗺️ Econometría espacial", "Dependencia espacial entre departamentos: I de Moran, clústeres LISA y "
          "selección OLS → SAR/SEM por pruebas de multiplicadores de Lagrange.",
          "Pregunta si departamentos vecinos tienden a parecerse y si un cambio en uno se relaciona "
          "con cambios en otros. Para que la comparación sea justa, el año debe tener datos suficientes "
          "para el mismo conjunto de departamentos.")

with st.sidebar:
    st.markdown("#### Controles del análisis")
    ind = ui.pick_indicators(master, "Indicadores disponibles", key="sp_ind", default_n=3, min_n=2)
    selection_key = "|".join(ind)
    target = st.selectbox(
        "Indicador a explicar (Y)", ind, index=0,
        help="Es el resultado que intentas entender, por ejemplo el PIB por habitante.",
        key=f"sp_target_{selection_key}",
    )
    available_features = [name for name in ind if name != target]
    feats = st.multiselect(
        "Indicadores explicativos (X)", available_features, default=available_features[:2],
        max_selections=3, help="Variables que podrían estar relacionadas con Y. Elige hasta tres.",
        key=f"sp_features_{selection_key}_{target}",
    )
    if not feats:
        st.warning("Elige al menos un indicador explicativo (X).")
        st.stop()
    variables = [target, *feats]
    coverage = panel.cross_section_coverage(master, variables)
    possible = coverage[coverage["Departamentos completos"] >= spatial.MIN_SPATIAL_N]
    if not possible.empty:
        available_years = possible["Año"].astype(int).tolist()
        best_year = int(possible.sort_values("Departamentos completos").iloc[-1]["Año"])
        year = st.select_slider(
            "Año del análisis", available_years, value=best_year,
            key=f"sp_year_{selection_key}_{target}_{'|'.join(feats)}",
        )
    else:
        year = None
        st.warning(
            f"Con esta selección no hay un año con {spatial.MIN_SPATIAL_N} departamentos completos. "
            "Prueba otros indicadores o usa menos variables."
        )
    wkind = st.radio(
        "Cómo definir los vecinos", ["Reina (contigüidad)", "KNN"],
        help="Reina conecta departamentos que comparten frontera. KNN conecta a cada departamento "
             "con sus k vecinos más cercanos.",
    )
    k = st.slider("k vecinos", 2, 8, 4) if wkind == "KNN" else 4

if year is None:
    st.warning(
        "No se estimó ningún modelo porque los datos no permiten una comparación territorial suficiente. "
        "Ajusta los indicadores en el panel lateral; la tabla muestra cuántos departamentos quedarían "
        "en cada año."
    )
    with st.expander("Ver cobertura por año", expanded=True):
        st.dataframe(coverage, width="stretch", hide_index=True)
    st.stop()

m = state.run(panel.cross_section, master, variables, year, min_rows=spatial.MIN_SPATIAL_N)
ui.dropped(m)
gdf = state.run(spatial.align, state.departments(), m.data)
w = state.run(
    state.weights, gdf,
    (tuple(gdf.codigo_divipola), GEO_CACHE_VERSION, wkind, k),
    wkind, k,
)
y = gdf[target].to_numpy(float)
mor = spatial.global_moran(y, w)
lisa = spatial.local_moran(y, w)

c = st.columns(4)
c[0].metric("I de Moran", f"{mor['I de Moran']:.3f}", help="Resume si los valores parecidos tienden a estar cerca.")
c[1].metric("Valor esperado", f"{mor['E[I]']:.3f}", help="Referencia teórica si no hubiera agrupación espacial.")
c[2].metric("p (999 perm.)", f"{mor['p (permutación)']:.3f}", help="Valores bajos indican más evidencia de autocorrelación espacial.")
c[3].metric("Departamentos", len(gdf), help="Territorios incluidos en este año con todos los indicadores elegidos.")
st.info(mor["Lectura"])
st.caption("Un resultado estadísticamente significativo señala un patrón, no explica por sí solo su causa.")

t1, t2, t3 = st.tabs(["Mapa de la variable", "Clústeres LISA", "Modelo espacial"])
with t1:
    st.plotly_chart(maps.choropleth(gdf, gdf, target, f"{target} · {year}"), width="stretch")
    st.caption("Cada departamento se colorea según su valor del indicador seleccionado. Los valores faltantes se dejan en gris.")
with t2:
    a, b = st.columns([3, 2])
    a.plotly_chart(maps.lisa_map(gdf, lisa), width="stretch")
    b.plotly_chart(maps.moran_scatter(lisa, gdf.departamento, mor["I de Moran"]), width="stretch")
    st.caption(
        "LISA busca agrupaciones locales: Alto-Alto y Bajo-Bajo son departamentos parecidos a sus vecinos; "
        "Alto-Bajo y Bajo-Alto son valores distintos. Solo se colorean clústeres con evidencia estadística."
    )
with t3:
    fit = spatial.fit_spatial(gdf, target, feats, w)
    st.success(f"Especificación recomendada: **{fit.recommended}**")
    st.caption(
        "OLS no encuentra dependencia espacial suficiente. SAR modela relación entre resultados vecinos. "
        "SEM atribuye la dependencia a factores no observados compartidos; no representa derrames de X."
    )
    ui.notes(fit.notes)
    ui.fmt_table(fit.diagnostics.set_index("Prueba"))
    ui.fmt_table(fit.coefs)
    if fit.impacts is not None:
        st.markdown("**Impactos (LeSage & Pace):** el derrame es el efecto sobre los demás departamentos.")
        ui.fmt_table(fit.impacts)
    sar_fit = fit if fit.rho is not None else None
    if sar_fit is None:
        with st.expander("Preparar un escenario espacial (opcional)"):
            st.info(
                f"Las pruebas recomiendan {fit.recommended}. Puedes ajustar un SAR aparte para explorar "
                "posibles derrames; se mostrará como análisis de sensibilidad, no como modelo recomendado."
            )
            use_sar = st.toggle(
                "Ajustar un SAR para la simulación",
                value=False,
                help="SAR supone que el indicador de cada departamento también depende del resultado en sus vecinos.",
                key="sp_sim_sar",
            )
            if use_sar:
                try:
                    sar_fit = state.sar_model(
                        gdf, w, (
                            tuple(gdf.codigo_divipola), int(year), target, tuple(feats), wkind, k,
                            tuple(gdf[[target, *feats]].to_numpy().ravel()),
                        ),
                        target, tuple(feats),
                    )
                    st.success("SAR alternativo estimado para explorar escenarios.")
                    ui.fmt_table(sar_fit.coefs)
                    ui.fmt_table(sar_fit.impacts)
                except Exception as exc:  # noqa: BLE001
                    st.warning(f"No fue posible ajustar el SAR alternativo: {type(exc).__name__}: {exc}")
                    sar_fit = None
    st.session_state["sp_last"] = {
        "fit": fit, "sar": sar_fit, "gdf": gdf, "w": w,
        "feats": feats, "target": target, "year": year,
    }
