# -*- coding: utf-8 -*-
"""Constantes globales: endpoints, DIVIPOLA y parámetros de red."""
from __future__ import annotations

TIMEOUT = (15, 90)
LIMIT = 50000
HEADERS = {"User-Agent": "ObservatorioColombia/1.0 (datos abiertos)"}
SODA = "https://www.datos.gov.co/resource"
POP_XLSX = "https://www.dane.gov.co/files/censo2018/proyecciones-de-poblacion/Departamental/PPED-AreaDep-2018-2050_VP.xlsx"
POVERTY = "https://geoportal.dane.gov.co/mparcgis/rest/services/INDICADORES_COND_DE_VIDA/Serv_Deptos_Pobreza_2012_2020/MapServer/2/query"
GINI = "https://geoportal.dane.gov.co/mparcgis/rest/services/INDICADORES_COND_DE_VIDA/Serv_Deptos_CoeficienteGini_2012_2020/MapServer/2/query"

DIVIPOLA = {
    "05":"Antioquia","08":"Atlántico","11":"Bogotá D.C.","13":"Bolívar",
    "15":"Boyacá","17":"Caldas","18":"Caquetá","19":"Cauca","20":"Cesar",
    "23":"Córdoba","25":"Cundinamarca","27":"Chocó","41":"Huila",
    "44":"La Guajira","47":"Magdalena","50":"Meta","52":"Nariño",
    "54":"Norte de Santander","63":"Quindío","66":"Risaralda","68":"Santander",
    "70":"Sucre","73":"Tolima","76":"Valle del Cauca","81":"Arauca",
    "85":"Casanare","86":"Putumayo","88":"San Andrés y Providencia",
    "91":"Amazonas","94":"Guainía","95":"Guaviare","97":"Vaupés","99":"Vichada",
}
CODE = {name: key for key, name in DIVIPOLA.items()}
ALIASES = {
    "bogota":"Bogotá D.C.","bogota dc":"Bogotá D.C.","bogota d c":"Bogotá D.C.",
    "bogota distrito capital":"Bogotá D.C.","distrito capital":"Bogotá D.C.",
    "san andres":"San Andrés y Providencia",
    "san andres y providencia":"San Andrés y Providencia",
    "archipielago de san andres":"San Andrés y Providencia",
    "archipielago de san andres providencia y santa catalina":"San Andrés y Providencia",
    "valle":"Valle del Cauca",
}

# Límites administrativos DANE MGN, servidos por el espejo ArcGIS Colombia.
# Esta capa evita depender del host del Geoportal que puede no responder desde Streamlit Cloud.
GEO_QUERY = (
    "https://ags.esri.co/arcgis/rest/services/DatosAbiertos/MGN_Departamentos/"
    "MapServer/0/query"
)
GEO_QUERY_FALLBACK = (
    "https://geoportal.dane.gov.co/mparcgis/rest/services/INDICADORES_COND_DE_VIDA/"
    "Serv_Deptos_Pobreza_2012_2020/MapServer/1/query"
)
GEO_CACHE_VERSION = "dane-mgn-esri-mirror-v2"
GEO_LOCAL = "data/departamentos.geojson"   # opcional: MGN DANE descargado a mano
NARINO = "52"
