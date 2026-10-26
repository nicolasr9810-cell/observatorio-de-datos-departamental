# -*- coding: utf-8 -*-
"""Página de bienvenida y guía de lectura del observatorio."""
import streamlit as st

st.title("🇨🇴 Bienvenido al Observatorio")
st.subheader("Socioeconomía y competitividad de Colombia, con énfasis en Nariño")
st.write(
    "Aquí puedes consultar indicadores públicos, comparar departamentos y explorar "
    "preguntas sobre desarrollo territorial. No necesitas saber econometría para empezar: "
    "cada sección explica qué muestran sus gráficos y cuáles son sus límites."
)

st.page_link("views/panorama.py", label="Explorar indicadores", icon="🔎")

st.markdown("### ¿Por dónde empezar?")
c1, c2, c3 = st.columns(3)
c1.markdown("**1. Elige una pregunta**  \nPor ejemplo: ¿cómo ha cambiado la pobreza en Nariño?")
c2.markdown("**2. Explora los datos**  \nCompara años y departamentos, o descarga la tabla para revisarla.")
c3.markdown("**3. Interpreta con contexto**  \nRevisa las fuentes, la cobertura y las notas antes de sacar conclusiones.")

st.markdown("### Qué encontrarás")
sections = st.columns(3)
sections[0].markdown(
    "**Explorar**  \nIndicadores, mapas, tendencias y comparaciones sencillas. "
    "El análisis exploratorio ayuda a resumir datos y encontrar relaciones que merecen revisión."
)
sections[1].markdown(
    "**Modelación**  \nHerramientas estadísticas para estudiar patrones en varios indicadores, "
    "a través del tiempo o entre departamentos vecinos. Cada resultado incluye una explicación."
)
sections[2].markdown(
    "**Decisión**  \nEscenarios hipotéticos para entender cómo cambiarían los resultados "
    "bajo distintos supuestos. Una simulación no demuestra por sí sola que una política cause ese cambio."
)

with st.expander("Glosario rápido: conceptos que aparecen en el observatorio"):
    st.markdown(
        "- **Indicador:** una medida, como el PIB por habitante o la pobreza monetaria.\n"
        "- **Cobertura:** cuántos departamentos y años tienen un dato disponible. Un espacio vacío "
        "significa que no hay un dato válido; no equivale a cero.\n"
        "- **Relación o correlación:** dos indicadores se mueven de forma parecida. Esto no prueba "
        "que uno cause el otro.\n"
        "- **Modelo:** una herramienta matemática que resume patrones en los datos bajo ciertos supuestos.\n"
        "- **Econometría espacial:** estudia si los resultados de un departamento se relacionan con "
        "los de sus vecinos.\n"
        "- **Escenario de política:** un cálculo hipotético basado en un modelo; sirve para explorar "
        "posibilidades, no reemplaza una evaluación causal."
    )

st.markdown("### Fuentes y cuidado en la interpretación")
st.write(
    "La plataforma integra fuentes públicas y conserva los faltantes como faltantes. "
    "La cobertura cambia según el indicador y el año; por eso cada vista informa qué datos usa "
    "y puede limitar algunos análisis cuando no hay suficientes departamentos comparables."
)

st.markdown("### Creado por")
authors = st.columns(4)
for col, name in zip(authors, [
    "Nicolas Rugeles Padilla",
    "Jennifer Valentina Chicaiza Obando",
    "Andres Rodrigo Meneses Ortega",
    "David Santiago Cabrera Rivera",
]):
    col.markdown(name)
