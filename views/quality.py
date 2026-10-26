# -*- coding: utf-8 -*-
"""Vista 8 · Datos, calidad y fuentes pendientes."""
import pandas as pd
import streamlit as st

from observatorio.ui import components as ui, state

master, quality = state.master()
ui.header("🧾 Datos y calidad", "Trazabilidad de cada fuente: filas leídas, descartadas y válidas. Sin imputación.")
st.dataframe(quality, width="stretch", hide_index=True)
st.subheader("Contrato largo (master)")
st.dataframe(master, width="stretch", hide_index=True)
ui.download(master.set_index("codigo_divipola"), "observatorio_master")
st.subheader("Integraciones pendientes")
st.markdown(open("FUENTES_PENDIENTES.md", encoding="utf-8").read().split("## Contrato")[0])
st.caption(f"{master.indicador.nunique()} indicadores · {len(master):,} registros · "
           f"{pd.Timestamp.now(tz='America/Bogota'):%Y-%m-%d %H:%M} (caché 6 h)")
