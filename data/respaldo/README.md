# Respaldos locales DANE

Los CSV de esta carpeta son copias estáticas de fuentes oficiales, descargadas el 3 de noviembre de 2026. La app los lee únicamente si fallan la fuente primaria y el espejo oficial.

| Archivo | Contenido | Fuente de origen |
|---|---|---|
| `dane_pobreza_departamental_2012_2020.csv` | Incidencia de pobreza por departamento y año, solo registros publicados por DANE | [Servicio DANE Geoportal 2012-2020](https://geoportal.dane.gov.co/mparcgis/rest/services/INDICADORES_COND_DE_VIDA/Serv_Deptos_Pobreza_2012_2020/MapServer) consultado desde su espejo oficial PortalGIS |
| `dane_gini_departamental_2012_2020.csv` | Coeficiente de Gini por departamento y año, solo registros publicados por DANE | [Servicio DANE Geoportal 2012-2020](https://geoportal.dane.gov.co/mparcgis/rest/services/INDICADORES_COND_DE_VIDA/Serv_Deptos_CoeficienteGini_2012_2020/MapServer) consultado desde su espejo oficial PortalGIS |
| `dane_poblacion_departamental_2018_2050.csv` | Proyecciones de población, área geográfica `Total`, departamento/año | [Anexo departamental de proyecciones DANE](https://www.dane.gov.co/files/censo2018/proyecciones-de-poblacion/Departamental/PPED-AreaDep-2018-2050_VP.xlsx) |

Las filas que no publica la fuente permanecen ausentes. No se imputaron valores. La capa histórica de pobreza no trae valor para todos los años (por ejemplo, no aparece `IP_AM_2019`); el CSV conserva ese faltante.

## Renovación manual

1. Consulta la página oficial o el servicio enlazado y descarga la versión vigente.
2. Normaliza la tabla al esquema que espera la app: `departamento,codigo_divipola,anio,indicador,categoria,valor,unidad,fuente,fuente_url` para pobreza/Gini y `departamento,codigo_divipola,anio,valor` para población.
3. Reemplaza el CSV correspondiente y confirma que códigos/años no se duplicaron y que valores y unidades coinciden con el anexo oficial.
4. Actualiza la fecha de descarga en este archivo y en `README.md`, luego sube los cambios a GitHub.

DANE publica además un anexo departamental de pobreza monetaria y Gini para 2021-2025 en su [página de publicaciones de pobreza monetaria](https://www.dane.gov.co/index.php/estadisticas-por-tema/pobreza-y-condiciones-de-vida/pobreza-monetaria). Es una publicación más reciente y debe conservarse como serie/corte identificado; esta app no la concatena automáticamente con la capa 2012-2020.
