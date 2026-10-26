# Hoja de ruta técnica · Observatorio v2

Objetivo: pasar de un `app.py` monolítico (654 líneas) a un sistema modular donde los
conectores de datos, los modelos y la interfaz evolucionan por separado, y donde el
mismo código corre en Google Colab y en Streamlit.

Se mantienen las reglas del proyecto: sin datos sintéticos, sin imputación,
fail-fast con la URL y el error técnico, y trazabilidad de las filas descartadas.

---

## 1. Arquitectura modular

```
observatorio/                    ← repositorio
├── app.py                       ← 30 líneas: set_page_config + st.navigation
├── views/                       ← una página por módulo (solo UI)
│   ├── panorama.py              tablero original + mapa coroplético
│   ├── eda.py                   EDA automatizado
│   ├── ml.py                    Ridge · Lasso · SVR · MLP + SHAP
│   ├── pca.py                   PCA, índice sintético, K-means
│   ├── timeseries.py            ADF/KPSS → Johansen → VAR / VECM
│   ├── spatial.py               Moran, LISA, OLS → SAR / SEM
│   ├── simulation.py            simulación de políticas (3 motores)
│   └── quality.py               calidad, contrato y fuentes pendientes
├── observatorio/                ← paquete Python importable (pip install -e .)
│   ├── config.py                URLs, DIVIPOLA, constantes
│   ├── core/                    sin Streamlit
│   │   ├── normalize.py         norm, norm_dept, norm_year, to_number
│   │   ├── http.py              get_json, soda_all, DataSourceError, InsufficientDataError
│   │   ├── schema.py            contrato largo + standardize()
│   │   ├── panel.py             largo → panel / corte / serie (casos completos)
│   │   └── artifacts.py         guardar/cargar modelos entrenados en Colab
│   ├── data/                    sin Streamlit
│   │   ├── loaders.py           conectores activos (migrados tal cual)
│   │   ├── geo.py               polígonos DANE (EPSG:4326)
│   │   └── pipeline.py          load_all()
│   ├── analytics/               sin Streamlit: es lo que importa Colab
│   │   ├── eda.py  ml.py  dimred.py  explain.py
│   │   ├── timeseries.py  spatial.py  policy.py
│   ├── viz/                     figuras Plotly reutilizables
│   │   ├── maps.py              coropletas, LISA, diagrama de Moran
│   │   └── charts.py            SHAP, biplot, IRF, pronóstico, mapas de calor
│   └── ui/                      única capa que importa Streamlit
│       ├── state.py             caché (cache_data / cache_resource) + run() fail-fast
│       └── components.py        selectores, tablas, descargas
├── tests/                       pytest; datos de prueba SOLO aquí
├── artifacts/                   modelos .joblib + metadatos .json
├── data/                        opcional: departamentos.geojson (MGN DANE)
└── notebooks/                   Colab como cliente del paquete
```

**Reglas de dependencia (en un solo sentido):**

```
views  →  ui  →  analytics / viz  →  core / data  →  config
```

- `analytics/` y `core/` nunca importan Streamlit, así que corren igual en Colab, en pytest y en la app.
- Las vistas no implementan modelos: leen widgets, llaman a `analytics` y pintan con `viz`.
- Toda la caché está en `ui/state.py`: `cache_data` para DataFrames y `cache_resource` para modelos ajustados.
  Cambiar un widget no vuelve a entrenar si los datos y los parámetros no cambiaron.
- `state.run()` traduce las excepciones: `DataSourceError` muestra un error y detiene la vista;
  `InsufficientDataError` muestra un aviso cuando hay muy pocos casos completos para estimar.

**El contrato de datos es el eje.** Todo sale del `master` largo
(`departamento, codigo_divipola, anio, indicador, categoria, valor, unidad, fuente, fuente_url`).
`core/panel.py` lo convierte en tres formas:

| Forma | Función | Lo usa |
|---|---|---|
| Panel depto × año | `panel()` | EDA, ML |
| Corte transversal de un año | `cross_section()` | PCA, espacial |
| Serie de un territorio, años consecutivos | `territory_series()` | VAR / VECM |

Un indicador nuevo (por ejemplo GEIH) entra en `loaders.py` cumpliendo el contrato y queda
disponible en todos los módulos sin tocar las vistas.

---

## 2. Integración paso a paso

### Fase 0 · Refactor sin cambios funcionales ✅ (incluido)
1. `app.py` se reparte en `config`, `core` y `data` sin cambiar la lógica de los conectores.
2. El tablero original se trasladó a `views/panorama.py` y ahora tiene una pestaña de mapa.
3. Pruebas: `pytest` (22 pruebas: normalización, cada modelo y cada vista con `AppTest`).

### Fase 1 · EDA y PCA ✅
- `eda.profile`: media, CV, asimetría, curtosis, Shapiro-Wilk, Jarque-Bera y atípicos por IQR.
- `eda.correlations` (Spearman o Pearson, con p-valores), `eda.vif` y hallazgos automáticos en texto.
- `dimred.run_pca`: estandariza, aplica Kaiser, orienta el signo de CP1 y construye un índice 0–100.
  Después K-means con *k* elegido por silueta. Ambos resultados se ven en mapa.

### Fase 2 · Machine Learning + SHAP ✅
1. `ml.supervised_frame(..., lag=1)`: usa X(t−1) para predecir y(t). Es predicción real, no ajuste contemporáneo.
2. El `Pipeline(StandardScaler → modelo)` evita la fuga de información en la validación.
3. Validación **por departamento** (`GroupKFold`: ¿generaliza a un territorio no visto?) o **temporal**.
4. Modelos: `RidgeCV`, `LassoCV` (selección de variables), `SVR` con `GridSearchCV` y `MLPRegressor` (32-16, early stopping).
5. `explain.shap_explain`: `PermutationExplainer` sobre el pipeline completo. Da valores en unidades
   originales de X y es válido para los cuatro modelos. La prueba de aditividad pasa:
   base + ΣSHAP = predicción. Como contraste está la importancia por permutación.

> Con aproximadamente 33 departamentos × 10–15 años, la red neuronal es un modelo de referencia.
> Si no supera a Ridge fuera de muestra, eso es un resultado que vale la pena reportar.
> Para LSTM o deep learning de verdad se necesitan series mensuales (ver Fase 5).

### Fase 3 · Series de tiempo VAR / VECM ✅
```
territory_series(master, vars, "52")        # exige años consecutivos (sin huecos)
  └─ stationarity(): ADF (H0 raíz unitaria) + KPSS (H0 estacionariedad), niveles y Δ
       ├─ todas I(0)  → VAR en niveles
       └─ I(1)        → johansen() traza 5 %
                         ├─ 0 < r < k → VECM(r)          (equilibrio de largo plazo + ajuste α)
                         └─ r = 0     → VAR en diferencias
  └─ Granger, IRF (Cholesky u ordinario), pronóstico con IC 95 %
```
- `max_safe_lags(T, k)` impide sobreparametrizar: exige T − p > k·p + 1.
- Avisos automáticos cuando T < 20, cuando el VAR es inestable o hay variables débilmente exógenas.

### Fase 4 · Econometría espacial ✅
1. `data/geo.py` descarga los polígonos del mismo servicio DANE que ya usa la app
   (`returnGeometry=true`, `f=geojson`, simplificados en el servidor). Si existe `data/departamentos.geojson`
   (MGN), se usa ese archivo.
2. `spatial.build_weights`: W de **reina**, con San Andrés conectado a su vecino más cercano para que no quede aislado,
   o **KNN**, calculado en EPSG:9377 (distancias en metros). W se estandariza por filas.
3. Moran global y LISA con 999 permutaciones. Se muestran en mapa de clústeres y diagrama de Moran.
4. `fit_spatial`: OLS → LM-lag/LM-error (simples y robustos) → **SAR** (`ML_Lag`) o **SEM** (`ML_Error`), según Anselin (2005).
5. En el SAR, los efectos se reportan como **directos, indirectos y totales** (LeSage & Pace),
   porque los β del SAR no son efectos marginales.

### Fase 5 · Simulación de políticas ✅
| Motor | Ecuación | Pregunta que responde |
|---|---|---|
| Espacial (SAR) | Δy = (I − ρW)⁻¹ β Δx | Si Nariño sube X, ¿cuánto cambia y en Nariño y en sus vecinos? (mapa de derrames) |
| VAR / VECM | IRF × tamaño del choque | ¿Cómo se propaga un choque año a año? Escenario = base + desvío |
| ML contrafactual | f(X + ΔX) − f(X) | ¿Cómo responde el modelo si se cambian las palancas? (asociacional) |

Las vistas comparten los modelos ya estimados mediante `st.session_state`, así que simular no obliga a reestimar.

### Fase 6 · Siguientes pasos (pendientes)
1. **Más T para VAR y deep learning:** agregar homicidios mensuales con `date_extract_ym(fecha_hecho)`.
   Eso da unas 200 observaciones por departamento y permite VAR más ricos y LSTM.
2. **GEIH departamental**, siguiendo el contrato de `FUENTES_PENDIENTES.md`, para mercado laboral y la línea TIC-género.
3. **Panel espacial** (SAR con efectos fijos, `spreg.Panel_FE_Lag`) para usar todos los años y no solo un corte.
4. **Panel VAR** (por ejemplo `linearmodels` o una implementación GMM) si se necesita dinámica multirregional.
5. Desplegar en Streamlit Community Cloud y correr `pytest` en GitHub Actions en cada push.

### Conectar Colab ↔ app (flujo recomendado)
1. **El código vive en GitHub**, no en celdas sueltas. Colab hace `git clone` y `pip install -e .`.
2. En Colab se experimenta importando el paquete (`from observatorio.analytics import ml`).
   Cuando una celda funciona, se convierte en función dentro de `analytics/` y se agrega una prueba.
3. Si un modelo es costoso de entrenar (grid grande, muchas épocas), se entrena en Colab y se guarda con
   `core.artifacts.save_model()`, que registra también la huella de los datos. Luego se sube `artifacts/` al repo
   y la app lo carga con `load_model()` dentro de `st.cache_resource`.
4. Antes de cada push, en Colab: `!pytest -q`.

---

## 3. `requirements.txt`
Ver el archivo. Las librerías que se agregan y su propósito:

| Paquete | Uso |
|---|---|
| `statsmodels` | VAR, VECM, Johansen, ADF/KPSS, VIF |
| `scikit-learn` | Ridge, Lasso, SVR, MLP, PCA, K-means, GroupKFold |
| `shap` | Interpretabilidad agnóstica |
| `geopandas`, `shapely`, `pyogrio` | Geometrías y reproyección |
| `libpysal`, `esda`, `spreg` | Pesos W, Moran/LISA, SAR/SEM |
| `scipy`, `joblib` | Pruebas estadísticas y persistencia de modelos |

Se usan los subpaquetes de PySAL (`libpysal`, `esda`, `spreg`) en lugar del metapaquete `pysal`,
que instala unas 20 librerías y hace lento el despliegue en Streamlit Cloud.
No se incluye TensorFlow ni PyTorch: superan el tamaño razonable para Streamlit Cloud y con datos anuales no aportan.
Están como opción en `requirements-dev.txt`.

---

## 4. Fragmentos clave
- Mapa coroplético: `observatorio/viz/maps.py` → `choropleth()`, `lisa_map()`, `moran_scatter()`.
- Interpretabilidad: `observatorio/analytics/explain.py` + `observatorio/viz/charts.py` (`shap_bar`, `shap_beeswarm`, `shap_waterfall`).
- Uso mínimo desde Colab:

```python
from observatorio.data.pipeline import load_all
from observatorio.data.geo import load_departments
from observatorio.core import panel
from observatorio.analytics import ml, explain, spatial
from observatorio.viz import maps, charts

master, quality = load_all()
ind = ["PIB por habitante", "Pobreza monetaria", "Coeficiente de Gini", "Cobertura neta educación"]

# ML + SHAP
m = panel.panel(master, ind)
X, y, g = ml.supervised_frame(m.data, "Pobreza monetaria", [i for i in ind if i != "Pobreza monetaria"], lag=1)
fit = ml.fit_evaluate(X, y, g, "Lasso")
sh = explain.shap_explain(fit.pipeline, X)
charts.shap_beeswarm(sh).show()

# Espacial
cs = panel.cross_section(master, ind, 2018)
gdf = spatial.align(load_departments(), cs.data)
w = spatial.build_weights(gdf)
lisa = spatial.local_moran(gdf["Pobreza monetaria"].to_numpy(), w)
maps.lisa_map(gdf, lisa).show()
```
