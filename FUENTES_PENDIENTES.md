# Cobertura pendiente

## Ya integrados

| Dimensión | Indicador | Cobertura y limitación |
|---|---|---|
| Mercado laboral | Tasa de desempleo DANE-GEIH | Serie 2007–2025 para 23 departamentos; quiebre metodológico desde 2021. |
| Finanzas públicas | IDF DNP | Resultados 2023–2024 desde anexos oficiales. Metodología distinta en 2024; valor de 2024 redondeado a un decimal. |
| Ambiente | Tasa IDEAM, pérdida anual promedio y superficie de bosque natural | Datos departamentales; la tasa conserva el signo IDEAM y los periodos se grafican por año final. |
| Cambio climático | Vulnerabilidad IDEAM TCNCC | Corte 2017, agregado ponderado por área municipal; no representa riesgo actual ni tendencia. |
| Clima | Anomalía de temperatura e índice anual de precipitación en estaciones IDEAM | La temperatura es anomalía; la precipitación es un índice en su escala oficial, no una anomalía. Promedio de estaciones: 28 departamentos para temperatura y 32 para precipitación; no es promedio espacial. La anomalía pluviométrica comparable queda pendiente.

## Requieren un insumo o una metodología adicional

| Dimensión | Fuente oficial a priorizar | Trabajo pendiente |
|---|---|---|
| Mercado laboral: informalidad | [DANE, empleo informal histórico](https://www.dane.gov.co/index.php/estadisticas-por-tema/mercado-laboral/empleo-informal-y-seguridad-social/empleo-informal-y-seguridad-social-historicos) | La publicación presenta total nacional, 13/23 ciudades y centros poblados/rural disperso, no departamentos. Estimar con microdatos GEIH, factores de expansión y errores de muestreo o esperar un anexo departamental. No usar la cifra de Pasto como si representara Nariño. |
| Brecha salarial de género | [Nota DANE 2022](https://www.dane.gov.co/files/investigaciones/notas-estadisticas/dic-brecha-salarail-genero-2022-v3.pdf) | La nota usa GEIH y RELAB con resultados nacionales y por 23 ciudades, no una serie departamental anual completa. Definir universo y medida (bruta/ajustada; ingreso mensual/horario) antes de estimar con ponderadores. |
| Densidad y dinámica empresarial | [DANE, REE](https://www.dane.gov.co/index.php/servicios-al-ciudadano/servicios-informacion/registro-estadistico-de-empresas/directorio-estadistico-de-empresas) | Hay geovisores y publicaciones de dinámica 2018–2020 / REE 2022–2024; falta validar un archivo abierto, estable y homogéneo con tablas departamentales anuales de activas, nacimientos y cierres. Definir universo y denominador por 1.000 habitantes. |
| Competitividad | [Consejo Privado de Competitividad](https://compite.com.co/) | Integrar el IDC departamental anual con pilares y posiciones. No confundirlo con el IDIC. |
| Educación | [ICFES y datos.gov.co](https://www.datos.gov.co/) | Definir agregación y ponderación válidas para resultados departamentales Saber 11. |
| Salud | [DANE](https://www.dane.gov.co/index.php/estadisticas-por-tema/salud) y [MinSalud](https://www.minsalud.gov.co/) | Integrar esperanza de vida, mortalidad infantil y capacidad hospitalaria con denominadores y vigencias comparables. |
| Riesgo climático | [IDEAM, TCNCC 2017](https://visualizador.ideam.gov.co/CatalogoObjetos/catalog/viewObjectIndex/17330947) | Encontrar un índice departamental actualizado que integre amenaza, exposición y vulnerabilidad. La capa integrada solo es vulnerabilidad de 2017. |
| CTeI: inversión en I+D | [MinCiencias, datos abiertos](https://minciencias.gov.co/ciudadano/datosabiertos) | Encontrar valor monetario anual por departamento. El conteo de grupos de investigación ya integrado mide capacidad, no gasto en I+D. |

La evaluación completa de fuentes, coberturas y decisiones está en [VIABILIDAD_NUEVAS_VARIABLES.md](VIABILIDAD_NUEVAS_VARIABLES.md).

## Contrato de integración

Todo conector entrega `departamento,codigo_divipola,anio,indicador,categoria,valor,unidad,fuente,fuente_url`. Si una fuente no responde o cambia de esquema, el indicador intenta usar un snapshot oficial local si existe y registra el estado en **Datos y calidad**. Si no hay respaldo válido, se marca como no disponible. No se inventan valores, no se sustituyen departamentos por ciudades y las tasas solo se calculan con denominadores compatibles.
