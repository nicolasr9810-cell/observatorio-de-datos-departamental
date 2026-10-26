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
          "ninguno sustituye una evaluación de impacto causal.",
          "Cambia una variable en el modelo para explorar un escenario hipotético y ver cómo se moverían "
          "los resultados. El cálculo depende de los supuestos del modelo y no predice el efecto real de una política.")

engine = st.radio(
    "Tipo de escenario",
    ["Espacial (SAR): derrames territoriales", "VAR/VECM: choque dinámico", "ML: contrafactual de Nariño"],
    horizontal=True,
    help="Elige un modelo que ya hayas estimado. Cada opción usa un supuesto distinto.",
)

with st.expander("Qué hace cada tipo de escenario"):
    st.markdown(
        "- **SAR espacial:** cambia una variable en algunos departamentos y calcula también posibles derrames "
        "a sus vecinos.\n"
        "- **VAR/VECM:** aplica un choque de una sola vez y sigue la respuesta estimada en los años siguientes.\n"
        "- **Contrafactual ML:** modifica los datos de entrada de un departamento y compara la predicción del modelo.\n"
        "En los tres casos el resultado depende de supuestos y asociaciones observadas; no es una evaluación "
        "del efecto real de una política."
    )

if engine.startswith("Espacial"):
    sp = st.session_state.get("sp_last")
    sar_fit = None if not sp else sp.get("sar")
    if sar_fit is None and sp and sp["fit"].rho is not None:
        sar_fit = sp["fit"]  # compatibilidad con el estado guardado antes del ajuste SAR alternativo
    if not sp or sar_fit is None:
        st.info(
            "Para simular derrames necesitas estimar un SAR. Entra a **Econometría espacial**, "
            "elige un año con suficiente cobertura y, si las pruebas recomiendan OLS o SEM, activa "
            "la opción de SAR alternativo para escenarios."
        )
        st.caption("Abre **Econometría espacial** desde el menú lateral para preparar el modelo SAR.")
        st.stop()
    fit, gdf, w = sar_fit, sp["gdf"], sp["w"]
    c1, c2, c3 = st.columns(3)
    var = c1.selectbox("Indicador que cambia (X)", sp["feats"],
                       help="Es una de las variables explicativas del SAR.")
    delta = c2.number_input("Cambio supuesto en X (unidades)", value=1.0,
                            help="Cambio absoluto aplicado por igual a cada territorio seleccionado.")
    codes = gdf.codigo_divipola.tolist()
    default_targets = [NARINO] if NARINO in codes else codes[:1]
    targets = c3.multiselect("Departamentos intervenidos", codes, default=default_targets,
                             format_func=DIVIPOLA.get,
                             help="Los demás departamentos solo reciben el efecto indirecto estimado por el SAR.")
    if not targets:
        st.info("Selecciona al menos un departamento para calcular el escenario.")
        st.stop()
    beta = float(fit.coefs.loc[var, "Coeficiente"])
    sim = policy.spatial_policy(gdf, w, fit.rho, beta, delta, targets)
    st.markdown(
        f"El escenario cambia **{var}** en {delta:+,.3f} unidades en los departamentos seleccionados. "
        f"Con ρ = {fit.rho:.3f} y β = {beta:.4f}, el cambio simulado agregado es "
        f"**{sim['Δy simulado'].sum():+,.3f}** en {sp['target']}."
    )
    st.plotly_chart(maps.choropleth(gdf, sim, "Δy simulado", f"Efecto simulado sobre {sp['target']}",
                                    diverging=True, highlight=targets[0] if targets else None),
                    width="stretch")
    ui.fmt_table(sim.set_index("departamento").sort_values("Δy simulado", key=abs, ascending=False))
    st.caption("La columna Δy es una variación estimada por el modelo; no es el valor observado ni una evaluación causal.")

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
    st.caption("La trayectoria muestra la diferencia frente al pronóstico base tras un choque hipotético.")

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
