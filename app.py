# -*- coding: utf-8 -*-
"""Punto de entrada: solo configuración y navegación. La lógica vive en observatorio/ y views/."""
import logging

import streamlit as st

st.set_page_config(page_title="Observatorio | Nariño", page_icon="🇨🇴", layout="wide")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

pages = {
    "Observatorio": [
        st.Page("views/panorama.py", title="Panorama", icon="🏠", default=True),
        st.Page("views/eda.py", title="Análisis exploratorio", icon="📊"),
    ],
    "Modelación": [
        st.Page("views/ml.py", title="Machine Learning + SHAP", icon="🤖"),
        st.Page("views/pca.py", title="PCA y tipologías", icon="🧭"),
        st.Page("views/timeseries.py", title="VAR y VECM", icon="📈"),
        st.Page("views/spatial.py", title="Econometría espacial", icon="🗺️"),
    ],
    "Decisión": [
        st.Page("views/simulation.py", title="Simulación de políticas", icon="🎛️"),
        st.Page("views/quality.py", title="Datos y calidad", icon="🧾"),
    ],
}
st.navigation(pages).run()
