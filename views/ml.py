# -*- coding: utf-8 -*-
"""Vista 3 · Machine Learning supervisado + interpretabilidad SHAP."""
import pandas as pd
import plotly.express as px
import streamlit as st

from observatorio.analytics import explain, ml
from observatorio.config import NARINO
from observatorio.core import panel
from observatorio.ui import components as ui, state
from observatorio.viz import charts

master, quality = state.master()
ui.header("🤖 Machine Learning e interpretabilidad",
          "Ridge, Lasso, SVR (SVM) y red neuronal MLP sobre el panel departamento × año, explicados con SHAP.")

with st.sidebar:
    ind = ui.pick_indicators(master, "Variables del panel", key="ml_ind", default_n=5, min_n=3)
    target = st.selectbox("Variable objetivo (y)", ind, index=1)
    feats = [c for c in ind if c != target]
    lag = st.radio("Especificación", [1, 0], format_func=lambda v: "Predictiva: X(t-1) → y(t)" if v else
                   "Contemporánea: X(t) → y(t)")
    scheme = st.radio("Validación", ["Por departamento", "Temporal"],
                      help="Por departamento: generaliza a territorios no vistos. Temporal: entrena en años "
                           "antiguos y prueba en los recientes.")
    kind = st.selectbox("Modelo a interpretar", ml.MODELS)

m = state.run(panel.panel, master, ind, min_rows=20)
ui.dropped(m)
X, y, g = state.run(ml.supervised_frame, m.data, target, feats, lag)

t1, t2, t3 = st.tabs(["Comparación de modelos", "Modelo e interpretación SHAP", "Predicción Nariño"])
with t1:
    cmp_ = state.compare_ml(X, y, g, scheme)
    ui.fmt_table(cmp_.set_index("Modelo"))
    st.caption("Métricas fuera de muestra (out-of-fold). Prefiere el modelo más simple dentro de ~1 RMSE del mejor.")

fit = state.fit_ml(X, y, g, kind, scheme)
with t2:
    ui.notes(fit.notes)
    c1, c2 = st.columns(2)
    obs = pd.DataFrame({"Observado": y, "Predicho (OOF)": fit.oof_pred}).dropna().reset_index()
    c1.plotly_chart(px.scatter(obs, x="Observado", y="Predicho (OOF)", hover_name="departamento",
                               hover_data=["anio"], template="plotly_white", title="Observado vs. predicho")
                    .add_shape(type="line", x0=y.min(), y0=y.min(), x1=y.max(), y1=y.max(),
                               line={"dash": "dash"}), width="stretch")
    if fit.coefs is not None:
        c2.plotly_chart(px.bar(fit.coefs.sort_values(), orientation="h", template="plotly_white",
                               title="Coeficientes estandarizados"), width="stretch")
    else:
        c2.dataframe(fit.cv_scores, hide_index=True)
    sh = state.shap_for(fit, (kind, scheme, lag, target, tuple(feats), len(X)))
    c3, c4 = st.columns(2)
    c3.plotly_chart(charts.shap_bar(sh), width="stretch")
    c4.plotly_chart(charts.shap_beeswarm(sh), width="stretch")
    with st.expander("Importancia por permutación (contraste robusto)"):
        ui.fmt_table(explain.permutation(fit.pipeline, X, y).set_index("Variable"))

with t3:
    rows = [i for i in sh.values.index if i[0] == NARINO]
    if not rows:
        st.info("Nariño no está entre las observaciones explicadas con casos completos.")
    else:
        row = st.selectbox("Año", rows, index=len(rows) - 1, format_func=lambda i: str(i[2]))
        st.markdown(explain.narrative(sh, row))
        st.plotly_chart(charts.shap_waterfall(sh, row), width="stretch")
        st.session_state["ml_last"] = {"fit": fit, "row": row}
