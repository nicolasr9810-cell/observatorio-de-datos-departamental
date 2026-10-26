# -*- coding: utf-8 -*-
"""Vista 5 · Series de tiempo multivariadas: VAR y VECM."""
import streamlit as st

from observatorio.analytics import timeseries
from observatorio.config import DIVIPOLA, NARINO
from observatorio.core import panel
from observatorio.ui import components as ui, state
from observatorio.viz import charts

master, quality = state.master()
ui.header("📈 VAR y VECM", "Estacionariedad (ADF/KPSS) → cointegración de Johansen → VAR o VECM, "
          "con causalidad de Granger, impulso-respuesta y pronóstico.")

with st.sidebar:
    code = st.selectbox("Territorio", sorted(DIVIPOLA), index=sorted(DIVIPOLA).index(NARINO),
                        format_func=DIVIPOLA.get)
    ind = ui.pick_indicators(master, "Variables endógenas (2–4)", key="ts_ind", default_n=3)
    mode = st.radio("Especificación", ["Automático", "VAR en niveles", "VAR en diferencias", "VECM"])
    maxlags = st.slider("Rezagos máximos", 1, 4, 2)
    steps = st.slider("Horizonte de pronóstico (años)", 1, 6, 3)

if len(ind) > 4:
    st.warning("Con series anuales cortas, más de 4 variables agota los grados de libertad.")
m = state.run(panel.territory_series, master, ind, code, min_rows=10)
df = m.data
st.caption(f"{DIVIPOLA[code]}: {len(df)} años consecutivos ({df.index.min()}–{df.index.max()}).")
rank = 1
if mode == "VECM":
    rank = st.number_input("Rango de cointegración", 1, len(ind) - 1, 1)
ts, st_tab, jt = state.run(state.ts_model, df, mode, maxlags, steps, rank)

st.success(f"Modelo estimado: **{ts.model_type}** · rezagos = {ts.lags}")
ui.notes(ts.notes)
t1, t2, t3, t4 = st.tabs(["Pruebas", "Impulso-respuesta", "Pronóstico", "Granger / ajuste"])
with t1:
    st.markdown("**Raíz unitaria** (ADF: H0 raíz unitaria · KPSS: H0 estacionariedad)")
    ui.fmt_table(st_tab.set_index("Variable"))
    if jt is not None:
        st.markdown("**Cointegración de Johansen (traza)**")
        ui.fmt_table(jt.set_index("H0: rango ≤"))
with t2:
    imp = st.selectbox("Variable que recibe el choque", ind)
    orth = st.toggle("Choques ortogonalizados (Cholesky, 1 d.e.)", True,
                     help="El orden de las variables define la identificación de Cholesky.")
    st.plotly_chart(charts.irf(timeseries.irf_table(ts, imp, 6, orth), imp), width="stretch")
with t3:
    var = st.selectbox("Variable", ind, key="fc_var")
    st.plotly_chart(charts.forecast(df, ts.forecast, ts.lower, ts.upper, var), width="stretch")
    ui.download(ts.forecast, "pronostico_var")
with t4:
    if ts.granger is not None:
        st.markdown("p-valores de Granger: fila = causada, columna = causante.")
        st.plotly_chart(charts.heatmap(ts.granger.astype(float), "Causalidad de Granger (p)", zmid=None),
                        width="stretch")
    st.text(str(ts.results.summary()))
st.session_state["ts_last"] = ts
