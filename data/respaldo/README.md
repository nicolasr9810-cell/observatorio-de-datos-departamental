# Snapshots y cruces oficiales

Estos archivos contienen observaciones reales publicadas por las fuentes oficiales enlazadas. No hay registros sintéticos ni imputaciones. Las copias de respaldo se consultan cuando falla la fuente en vivo; el IDF se carga directamente desde documentos oficiales estáticos porque el visor del DNP no ofrece un endpoint tabular estable.

## Indicadores

| Archivo | Contenido | Fuente de origen y cobertura |
|---|---|---|
| `dane_pobreza_departamental_2012_2020.csv` | Incidencia de pobreza monetaria por departamento y año | [DANE Geoportal 2012–2020](https://geoportal.dane.gov.co/mparcgis/rest/services/INDICADORES_COND_DE_VIDA/Serv_Deptos_Pobreza_2012_2020/MapServer), consultado desde PortalGIS. |
| `dane_gini_departamental_2012_2020.csv` | Coeficiente Gini por departamento y año | [DANE Geoportal 2012–2020](https://geoportal.dane.gov.co/mparcgis/rest/services/INDICADORES_COND_DE_VIDA/Serv_Deptos_CoeficienteGini_2012_2020/MapServer), consultado desde PortalGIS. |
| `dane_poblacion_departamental_2018_2050.csv` | Proyecciones DANE, área geográfica Total | [Anexo departamental DANE](https://www.dane.gov.co/files/censo2018/proyecciones-de-poblacion/Departamental/PPED-AreaDep-2018-2050_VP.xlsx). |
| `dane_desempleo_departamental_2007_2025.csv` | Tasa anual de desempleo (TD), 23 departamentos principales | [Anexo GEIH departamental 2025](https://www.dane.gov.co/files/operaciones/GEIH/anex-GEIHDepartamentos-2025.xls), hoja `Departamentos anual`. Descarga 2026-11-03; cambio metodológico desde 2021. |
| `dnp_idf_departamental_2023_2024.csv` | Puntaje IDF departamental: 2023 exacto desde anexo; 2024 a un decimal | [XLSX DNP 2023](https://colaboracion.dnp.gov.co/CDT/Desarrollo%20Territorial/Desempeno_Fiscal/ResultadosIDF_Nueva_MetodologIa_2023_Act.xlsx) y [PDF DNP 2024](https://colaboracion.dnp.gov.co/CDT/Desarrollo%20Territorial/CIFFIT_DocumentosPublicacion/Presentacion_IDF_Departamentos_2024.pdf). Descarga/transcripción 2026-11-03. Hay cambio de metodología en 2024. |
| `ideam_bosques_departamental.csv` | Superficie observada de bosque natural, tasa anual de deforestación y deforestación media anual | [IDEAM Indicadores, tablas 50 y 56](https://visualizador.ideam.gov.co/gisserver/rest/services/Indicadores/INDICADORES_DATOS/MapServer). Descarga 2026-11-03; serie departamental completa disponible hasta 2024. El [resumen nacional 2025](https://ideam.gov.co/sala-de-prensa/informes/publicacion-vie-31072026-1200) no presenta cifra de Nariño ni tabla departamental completa. Las medidas de tasa y hectáreas por año conservan periodos anuales desde 2012–2013; el eje usa el año final. |
| `ideam_vulnerabilidad_cc_departamental_2017.csv` | Promedio departamental ponderado por área de la vulnerabilidad municipal IDEAM 2017 | [Capa IDEAM TCNCC 2017](https://visualizador.ideam.gov.co/CatalogoObjetos/catalog/viewObjectIndex/17330947), descarga 2026-11-03. No es riesgo climático ni serie temporal; cobertura: 31 departamentos. |
| `ideam_anomalias_climaticas_departamental_estaciones_2000_2025.csv` | Anomalía anual de temperatura e índice anual de precipitación (este último no es una anomalía), promediados entre estaciones de referencia por departamento | [IDEAM tablas 39 y 40](https://visualizador.ideam.gov.co/gisserver/rest/services/Indicadores/INDICADORES_DATOS/MapServer). Descarga 2026-11-03. Cobertura: 28 departamentos para temperatura y 32 para precipitación; el agregado no es espacial. |
| `ideam_cruce_municipio_estacion_departamento.csv` | Cruce de municipios de estaciones IDEAM a DIVIPOLA departamental | [Catálogo Nacional de Estaciones IDEAM en datos.gov.co](https://www.datos.gov.co/resource/hp9r-jxuu.json) + municipio informado en las tablas IDEAM. Es una tabla de correspondencia geográfica, no un indicador. |

## Esquemas

Los snapshots de indicadores tienen como mínimo `departamento,codigo_divipola,anio,valor`. Los archivos multindicador añaden `indicador`; el de anomalías puede añadir `n_estaciones`. El cruce usa `municipio_key,codigo_divipola`. Los conectores reducen los archivos a las columnas del contrato común antes de incorporarlos al panel.

## Renovación

1. Descarga la nueva versión desde el enlace oficial indicado en la tabla.
2. Actualiza el CSV sin alterar valores originales; convierte únicamente la estructura, los códigos DIVIPOLA y la vigencia al esquema descrito arriba.
3. Revisa duplicados por indicador, código y año; verifica los faltantes y anota cualquier cambio de metodología o cobertura.
4. Cambia la fecha de snapshot y sus notas en este archivo y en `VIABILIDAD_NUEVAS_VARIABLES.md`.
5. Sube el CSV y la documentación actualizada al mismo commit de GitHub.

Las filas no publicadas permanecen ausentes. No extrapoles los snapshots a vigencias futuras ni sustituyas la observación departamental por datos de una ciudad.
