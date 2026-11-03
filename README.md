# Observatorio Socioeconómico y de Competitividad de Colombia
## Énfasis analítico en Nariño

Aplicación en Streamlit y Plotly. Consume fuentes oficiales en vivo cuando existe un endpoint estable y usa snapshots oficiales versionados cuando una consulta falla o solo existe un documento estático. No usa filas sintéticas ni rellena ausentes con cero. Una fuente fallida no bloquea los indicadores independientes.

## Estructura (v2, modular)

- `app.py`: solo navegación (`st.navigation`). Cada módulo es una vista en `views/`.
- `observatorio/`: paquete importable con conectores (`data/`), contrato y utilidades (`core/`), modelos (`analytics/`), figuras (`viz/`) y caché/UI (`ui/`).
- `ROADMAP.md`: arquitectura, fases de integración y flujo Colab ↔ app.
- `tests/`: pruebas con `pytest`. Los datos de prueba existen solo ahí.
- `requirements.txt`: dependencias de producción (Streamlit Cloud). `requirements-dev.txt` agrega pytest.
- `colab_celdas.txt`: clona el repositorio en Colab, importa el paquete y abre el túnel.
- `FUENTES_PENDIENTES.md`: cobertura pendiente y contratos de integración.
- `VIABILIDAD_NUEVAS_VARIABLES.md`: evaluación de fuentes, alcance y límites de los nuevos indicadores.
- `data/respaldo/`: snapshots oficiales y cruces geográficos usados como respaldo.

## Módulos analíticos

| Vista | Métodos |
|---|---|
| Panorama | KPIs de Nariño, tendencias, ranking, dispersión, mapa coroplético |
| Análisis exploratorio | Perfil, normalidad, atípicos, correlaciones con p-valor, VIF, hallazgos automáticos |
| Machine Learning + SHAP | Ridge, Lasso, SVR (SVM), red neuronal MLP; validación por departamento o temporal; SHAP |
| PCA y tipologías | PCA, índice sintético 0–100, K-means por silueta, mapas |
| VAR y VECM | ADF/KPSS, Johansen, VAR/VECM, Granger, impulso-respuesta, pronóstico |
| Econometría espacial | W reina/KNN, Moran global, LISA, OLS → SAR/SEM con pruebas LM, impactos directos/indirectos |
| Simulación de políticas | Derrames SAR, choques VAR/VECM, contrafactual ML |

Todos los modelos usan casos completos y reportan cuántas filas descartaron. Cuando no hay observaciones suficientes, la vista muestra un aviso y no estima.

## Indicadores incluidos

| Dimensión | Indicadores | Fuente |
|---|---|---|
| Economía y crecimiento | PIB departamental a precios constantes de 2015 y PIB por habitante | [PIB departamental en datos.gov.co](https://www.datos.gov.co/Econom-a-y-Finanzas/PIB-Departamental-con-proyecci-n/kgyi-qc7j) |
| Seguridad | Homicidios y tasa por 100.000 habitantes | [Ministerio de Defensa](https://www.datos.gov.co/Seguridad-y-Defensa/HOMICIDIO/m8fd-ahd9) + [población DANE](https://www.dane.gov.co/index.php/estadisticas-por-tema/demografia-y-poblacion/proyecciones-de-poblacion) |
| Mercado laboral | Tasa anual de desempleo departamental, GEIH 2007–2025 | [DANE, resultados por departamentos](https://www.dane.gov.co/index.php/estadisticas-por-tema/mercado-laboral/mercado-laboral-por-departamentos) |
| Finanzas públicas | Recursos obligados por habitante e Índice de Desempeño Fiscal (IDF), 2023–2024 | [DNP-RecursosEntidad](https://www.datos.gov.co/resource/wc86-9j4a.json), [anexo IDF 2023](https://colaboracion.dnp.gov.co/CDT/Desarrollo%20Territorial/Desempeno_Fiscal/ResultadosIDF_Nueva_MetodologIa_2023_Act.xlsx) y [IDF 2024](https://www.dnp.gov.co/Prensa_/Noticias/Paginas/dnp-presenta-resultados-indice-desempeno-fiscal-departamentos-2024.aspx) |
| Ciencia, tecnología e innovación | Grupos de investigación reconocidos por convocatoria | [MinCiencias](https://www.datos.gov.co/Ciencia-Tecnolog-a-e-Innovaci-n/Grupos-de-Investigaci-n-Reconocidos/hrhc-c4wu) |
| Pobreza y desigualdad | Incidencia de pobreza monetaria y coeficiente Gini, 2012–2020 | [DANE pobreza](https://geoportal.dane.gov.co/mparcgis/rest/services/INDICADORES_COND_DE_VIDA/Serv_Deptos_Pobreza_2012_2020/MapServer) y [DANE Gini](https://geoportal.dane.gov.co/mparcgis/rest/services/INDICADORES_COND_DE_VIDA/Serv_Deptos_CoeficienteGini_2012_2020/MapServer) |
| Educación | Cobertura neta, cobertura bruta y deserción | [MEN por departamento](https://www.datos.gov.co/d/ji8i-4anb) |
| Medio ambiente | Tasa anual de deforestación, pérdida promedio anual y superficie de bosque natural | [IDEAM, tablas por departamento](https://visualizador.ideam.gov.co/gisserver/rest/services/Indicadores/INDICADORES_DATOS/MapServer). Serie departamental completa hasta 2024; el [resumen nacional 2025](https://ideam.gov.co/sala-de-prensa/informes/publicacion-vie-31072026-1200) no contiene cifra de Nariño ni tabla departamental completa. |
| Cambio climático | Vulnerabilidad TCNCC 2017 ponderada por área municipal | [Capa oficial IDEAM 2017](https://visualizador.ideam.gov.co/CatalogoObjetos/catalog/viewObjectIndex/17330947) |
| Clima | Anomalía media anual de temperatura e índice anual de precipitación de estaciones IDEAM | [IDEAM, estaciones de referencia](https://visualizador.ideam.gov.co/gisserver/rest/services/Indicadores/INDICADORES_DATOS/MapServer). El índice de precipitación no es una anomalía; la anomalía pluviométrica comparable queda pendiente. |

El PIB integrado proviene de un conjunto publicado por la Gobernación de Caldas en datos.gov.co, no de una API directa del DANE. Los grupos de investigación reconocidos miden capacidad científica; no equivalen a gasto en I+D. La tasa de homicidios, PIB por habitante y recursos por habitante usan población DANE del mismo año.

## Preprocesamiento

1. Normaliza nombres de departamentos y asigna códigos DIVIPOLA, incluidas variantes con tildes y caracteres dañados por la codificación de fuentes antiguas.
2. Homologa periodos a año entero.
3. Integra tablas por código DIVIPOLA y año cuando ambas fuentes tienen esas llaves.
4. Calcula tasas y valores por habitante solo con denominador de población disponible para el mismo año.
5. Conserva faltantes como nulos y muestra filas descartadas en el control de calidad.
6. Mapea estaciones climáticas a departamento mediante el municipio y un cruce versionado; promedia las estaciones disponibles de forma simple. Ese promedio no es espacial.
7. Agrega el índice de vulnerabilidad 2017 con ponderación por área municipal, no por población.
8. No imputa, extrapola ni convierte faltantes en cero.

El KPI de IDF 2024 usa el promedio nacional publicado por DNP (53,46). Cuando una fuente no publica un dato nacional integrado, el KPI compara Nariño con la media simple de los otros departamentos disponibles y lo identifica; no es un agregado ponderado nacional.

## Dimensiones todavía no conectadas

La app marca como pendientes informalidad laboral, brecha salarial de género, densidad y dinámica empresarial, anomalía de precipitación comparable, IDC, resultados Saber 11, salud, riesgo climático actual e inversión monetaria en I+D. La cobertura pendiente está dentro de la app y en `FUENTES_PENDIENTES.md`. No se muestran proxies como si fueran el indicador solicitado.

## Ejecutar localmente

Desde la carpeta con app.py:

    python -m pip install -r requirements.txt
    streamlit run app.py

La dirección local por defecto es http://localhost:8501.

## Streamlit Community Cloud

Sube el repositorio completo a GitHub, incluida la carpeta `data/respaldo/`, `requirements.txt`, `FUENTES_PENDIENTES.md` y `VIABILIDAD_NUEVAS_VARIABLES.md`. Crea una app de Streamlit Community Cloud que apunte a `app.py`.

## Pruebas

    python -m pip install -r requirements-dev.txt
    python -m pytest -q

## Google Colab

Sigue colab_celdas.txt. El túnel de prueba usa pyngrok y requiere un token propio guardado en Colab Secrets con el nombre NGROK_AUTHTOKEN. No publiques el token en una celda ni en el repositorio.

## Snapshots oficiales y respaldo sin conexión

La app consulta primero en vivo población DANE, pobreza, Gini, GEIH desempleo, indicadores IDEAM de bosque, anomalía de temperatura, índice de precipitación y vulnerabilidad. Pobreza y Gini prueban Geoportal y PortalGIS; otros conectores usan sus CSV oficiales de `data/respaldo/` cuando la descarga, lectura o validación falla. El IDF se toma de copias locales de anexos oficiales DNP porque el visor no ofrece una consulta tabular estable. La vista **Datos y calidad** muestra `En vivo`, `Espejo oficial`, `Respaldo local`, `Snapshot oficial local` o `No disponible`.

Los snapshots se descargaron el 3 de noviembre de 2026 y no se actualizan solos. Revisa `data/respaldo/README.md` y `VIABILIDAD_NUEVAS_VARIABLES.md` al renovar los CSV. La GEIH tiene quiebre metodológico desde 2021; el IDF cambia metodología en 2024; la vulnerabilidad climática es un único corte 2017; los indicadores de clima son promedios de estaciones de referencia; la precipitación es un índice, no una anomalía.

## Disponibilidad de fuentes

Una caída HTTP, respuesta vacía o cambio de esquema se registra en **Datos y calidad** y no bloquea las demás fuentes independientes. Los indicadores que dependen de población DANE se omiten si esa base no está disponible. La interfaz permite reintentar la carga; el detalle técnico queda en los logs de la aplicación.
