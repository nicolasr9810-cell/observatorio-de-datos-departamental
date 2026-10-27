# Observatorio Socioeconómico y de Competitividad de Colombia
## Énfasis analítico en Nariño

Aplicación en Streamlit y Plotly. Las fuentes activas se consultan en vivo. No usa filas sintéticas ni rellena ausentes con cero. Si una fuente falla, conserva los indicadores disponibles y reporta los que faltan; los indicadores que dependen de población se omiten si esa base no responde.

## Estructura (v2, modular)

- `app.py`: solo navegación (`st.navigation`). Cada módulo es una vista en `views/`.
- `observatorio/`: paquete importable con conectores (`data/`), contrato y utilidades (`core/`), modelos (`analytics/`), figuras (`viz/`) y caché/UI (`ui/`).
- `ROADMAP.md`: arquitectura, fases de integración y flujo Colab ↔ app.
- `tests/`: pruebas con `pytest`. Los datos de prueba existen solo ahí.
- `requirements.txt`: dependencias de producción (Streamlit Cloud). `requirements-dev.txt` agrega pytest.
- `colab_celdas.txt`: clona el repositorio en Colab, importa el paquete y abre el túnel.
- `FUENTES_PENDIENTES.md`: cobertura pendiente y contratos de integración.

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
| Finanzas públicas | Recursos obligados DNP y recursos por habitante | [DNP-RecursosEntidad](https://www.datos.gov.co/resource/wc86-9j4a.json) |
| Ciencia, tecnología e innovación | Grupos de investigación reconocidos por convocatoria | [MinCiencias](https://www.datos.gov.co/Ciencia-Tecnolog-a-e-Innovaci-n/Grupos-de-Investigaci-n-Reconocidos/hrhc-c4wu) |
| Pobreza y desigualdad | Incidencia de pobreza monetaria y coeficiente Gini, 2012–2020 | [DANE pobreza](https://geoportal.dane.gov.co/mparcgis/rest/services/INDICADORES_COND_DE_VIDA/Serv_Deptos_Pobreza_2012_2020/MapServer) y [DANE Gini](https://geoportal.dane.gov.co/mparcgis/rest/services/INDICADORES_COND_DE_VIDA/Serv_Deptos_CoeficienteGini_2012_2020/MapServer) |
| Educación | Cobertura neta, cobertura bruta y deserción | [MEN por departamento](https://www.datos.gov.co/d/ji8i-4anb) |

El PIB integrado proviene de un conjunto publicado por la Gobernación de Caldas en datos.gov.co, no de una API directa del DANE. Los grupos de investigación reconocidos miden capacidad científica; no equivalen a gasto en I+D. La tasa de homicidios, PIB por habitante y recursos por habitante usan población DANE del mismo año.

## Preprocesamiento

1. Normaliza nombres de departamentos y asigna códigos DIVIPOLA, incluyendo variantes con tildes.
2. Homologa periodos a año entero.
3. Integra tablas por código DIVIPOLA y año cuando ambas fuentes tienen esas llaves.
4. Calcula tasas y valores por habitante solo con denominador de población disponible para el mismo año.
5. Conserva faltantes como nulos y muestra filas descartadas en el control de calidad.
6. No imputa, extrapola ni convierte faltantes en cero.

Cuando una fuente no publica un dato nacional, el KPI usa la media simple de otros departamentos con dato y lo etiqueta así. Esa referencia no es un agregado ponderado por población.

## Dimensiones todavía no conectadas

La app marca como pendientes GEIH departamental, IDC, resultados Saber 11, salud y deforestación. La cobertura pendiente está dentro de la app y en FUENTES_PENDIENTES.md. No se muestran proxies como si fueran el indicador solicitado.

## Ejecutar localmente

Desde la carpeta con app.py:

    python -m pip install -r requirements.txt
    streamlit run app.py

La dirección local por defecto es http://localhost:8501.

## Streamlit Community Cloud

Sube el repositorio completo a GitHub (app.py, views/, observatorio/, requirements.txt, FUENTES_PENDIENTES.md). Crea una app de Streamlit Community Cloud que apunte a app.py.

## Pruebas

    python -m pip install -r requirements-dev.txt
    python -m pytest -q

## Google Colab

Sigue colab_celdas.txt. El túnel de prueba usa pyngrok y requiere un token propio guardado en Colab Secrets con el nombre NGROK_AUTHTOKEN. No publiques el token en una celda ni en el repositorio.

## Disponibilidad de fuentes

Una caída HTTP, respuesta vacía o cambio de esquema se registra en **Datos y calidad** y no bloquea las demás fuentes independientes. Los indicadores que dependen de población DANE se omiten si esa base no está disponible. La interfaz permite reintentar la carga; el detalle técnico queda en los logs de la aplicación.
