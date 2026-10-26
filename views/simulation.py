# -*- coding: utf-8 -*-
"""Vista 7 · Simulación de políticas: reutiliza los modelos estimados en las otras vistas."""
import pandas as pd
import plotly.express as px
import streamlit as st

from observatorio.analytics import policy
from observatorio.config import DIVIPOLA, NARINO
from observatorio.ui import components as ui
from observatorio.viz import maps

ui.header("🎛️ Simulación de políticas", "Escenarios sobre los modelos estimados. Cada motor declara su supuesto; "
          "ninguno sustituye una evaluación de impacto causal.")

engine = st.radio("Motor", ["Espacial (SAR): derrames territoriales", "VAR/VECM: choque dinámico",
                            "ML: contrafactual de Nariño"], horizontal=True)

if engine.startswith("Espacial"):
    sp = st.session_state.get("sp_last")
    if not sp or sp["fit"].rho is None:
        st.info("Primero estima un modelo SAR en la vista **Econometría espacial** (el SEM no transmite derrames de X).")
        st.stop()
    fit, gdf, w = sp["fit"], sp["gdf"], sp["w"]
    c1, c2, c3 = st.columns(3)
    var = c1.selectbox("Instrumento de política (X)", sp["feats"])
    delta = c2.number_input("Cambio en X (unidades)", value=1.0)
    targets = c3.multiselect("Departamentos intervenidos", gdf.codigo_divipola.tolist(), default=[NARINO],
                             format_func=DIVIPOLA.get)
    beta = float(fit.coefs.loc[var, "Coeficiente"])
    sim = policy.spatial_policy(gdf, w, fit.rho, beta, delta, targets)
    st.markdown(f"Δy = (I − ρW)⁻¹ β Δx con ρ = {fit.rho:.3f}, β({var}) = {beta:.4f}. "
                f"Efecto total agregado: **{sim['Δy simulado'].sum():,.3f}** en {sp['target']}.")
    st.plotly_chart(maps.choropleth(gdf, sim, "Δy simulado", f"Efecto simulado sobre {sp['target']}",
                                    diverging=True, highlight=targets[0] if targets else None),
                    width="stretch")
    ui.fmt_table(sim.set_index("departamento").sort_values("Δy simulado", key=abs, ascending=False))

elif engine.startswith("VAR"):
    ts = st.session_state.get("ts_last")
    if ts is None:
        st.info("Primero estima un modelo en la vista **VAR y VECM**.")
        st.stop()
    c1, c2 = st.columns(2)
    imp = c1.selectbox("Variable de política (choque)", list(ts.data.columns))
    shock = c2.number_input("Tamaño del choque (unidades de la variable)", value=1.0)
    path = policy.var_policy(ts, imp, shock)
    long = path.reset_index().melt("Año", var_name="Variable", value_name="Desvío vs. línea base")
    st.plotly_chart(px.bar(long, x="Año", y="Desvío vs. línea base", facet_col="Variable", template="plotly_white",
                           title=f"Trayectoria del choque en {imp} ({ts.model_type})")
                    .update_yaxes(matches=None), width="stretch")
    base = ts.forecast.reindex(path.index)
    st.markdown("**Escenario = pronóstico base + desvío** (años con pronóstico disponible)")
    ui.fmt_table(pd.concat({"Base": base, "Escenario": base + path}, axis=1).dropna())

else:
    last = st.session_state.get("ml_last")
    if last is None:
        st.info("Primero ajusta un modelo y abre la pestaña **Predicción Nariño** en la vista Machine Learning.")
        st.stop()
    fit, row = last["fit"], last["row"]
    x_row = fit.X.loc[[row]]
    st.caption(f"Modelo: {fit.kind} · observación {row[1]} {row[2]}")
    changes = {c: st.slider(f"{c} (% de cambio)", -50, 50, 0, key=f"cf_{c}") for c in fit.X.columns}
    out = policy.ml_counterfactual(fit.pipeline, x_row, changes)
    c = st.columns(3)
    c[0].metric("Predicción base", f"{out['Predicción base']:,.3f}")
    c[1].metric("Predicción simulada", f"{out['Predicción simulada']:,.3f}", f"{out['Cambio']:+,.3f}")
    c[2].metric("Cambio %", f"{out['Cambio %']:+.2f}%")
    st.warning("Contrafactual asociacional: muestra cómo responde el modelo, no un efecto causal de la política.")
