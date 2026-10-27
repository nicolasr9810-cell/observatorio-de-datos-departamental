# Integraciones pendientes

Solo se activan fuentes con territorio, periodo, unidad y metodología verificables. No completar huecos con datos de ejemplo ni con indicadores de nombre parecido.

| Dimensión | Fuente a integrar | Trabajo pendiente |
|---|---|---|
| Mercado laboral: desempleo, ocupación e informalidad | [DANE, histórico por departamentos](https://www.dane.gov.co/index.php/estadisticas-por-tema/mercado-laboral/mercado-laboral-por-departamentos/mercado-laboral-por-departamento-historicos) | Leer anexos GEIH y respetar cobertura territorial y notas de comparabilidad. |
| Competitividad: IDC | [Consejo Privado de Competitividad](https://compite.com.co/) | Conectar base departamental anual de puntajes, pilares y posiciones. No confundir IDC con IDIC. |
| Educación: Saber 11 | [ICFES y datos.gov.co](https://www.datos.gov.co/) | Definir agregación departamental y ponderación válida desde resultados publicados. |
| Salud | [DANE](https://www.dane.gov.co/index.php/estadisticas-por-tema/salud) y [MinSalud](https://www.minsalud.gov.co/) | Integrar esperanza de vida, mortalidad infantil y capacidad hospitalaria con denominadores revisados. |
| Ambiente: deforestación | [IDEAM, monitoreo de bosques](https://www.datos.gov.co/Ambiente-y-Desarrollo-Sostenible/Monitoreo-de-bosques/pb29-gexz) | Confirmar campos, periodo y geografía antes de graficar. |
| CTeI: inversión en I+D | [MinCiencias](https://minciencias.gov.co/ciudadano/datosabiertos) | Falta un valor monetario departamental anual homogéneo; el conteo de grupos integrado es una medida distinta. |

## Contrato del conector

Cada módulo nuevo debe entregar departamento, código DIVIPOLA, año, indicador, categoría, valor, unidad, fuente y URL. Debe detenerse con un error técnico y recomendación si falla la descarga o el esquema. Tasas solo se calculan cuando numerador y denominador son compatibles para el mismo territorio y periodo.
