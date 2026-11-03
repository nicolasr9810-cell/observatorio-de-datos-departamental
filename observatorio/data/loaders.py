# -*- coding: utf-8 -*-
"""Conectores de fuentes activas (migrados sin cambios desde app.py)."""
from __future__ import annotations

import logging
import re
from difflib import SequenceMatcher, get_close_matches
from io import BytesIO

import pandas as pd

from observatorio.config import (DANE_BACKUP_DIR, GINI, GINI_MIRROR, POP_XLSX, POVERTY,
                                 POVERTY_MIRROR, SODA, LIMIT, DIVIPOLA)
from observatorio.core.http import DataSourceError, get_bytes, get_json, soda_all, source_error
from observatorio.core.normalize import norm, norm_dept, norm_year, to_number
from observatorio.core.schema import standardize


def _load_population_live(quality: list) -> pd.DataFrame:
    """Lee el anexo DANE por área geográfica y conserva el renglón Total."""
    source = "DANE - proyecciones departamentales de población"
    content = get_bytes(source, POP_XLSX)
    try:
        sheets = pd.read_excel(BytesIO(content), sheet_name=None, header=None, engine="openpyxl")
    except Exception as exc:
        raise source_error(source, POP_XLSX, exc, "revisa el formato del anexo XLSX.") from exc

    # El anexo vigente tiene una tabla larga:
    # DP, DPNOM, AÑO, ÁREA GEOGRÁFICA, TOTAL.
    for sheet_name, raw in sheets.items():
        for h in range(min(40, len(raw))):
            header = ["" if pd.isna(x) else str(x).strip() for x in raw.iloc[h]]
            labels = [norm(x) for x in header]
            code_i = next((i for i, x in enumerate(labels) if x == "dp"), None)
            dept_i = next((i for i, x in enumerate(labels) if x in {"dpnom", "departamento", "nombre departamento"}), None)
            year_i = next((i for i, x in enumerate(labels) if x in {"ano", "anio", "año"}), None)
            area_i = next((i for i, x in enumerate(labels) if x in {"area geografica", "area"}), None)
            value_i = next((i for i, x in enumerate(labels) if x in {"total", "poblacion total", "poblacion"}), None)
            if None in (code_i, dept_i, year_i, area_i, value_i):
                continue

            data = raw.iloc[h + 1:].copy()
            is_total = data.iloc[:, area_i].astype(str).map(norm).eq("total")
            data = data.loc[is_total]
            rows = []
            miss_value = miss_geo = miss_year = 0
            for _, row in data.iterrows():
                dept, code = norm_dept(row.iloc[dept_i], row.iloc[code_i])
                year = norm_year(row.iloc[year_i])
                value = to_number(pd.Series([row.iloc[value_i]])).iloc[0]
                miss_geo += int(dept is None)
                miss_year += int(year is None)
                miss_value += int(pd.isna(value))
                if dept and year and pd.notna(value):
                    rows.append({
                        "departamento": dept,
                        "codigo_divipola": code,
                        "anio": year,
                        "valor": float(value),
                    })
            pop = pd.DataFrame(rows)
            if pop.empty:
                continue
            duplicate = pop.duplicated(["codigo_divipola", "anio"], keep=False)
            if duplicate.any():
                examples = pop.loc[
                    duplicate, ["departamento", "anio"]
                ].drop_duplicates().head(8).to_dict("records")
                raise source_error(
                    source, POP_XLSX,
                    ValueError(f"duplicados en hoja {sheet_name}: {examples}"),
                    "revisa las filas Total por departamento y año del anexo.",
                )
            quality.append({
                "Indicador": "Población de referencia",
                "Filas fuente": len(data),
                "Nulos de valor descartados": miss_value,
                "Geografía no homologada": miss_geo,
                "Periodo inválido": miss_year,
                "Filas válidas": len(pop),
                "Fuente": f"{source} | hoja {sheet_name} | área Total",
            })
            return pop

    raise source_error(
        source, POP_XLSX,
        ValueError(f"no se reconoció la tabla larga DP/DPNOM/AÑO/ÁREA GEOGRÁFICA/TOTAL; hojas: {list(sheets)}"),
        "revisa encabezados de código, departamento, año, área y población en el anexo DANE.",
    )



def load_population(quality: list) -> pd.DataFrame:
    """Usa el anexo DANE en vivo y recurre al CSV versionado si no responde."""
    source = "DANE - proyecciones departamentales de población"
    try:
        return _load_population_live(quality)
    except Exception as live_exc:
        backup = DANE_BACKUP_DIR / "dane_poblacion_departamental_2018_2050.csv"
        try:
            pop = pd.read_csv(backup, dtype={"codigo_divipola": "string"})
            required = {"departamento", "codigo_divipola", "anio", "valor"}
            if not required.issubset(pop.columns):
                raise ValueError(f"faltan columnas: {sorted(required - set(pop.columns))}")
            geo = [norm_dept(pop.at[i, "departamento"], pop.at[i, "codigo_divipola"])
                   for i in pop.index]
            pop["departamento"] = [item[0] for item in geo]
            pop["codigo_divipola"] = [item[1] for item in geo]
            pop["anio"] = pop["anio"].map(norm_year)
            pop["valor"] = to_number(pop["valor"])
            pop = pop.dropna(subset=["departamento", "codigo_divipola", "anio", "valor"]).copy()
            pop["anio"] = pop["anio"].astype(int)
            if pop.empty:
                raise ValueError("el CSV de respaldo no contiene filas válidas")
            if pop.duplicated(["codigo_divipola", "anio"]).any():
                raise ValueError("el CSV de respaldo contiene duplicados por DIVIPOLA y año")
        except Exception as backup_exc:
            raise source_error(
                source, f"{POP_XLSX} | respaldo local: {backup}",
                ValueError(f"fuente en vivo: {type(live_exc).__name__}: {live_exc}; "
                           f"respaldo: {type(backup_exc).__name__}: {backup_exc}"),
                "verifica la conectividad DANE y que exista un CSV de respaldo válido en data/respaldo.",
            ) from backup_exc
        quality.append({
            "Indicador": "Población de referencia",
            "Estado": "Respaldo local",
            "Filas válidas": len(pop),
            "Fuente": "DANE - proyecciones 2018-2050; copia estática descargada 2026-11-03",
            "Detalle": f"Se usó {backup.name} tras fallar el XLSX en vivo.",
        })
        return pop[["departamento", "codigo_divipola", "anio", "valor"]]


def load_gdp(population: pd.DataFrame, quality: list) -> list[pd.DataFrame]:
    dataset = "kgyi-qc7j"
    source = "datos.gov.co - PIB departamental (publicado por Gobernación de Caldas)"
    url = f"{SODA}/{dataset}.json"
    df = pd.DataFrame(soda_all(
        dataset, source,
        "departamento,c_digo_departamento_divipola,a_o,tipo_de_precios,valor_miles_de_millones_de",
    ))
    df = df[df["tipo_de_precios"].astype(str).map(norm).str.contains("constantes")].copy()
    if df.empty:
        raise source_error(source, url, ValueError("cero filas a precios constantes"),
                           "revisa el diccionario del campo tipo_de_precios.")
    df["valor_miles_de_millones_de"] = to_number(df["valor_miles_de_millones_de"])
    df["a_o"] = df["a_o"].map(norm_year)
    df = df.dropna(subset=["a_o","valor_miles_de_millones_de"])
    df["a_o"] = df["a_o"].astype(int)
    df = df.groupby(["departamento","c_digo_departamento_divipola","a_o"], as_index=False)[
        "valor_miles_de_millones_de"
    ].sum()
    base = standardize(
        df, "departamento","a_o","valor_miles_de_millones_de",
        "PIB departamental","Economía y crecimiento",
        "Miles de millones COP constantes de 2015",source,
        "https://www.datos.gov.co/Econom-a-y-Finanzas/PIB-Departamental-con-proyecci-n/kgyi-qc7j",
        code="c_digo_departamento_divipola", quality=quality,
    )
    pop = population[["codigo_divipola","anio","valor"]].rename(columns={"valor":"poblacion"})
    joined = base.merge(pop, on=["codigo_divipola","anio"])
    if joined.empty:
        raise source_error(source, POP_XLSX, ValueError("sin años DIVIPOLA comunes"),
                           "verifica cobertura temporal y llaves geográficas.")
    joined["valor_calc"] = joined["valor"] * 1_000_000_000 / joined["poblacion"]
    per_capita = standardize(
        joined, "departamento","anio","valor_calc","PIB por habitante",
        "Economía y crecimiento","COP constantes de 2015 por habitante",
        source+" + población DANE",POP_XLSX,code="codigo_divipola",quality=quality,
    )
    return [base, per_capita]


def load_homicides(population: pd.DataFrame, quality: list) -> list[pd.DataFrame]:
    dataset = "m8fd-ahd9"
    source = "datos.gov.co - HOMICIDIO (Ministerio de Defensa Nacional)"
    url = f"{SODA}/{dataset}.json"
    records = get_json(source, url, {
        "$select":"cod_depto,departamento,date_extract_y(fecha_hecho) as anio,sum(cantidad) as valor",
        "$group":"cod_depto,departamento,date_extract_y(fecha_hecho)",
        "$limit":LIMIT,
    })
    if not isinstance(records,list) or not records:
        raise source_error(source,url,ValueError("agregación SODA sin filas"),
                           "revisa fecha_hecho, cantidad y cod_depto.")
    base = standardize(
        pd.DataFrame(records),"departamento","anio","valor",
        "Homicidios (víctimas)","Seguridad ciudadana","Víctimas",source,
        "https://www.datos.gov.co/Seguridad-y-Defensa/HOMICIDIO/m8fd-ahd9",
        code="cod_depto",quality=quality,
    )
    pop = population[["codigo_divipola","anio","valor"]].rename(columns={"valor":"poblacion"})
    joined = base.merge(pop,on=["codigo_divipola","anio"])
    if joined.empty:
        raise source_error(source,POP_XLSX,ValueError("sin años DIVIPOLA comunes"),
                           "verifica proyecciones de población y códigos DIVIPOLA.")
    joined["valor_calc"] = joined["valor"] / joined["poblacion"] * 100000
    rate = standardize(
        joined,"departamento","anio","valor_calc","Homicidios por 100.000 habitantes",
        "Seguridad ciudadana","Víctimas por 100.000 habitantes",
        source+" + población DANE",POP_XLSX,code="codigo_divipola",quality=quality,
    )
    return [base,rate]


def load_finance(population: pd.DataFrame, quality: list) -> list[pd.DataFrame]:
    dataset = "wc86-9j4a"
    source = "datos.gov.co - DNP-RecursosEntidad"
    url = f"{SODA}/{dataset}.json"
    df = pd.DataFrame(soda_all(dataset,source,"departamento,vigencia,valorobligado"))
    df["anio"] = df["vigencia"].map(norm_year)
    df["valor"] = to_number(df["valorobligado"])
    df = df.dropna(subset=["anio","valor","departamento"])
    df["anio"] = df["anio"].astype(int)
    df = df.groupby(["departamento","anio"],as_index=False)["valor"].sum()
    base = standardize(
        df,"departamento","anio","valor","Recursos obligados reportados por DNP",
        "Finanzas públicas","Unidades monetarias reportadas por la fuente",
        source,url,quality=quality,
    )
    pop = population[["codigo_divipola","anio","valor"]].rename(columns={"valor":"poblacion"})
    joined = base.merge(pop,on=["codigo_divipola","anio"])
    if joined.empty:
        raise source_error(source,POP_XLSX,ValueError("sin años DIVIPOLA comunes"),
                           "confirma vigencia anual y código departamental en ambas fuentes.")
    joined["valor_calc"] = joined["valor"] / joined["poblacion"]
    per_capita = standardize(
        joined,"departamento","anio","valor_calc","Recursos DNP obligados por habitante",
        "Finanzas públicas","Unidades monetarias de la fuente por habitante",
        source+" + población DANE",POP_XLSX,code="codigo_divipola",quality=quality,
    )
    return [base,per_capita]


def load_poverty_gini(quality: list) -> list[pd.DataFrame]:
    specs = [
        (POVERTY, POVERTY_MIRROR, "DANE - incidencia de pobreza monetaria",
         r"^IP_AM_(\d{4})$", "Pobreza monetaria", "Porcentaje",
         "https://geoportal.dane.gov.co/mparcgis/rest/services/INDICADORES_COND_DE_VIDA/Serv_Deptos_Pobreza_2012_2020/MapServer",
         "dane_pobreza_departamental_2012_2020.csv"),
        (GINI, GINI_MIRROR, "DANE - coeficiente de Gini",
         r"^GINI_(\d{4})$", "Coeficiente de Gini", "Coeficiente (0 a 1)",
         "https://geoportal.dane.gov.co/mparcgis/rest/services/INDICADORES_COND_DE_VIDA/Serv_Deptos_CoeficienteGini_2012_2020/MapServer",
         "dane_gini_departamental_2012_2020.csv"),
    ]
    result = []
    for endpoint, mirror, source, pattern, indicator, unit, public_url, backup_name in specs:
        frame = None
        failures = []
        transport_failures = 0
        schema_failures = 0
        candidates = [
            (endpoint, public_url, source, "En vivo"),
            (mirror, public_url.replace("https://geoportal.dane.gov.co", "https://portalgis.dane.gov.co"),
             "DANE PortalGIS (espejo oficial)", "Espejo oficial"),
        ]
        for query_url, source_url, source_label, state in candidates:
            try:
                payload = get_json(source_label, query_url, {
                    "where": "1=1", "outFields": "*", "returnGeometry": "false", "f": "json"
                })
            except DataSourceError as exc:
                transport_failures += 1
                failures.append(f"{source_label}: {type(exc).__name__}: {exc}")
                logging.warning("No respondió %s para %s: %s", source_label, indicator, exc)
                continue

            source_quality = []
            try:
                features = payload.get("features") if isinstance(payload, dict) else None
                if not features:
                    raise ValueError("ArcGIS devolvió cero entidades o un esquema inesperado")
                records = []
                for feature in features:
                    attrs = feature.get("attributes", {})
                    dept, code = norm_dept(attrs.get("DPTO_CNMBR"), attrs.get("DPTO_CCDGO"))
                    if not dept:
                        continue
                    for field, value in attrs.items():
                        match = re.match(pattern, str(field), flags=re.I)
                        if match:
                            records.append({"departamento": dept, "codigo_divipola": code,
                                            "anio": int(match.group(1)), "valor": value})
                if not records:
                    raise ValueError("no hay campos anuales esperados en la respuesta")
                frame = standardize(
                    pd.DataFrame(records), "departamento", "anio", "valor", indicator,
                    "Pobreza y desigualdad", unit, f"{source_label} - {source}", source_url,
                    code="codigo_divipola", quality=source_quality,
                )
                for item in source_quality:
                    item["Estado"] = state
                quality.extend(source_quality)
                break
            except Exception as exc:
                schema_failures += 1
                failures.append(f"{source_label}: {type(exc).__name__}: {exc}")
                logging.warning("Respuesta incompatible de %s para %s: %s", source_label, indicator, exc)

        if frame is None and transport_failures == len(candidates):
            backup = DANE_BACKUP_DIR / backup_name
            try:
                cached = pd.read_csv(backup, dtype={"codigo_divipola": "string"})
                required = {"departamento", "codigo_divipola", "anio", "valor"}
                if not required.issubset(cached.columns):
                    raise ValueError(f"faltan columnas: {sorted(required - set(cached.columns))}")
                frame = standardize(
                    cached, "departamento", "anio", "valor", indicator,
                    "Pobreza y desigualdad", unit,
                    f"DANE - serie histórica 2012-2020 (respaldo local descargado 2026-11-03)",
                    public_url, code="codigo_divipola", quality=None,
                )
                if frame.empty:
                    raise ValueError("el CSV de respaldo no contiene filas válidas")
                quality.append({
                    "Indicador": indicator,
                    "Estado": "Respaldo local",
                    "Filas válidas": len(frame),
                    "Fuente": f"DANE - Geoportal histórico 2012-2020 | {backup.name}",
                    "Detalle": "Se usó una copia oficial versionada después de no responder ni el servicio ni el espejo.",
                })
            except Exception as backup_exc:
                logging.error("Fallaron las fuentes y el respaldo de %s: %s", indicator, backup_exc)
                quality.append({
                    "Indicador": indicator,
                    "Estado": "No disponible",
                    "Filas válidas": 0,
                    "Detalle": f"Fallaron el servicio, el espejo oficial y el CSV local: {type(backup_exc).__name__}: {backup_exc}",
                    "Fuente": source,
                })
                continue
        elif frame is None:
            quality.append({
                "Indicador": indicator,
                "Estado": "No disponible",
                "Filas válidas": 0,
                "Detalle": "Una fuente respondió, pero su esquema no pasó la validación; se requiere actualizar el mapeo antes de usar un respaldo.",
                "Fuente": source,
            })
            continue
        result.append(frame)
    return result


def load_education(quality: list) -> list[pd.DataFrame]:
    dataset = "ji8i-4anb"
    source = "datos.gov.co - MEN: estadísticas de educación por departamento"
    url = f"{SODA}/{dataset}.json"
    df = pd.DataFrame(soda_all(
        dataset,source,
        "ano,c_digo_departamento,departamento,cobertura_neta,cobertura_bruta,desercion",
    ))
    result = []
    for field,indicator in [
        ("cobertura_neta","Cobertura neta educación"),
        ("cobertura_bruta","Cobertura bruta educación"),
        ("desercion","Deserción escolar"),
    ]:
        if field not in df:
            raise source_error(source,url,ValueError(f"falta campo {field}"),
                               "actualiza el mapeo con el diccionario MEN.")
        raw = df[["departamento","c_digo_departamento","ano",field]].copy()
        raw[field] = to_number(raw[field])
        vals = raw[field].dropna()
        if not vals.empty and vals.abs().quantile(.95) <= 1.5:
            raw[field] = raw[field] * 100
        result.append(standardize(
            raw,"departamento","ano",field,indicator,"Educación y capital humano",
            "Porcentaje",source,"https://www.datos.gov.co/d/ji8i-4anb",
            code="c_digo_departamento",quality=quality,
        ))
    return result


def load_ctei(quality: list) -> list[pd.DataFrame]:
    dataset = "hrhc-c4wu"
    source = "datos.gov.co - MinCiencias: grupos de investigación reconocidos"
    url = f"{SODA}/{dataset}.json"
    df = pd.DataFrame(soda_all(
        dataset,source,"nme_departamento_gr,cod_dane_gr,ano_convo,cod_grupo_gr"
    ))
    required = {"nme_departamento_gr","ano_convo","cod_grupo_gr"}
    if not required.issubset(df):
        raise source_error(source,url,ValueError(f"faltan campos: {required-set(df)}"),
                           "actualiza el mapeo con el diccionario MinCiencias.")
    df["anio"] = df["ano_convo"].map(norm_year)
    geo = [norm_dept(df.at[i,"nme_departamento_gr"],
                     df.at[i,"cod_dane_gr"] if "cod_dane_gr" in df else None)
           for i in df.index]
    df["departamento"] = [x[0] for x in geo]
    df["codigo_divipola"] = [x[1] for x in geo]
    df = df.dropna(subset=["departamento","codigo_divipola","anio","cod_grupo_gr"])
    df = df.drop_duplicates(["codigo_divipola","anio","cod_grupo_gr"])
    if df.empty:
        raise source_error(source,url,ValueError("no hay grupos con periodo/geografía válidos"),
                           "revisa departamento, código DANE y convocatoria.")
    counts = df.groupby(["departamento","codigo_divipola","anio"],as_index=False)[
        "cod_grupo_gr"
    ].nunique().rename(columns={"cod_grupo_gr":"valor"})
    return [standardize(
        counts,"departamento","anio","valor","Grupos de investigación reconocidos",
        "Ciencia, tecnología e innovación","Grupos (conteo)",source,
        "https://www.datos.gov.co/Ciencia-Tecnolog-a-e-Innovaci-n/Grupos-de-Investigaci-n-Reconocidos/hrhc-c4wu",
        code="codigo_divipola",quality=quality,
    )]


# ---------------------------------------------------------------------------
# Nuevas integraciones con fuente oficial y respaldo estático versionado.
# ---------------------------------------------------------------------------

GEIH_DEPT_XLS = "https://www.dane.gov.co/files/operaciones/GEIH/anex-GEIHDepartamentos-2025.xls"
IDEAM_INDICATORS = (
    "https://visualizador.ideam.gov.co/gisserver/rest/services/Indicadores/"
    "INDICADORES_DATOS/MapServer"
)
IDEAM_VULNERABILITY = (
    "https://visualizador.ideam.gov.co/gisserver/rest/services/"
    "Vulnerabilidad_Cambio_Climatico/FeatureServer/5"
)
IDEAM_STATION_CROSSWALK = DANE_BACKUP_DIR / "ideam_cruce_municipio_estacion_departamento.csv"


def _record_quality(quality: list, indicator: str, state: str, frame: pd.DataFrame,
                    source: str, detail: str) -> None:
    quality.append({
        "Indicador": indicator,
        "Estado": state,
        "Filas válidas": len(frame),
        "Fuente": source,
        "Detalle": detail,
    })


def _snapshot_frame(filename: str, indicator: str, category: str, unit: str,
                    source: str, url: str, quality: list, detail: str,
                    live_error: Exception | None = None) -> pd.DataFrame:
    backup = DANE_BACKUP_DIR / filename
    try:
        cached = pd.read_csv(backup, dtype={"codigo_divipola": "string"})
        required = {"departamento", "codigo_divipola", "anio", "valor"}
        if not required.issubset(cached.columns):
            raise ValueError(f"faltan columnas: {sorted(required - set(cached.columns))}")
        if "indicador" in cached.columns:
            cached = cached[cached["indicador"] == indicator].copy()
        frame = standardize(
            cached, "departamento", "anio", "valor", indicator, category, unit,
            source, url, code="codigo_divipola", quality=None,
        )
        if frame.empty:
            raise ValueError("el CSV no contiene filas válidas para este indicador")
        note = detail
        if live_error is not None:
            note = (f"Se usó {backup.name} tras fallar la fuente en vivo: "
                    f"{type(live_error).__name__}: {live_error}. {detail}")
        _record_quality(quality, indicator, "Respaldo local", frame, source, note)
        return frame
    except Exception as backup_error:
        if live_error is None:
            live_text = "no se consultó una ruta de actualización automática"
        else:
            live_text = f"fuente en vivo: {type(live_error).__name__}: {live_error}"
        raise source_error(
            source, f"{url} | respaldo local: {backup}",
            ValueError(f"{live_text}; respaldo: {type(backup_error).__name__}: {backup_error}"),
            "verifica el endpoint oficial y confirma que el CSV versionado exista y conserve las columnas requeridas.",
        ) from backup_error


def _parse_geih_unemployment(raw: pd.DataFrame) -> pd.DataFrame:
    """Extrae la fila TD del anexo anual de departamentos de DANE."""
    years_by_col: dict[int, int] = {}
    current_dept: tuple[str | None, str | None] = (None, None)
    rows: list[dict] = []
    for values in raw.itertuples(index=False, name=None):
        first = values[0] if values else None
        found = {
            i: norm_year(value)
            for i, value in enumerate(values)
            if norm_year(value) is not None and 2000 <= norm_year(value) <= 2100
        }
        if len(found) >= 10:
            years_by_col = found

        label = "" if first is None or pd.isna(first) else str(first).strip()
        label_norm = norm(label)
        if "tasa de desocupacion" in label_norm:
            if current_dept[0] and years_by_col:
                for col, year in years_by_col.items():
                    if col < len(values):
                        value = pd.to_numeric(values[col], errors="coerce")
                        if pd.notna(value):
                            rows.append({
                                "departamento": current_dept[0],
                                "codigo_divipola": current_dept[1],
                                "anio": int(year),
                                "valor": float(value),
                            })
            continue

        if label and label_norm != "concepto":
            mapped = norm_dept(label)
            if mapped[0]:
                current_dept = mapped

    result = pd.DataFrame(rows)
    if result.empty:
        raise ValueError("no se localizó la fila Tasa de Desocupación (TD) en el anexo GEIH")
    if result.duplicated(["codigo_divipola", "anio"]).any():
        raise ValueError("el anexo GEIH contiene más de una tasa TD por departamento y año")
    if "Nariño" not in set(result.departamento) or result.departamento.nunique() < 20:
        raise ValueError("el anexo GEIH no contiene la cobertura departamental esperada o falta Nariño")
    return result


def load_unemployment(quality: list) -> pd.DataFrame:
    indicator = "Tasa de desempleo (GEIH)"
    category = "Mercado laboral"
    unit = "Porcentaje"
    source = "DANE - GEIH, mercado laboral por departamentos"
    try:
        content = get_bytes(source, GEIH_DEPT_XLS)
        try:
            raw = pd.read_excel(BytesIO(content), sheet_name="Departamentos anual",
                                header=None, engine="xlrd")
        except Exception as exc:
            raise source_error(source, GEIH_DEPT_XLS, exc,
                               "instala xlrd y confirma que el anexo conserve la hoja 'Departamentos anual'.") from exc
        parsed = _parse_geih_unemployment(raw)
        frame = standardize(
            parsed, "departamento", "anio", "valor", indicator, category, unit,
            source, GEIH_DEPT_XLS, code="codigo_divipola", quality=None,
        )
        _record_quality(
            quality, indicator, "En vivo", frame, source,
            "Serie anual 2007-2025 de 23 departamentos principales. DANE advierte un cambio metodológico GEIH desde 2021; no interpretar el quiebre como variación puramente económica.",
        )
        return frame
    except Exception as live_error:
        return _snapshot_frame(
            "dane_desempleo_departamental_2007_2025.csv", indicator, category, unit,
            source, GEIH_DEPT_XLS, quality,
            "Snapshot oficial descargado el 2026-11-03; cobertura 23 departamentos, años 2007-2025. Ruptura metodológica GEIH desde 2021.",
            live_error,
        )


def load_idf(quality: list) -> list[pd.DataFrame]:
    """Carga resultados publicados; el DNP no ofrece un endpoint tabular estable."""
    indicator = "Índice de Desempeño Fiscal (IDF)"
    category = "Finanzas públicas"
    unit = "Puntaje (0 a 100)"
    backup = DANE_BACKUP_DIR / "dnp_idf_departamental_2023_2024.csv"
    source23 = "DNP - IDF departamental 2023 (anexo XLSX oficial)"
    url23 = "https://colaboracion.dnp.gov.co/CDT/Desarrollo%20Territorial/Desempeno_Fiscal/ResultadosIDF_Nueva_MetodologIa_2023_Act.xlsx"
    source24 = "DNP - IDF departamental 2024 (presentación oficial)"
    url24 = "https://colaboracion.dnp.gov.co/CDT/Desarrollo%20Territorial/CIFFIT_DocumentosPublicacion/Presentacion_IDF_Departamentos_2024.pdf"
    try:
        data = pd.read_csv(backup, dtype={"codigo_divipola": "string"})
        required = {"departamento", "codigo_divipola", "anio", "valor"}
        if not required.issubset(data.columns):
            raise ValueError(f"faltan columnas: {sorted(required - set(data.columns))}")
        result = []
        for year, source, url, note in [
            (2023, source23, url23, "Valor de la columna Nuevo IDF, anexo exacto; la tabla publicada no incluye Bogotá D.C."),
            (2024, source24, url24, "Valores del cuadro departamental redondeados a un decimal; metodología por tipologías territoriales introducida en 2024. No comparar el cambio 2023-2024 como si mantuviera una metodología idéntica."),
        ]:
            subset = data[pd.to_numeric(data["anio"], errors="coerce").eq(year)]
            frame = standardize(
                subset, "departamento", "anio", "valor", indicator, category, unit,
                source, url, code="codigo_divipola", quality=None,
            )
            result.append(frame)
            _record_quality(quality, indicator, "Snapshot oficial local", frame, source,
                            f"Copia versionada 2026-11-03. {note}")
        return result
    except Exception as exc:
        raise source_error(
            "DNP - Índice de Desempeño Fiscal departamental", f"{url23} | {url24} | {backup}", exc,
            "verifica el anexo DNP y reemplaza el CSV con resultados departamentales oficiales para ambas vigencias.",
        ) from exc


def _ideam_table(table_id: int, source: str) -> tuple[pd.DataFrame, str]:
    url = f"{IDEAM_INDICATORS}/{table_id}/query"
    records: list[dict] = []
    offset = 0
    while True:
        payload = get_json(source, url, {
            "where": "1=1", "outFields": "*", "returnGeometry": "false",
            "resultOffset": offset, "resultRecordCount": 1000, "f": "json",
        })
        features = payload.get("features") if isinstance(payload, dict) else None
        if not isinstance(features, list):
            raise source_error(source, url, ValueError("ArcGIS no devolvió la lista features"),
                               "revisa el servicio IDEAM y el identificador de la tabla.")
        records.extend(feature.get("attributes", {}) for feature in features)
        if len(features) < 1000:
            break
        offset += len(features)
    if not records:
        raise source_error(source, url, ValueError("tabla IDEAM vacía"),
                           "confirma que el servicio de indicadores siga publicado.")
    return pd.DataFrame(records), url


def _ideam_dept(name) -> tuple[str | None, str | None]:
    mapped = norm_dept(name)
    if mapped[0]:
        return mapped
    key = norm(name)
    canonical = {norm(value): value for value in DIVIPOLA.values()}
    match = get_close_matches(key, list(canonical), n=1, cutoff=0.78)
    return norm_dept(canonical[match[0]]) if match else (None, None)


def _column_by_short_name(frame: pd.DataFrame, name: str) -> str:
    target = norm(name)
    for column in frame.columns:
        # The live IDEAM service currently returns "a\ufffdo" for the year field.
        if target == "ano" and str(column).lower().startswith("a") and len(str(column)) <= 4:
            return column
        if norm(column) == target:
            return column
    raise ValueError(f"no se encontró el campo {name}; columnas recibidas: {list(frame.columns)}")


def _ideam_period_end(period) -> int | None:
    years = [int(value) for value in re.findall(r"(?:19|20)\d{2}", str(period))]
    if not years:
        return None
    if len(years) > 1:
        start, end = years[-2], years[-1]
        # IDEAM recomienda graficar únicamente los periodos anuales desde 2012-2013.
        if start < 2012 or end - start != 1:
            return None
        return end
    return years[0] if years[0] >= 2013 else None


def _parse_forest_cover(frame: pd.DataFrame) -> pd.DataFrame:
    dept_col = _column_by_short_name(frame, "departamento")
    var_col = _column_by_short_name(frame, "variable")
    value_col = _column_by_short_name(frame, "valor")
    year_col = _column_by_short_name(frame, "año")
    rows = []
    for _, row in frame.iterrows():
        score = SequenceMatcher(None, norm(row[var_col]), norm("Superficie cubierta por bosque natural")).ratio()
        if score < 0.86:
            continue
        dept, code = _ideam_dept(row[dept_col])
        year = norm_year(row[year_col])
        value = pd.to_numeric(row[value_col], errors="coerce")
        if dept and year and pd.notna(value):
            rows.append({"departamento": dept, "codigo_divipola": code, "anio": year, "valor": float(value)})
    result = pd.DataFrame(rows)
    if result.empty:
        raise ValueError("la tabla IDEAM no contiene Superficie cubierta por bosque natural")
    return result


def _parse_deforestation_rates(frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    dept_col = _column_by_short_name(frame, "departamento")
    var_col = _column_by_short_name(frame, "variable")
    value_col = _column_by_short_name(frame, "valor")
    year_col = _column_by_short_name(frame, "año")
    specs = [
        ("Tasa anual de deforestación", "Tasa anual de deforestación (IDEAM)"),
        ("Promedio anual de superficie deforestada", "Deforestación promedio anual (IDEAM)"),
    ]
    results: dict[str, pd.DataFrame] = {}
    for source_label, indicator in specs:
        rows = []
        for _, row in frame.iterrows():
            score = SequenceMatcher(None, norm(row[var_col]), norm(source_label)).ratio()
            if score < 0.85:
                continue
            dept, code = _ideam_dept(row[dept_col])
            year = _ideam_period_end(row[year_col])
            value = pd.to_numeric(row[value_col], errors="coerce")
            if dept and year and pd.notna(value):
                rows.append({"departamento": dept, "codigo_divipola": code,
                             "anio": year, "valor": float(value)})
        result = pd.DataFrame(rows)
        if result.empty:
            raise ValueError(f"la tabla IDEAM no contiene {source_label} para periodos anuales")
        results[indicator] = result
    return results


def load_forest(quality: list) -> list[pd.DataFrame]:
    backup_name = "ideam_bosques_departamental.csv"
    backup = DANE_BACKUP_DIR / backup_name
    source50 = "IDEAM - proporción/superficie de bosque natural por departamento"
    source56 = "IDEAM - tasa anual y promedio anual de deforestación por departamento"
    result: list[pd.DataFrame] = []

    try:
        raw50, url50 = _ideam_table(50, source50)
        cover = _parse_forest_cover(raw50)
        source = source50
        status = "En vivo"
        note = "Superficie de bosque natural publicada por año; conserva solo vigencias observadas, sin interpolación."
    except Exception as live_error:
        cover = _snapshot_frame(
            backup_name, "Superficie cubierta por bosque natural (IDEAM)", "Medio ambiente",
            "Hectáreas", source50, f"{IDEAM_INDICATORS}/50", quality,
            "Snapshot IDEAM del 2026-11-03.", live_error,
        )
        result.append(cover)
        raw50 = None

    if raw50 is not None:
        cover = standardize(
            cover, "departamento", "anio", "valor", "Superficie cubierta por bosque natural (IDEAM)",
            "Medio ambiente", "Hectáreas", source50, url50, code="codigo_divipola", quality=None,
        )
        _record_quality(quality, "Superficie cubierta por bosque natural (IDEAM)", status,
                        cover, source, note)
        result.append(cover)

    try:
        raw56, url56 = _ideam_table(56, source56)
        parsed = _parse_deforestation_rates(raw56)
    except Exception as live_error:
        for indicator, unit, detail in [
            ("Tasa anual de deforestación (IDEAM)", "Porcentaje anual", "Valores IDEAM negativos indican pérdida de bosque; los datos se muestran con su signo publicado. Solo periodos anuales desde 2012-2013; el año del registro es el final del intervalo."),
            ("Deforestación promedio anual (IDEAM)", "Hectáreas por año", "Promedio anual publicado para el intervalo IDEAM; solo periodos anuales desde 2012-2013 y año del registro = final del intervalo."),
        ]:
            result.append(_snapshot_frame(
                backup_name, indicator, "Medio ambiente", unit, source56,
                f"{IDEAM_INDICATORS}/56", quality, f"Snapshot IDEAM 2026-11-03. {detail}", live_error,
            ))
        return result

    for indicator, unit, note in [
        ("Tasa anual de deforestación (IDEAM)", "Porcentaje anual",
         "Valores negativos indican pérdida de bosque natural; se conserva el signo oficial. Periodos anuales desde 2012-2013, etiquetados por su año final."),
        ("Deforestación promedio anual (IDEAM)", "Hectáreas por año",
         "Promedio anual de pérdida de bosque reportado para periodos anuales desde 2012-2013; el año del registro es el final del intervalo."),
    ]:
        frame = standardize(
            parsed[indicator], "departamento", "anio", "valor", indicator,
            "Medio ambiente", unit, source56, url56, code="codigo_divipola", quality=None,
        )
        _record_quality(quality, indicator, "En vivo", frame, source56, note)
        result.append(frame)
    return result


def _municipality_code(value, crosswalk: dict[str, str]) -> str | None:
    key = norm(value)
    if key in crosswalk:
        return crosswalk[key]
    near = get_close_matches(key, list(crosswalk), n=2, cutoff=0.78)
    codes = {crosswalk[candidate] for candidate in near}
    return next(iter(codes)) if len(codes) == 1 else None


def _load_station_crosswalk() -> dict[str, str]:
    table = pd.read_csv(IDEAM_STATION_CROSSWALK, dtype={"codigo_divipola": "string"})
    required = {"municipio_key", "codigo_divipola"}
    if not required.issubset(table.columns):
        raise ValueError(f"cruce municipal IDEAM incompleto: faltan {sorted(required - set(table.columns))}")
    mapping = {}
    for _, row in table.iterrows():
        key = norm(row["municipio_key"])
        code = str(row["codigo_divipola"]).zfill(2)
        if code not in DIVIPOLA:
            raise ValueError(f"código DIVIPOLA inválido en el cruce de estaciones: {code}")
        if key in mapping and mapping[key] != code:
            raise ValueError(f"municipio ambiguo en el cruce de estaciones: {key}")
        mapping[key] = code
    return mapping


def _parse_climate_stations(raw: pd.DataFrame, value_name: str,
                            crosswalk: dict[str, str]) -> tuple[pd.DataFrame, int]:
    year_col = _column_by_short_name(raw, "año")
    municipality_col = _column_by_short_name(raw, "municipio")
    station_col = next((col for col in raw.columns if str(col).lower().startswith("estaci")), None)
    if station_col is None:
        raise ValueError(f"tabla climática sin columna de estación: {list(raw.columns)}")
    target = norm(value_name)
    excluded = {"objectid", year_col, municipality_col, station_col}
    value_col = max(
        [col for col in raw.columns if col not in excluded and norm(col) not in
         {"ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"}],
        key=lambda col: SequenceMatcher(None, norm(col), target).ratio(),
    )
    matched = raw.copy()
    matched["codigo_divipola"] = matched[municipality_col].map(
        lambda value: _municipality_code(value, crosswalk)
    )
    if matched["codigo_divipola"].isna().any():
        missing = sorted(matched.loc[matched.codigo_divipola.isna(), municipality_col].astype(str).unique())
        raise ValueError(f"municipios de estaciones sin cruce DIVIPOLA: {missing}")
    matched["departamento"] = matched["codigo_divipola"].map(DIVIPOLA)
    matched["anio"] = matched[year_col].map(norm_year)
    matched["valor"] = to_number(matched[value_col])
    matched["estacion"] = matched[station_col].astype(str)
    matched = matched.dropna(subset=["departamento", "anio", "valor"])
    result = matched.groupby(
        ["departamento", "codigo_divipola", "anio"], as_index=False
    ).agg(valor=("valor", "mean"), n_estaciones=("estacion", "nunique"))
    if result.empty:
        raise ValueError(f"no hay datos climáticos válidos para el campo {value_name}")
    return result, matched["estacion"].nunique()


def load_climate(quality: list) -> list[pd.DataFrame]:
    specs = [
        (39, "Anomalía media anual de temperatura (IDEAM, estaciones)",
         "anomalía_media_anual", "°C de anomalía"),
        (40, "Índice anual de precipitación (IDEAM, estaciones)",
         "índice de precipitación anual", "Índice IDEAM"),
    ]
    snapshot = "ideam_anomalias_climaticas_departamental_estaciones_2000_2025.csv"
    try:
        crosswalk = _load_station_crosswalk()
    except Exception as exc:
        crosswalk = None
        crosswalk_error = exc

    output = []
    for table_id, indicator, value_name, unit in specs:
        source = f"IDEAM - {indicator} en estaciones de referencia"
        url = f"{IDEAM_INDICATORS}/{table_id}/query"
        try:
            if crosswalk is None:
                raise ValueError(f"no se pudo leer el cruce de estaciones: {crosswalk_error}")
            raw, url = _ideam_table(table_id, source)
            parsed, station_count = _parse_climate_stations(raw, value_name, crosswalk)
            frame = standardize(
                parsed, "departamento", "anio", "valor", indicator, "Clima y ambiente",
                unit, source, url, code="codigo_divipola", quality=None,
            )
            _record_quality(
                quality, indicator, "En vivo", frame, source,
                f"Promedio simple de {station_count} estaciones de referencia, agrupadas por municipio. No equivale a promedio espacial departamental; el índice de precipitación conserva la escala publicada por IDEAM.",
            )
        except Exception as live_error:
            frame = _snapshot_frame(
                snapshot, indicator, "Clima y ambiente", unit, source, url, quality,
                "Promedio simple de estaciones de referencia agrupadas por municipio; no es un promedio espacial del departamento. Snapshot oficial 2026-11-03.",
                live_error,
            )
        output.append(frame)
    return output


def _aggregate_vulnerability(features: list[dict]) -> pd.DataFrame:
    frame = pd.DataFrame(features)
    required = {"nom_dpto", "val_vu_cc", "area_ha"}
    if frame.empty or not required.issubset(frame.columns):
        raise ValueError(f"capa de vulnerabilidad sin campos requeridos {sorted(required)}")
    geo = [_ideam_dept(value) for value in frame["nom_dpto"]]
    frame["departamento"] = [item[0] for item in geo]
    frame["codigo_divipola"] = [item[1] for item in geo]
    frame["valor"] = to_number(frame["val_vu_cc"])
    frame["area_ha"] = to_number(frame["area_ha"])
    frame = frame.dropna(subset=["departamento", "valor", "area_ha"])
    frame = frame[frame["area_ha"] > 0].copy()
    frame["valor_area"] = frame["valor"] * frame["area_ha"]
    result = frame.groupby(
        ["departamento", "codigo_divipola"], as_index=False
    ).agg(valor_area=("valor_area", "sum"), area_ha=("area_ha", "sum"))
    result["anio"] = 2017
    result["valor"] = result["valor_area"] / result["area_ha"]
    if result.empty:
        raise ValueError("no quedaron municipios con valor y área válidos")
    return result[["departamento", "codigo_divipola", "anio", "valor"]]


def load_climate_vulnerability(quality: list) -> pd.DataFrame:
    indicator = "Índice de vulnerabilidad al cambio climático (IDEAM, 2017)"
    category = "Cambio climático y riesgo"
    unit = "Índice (0.1 a 1.0)"
    source = "IDEAM - TCNCC 2017, agregación departamental ponderada por área"
    url = f"{IDEAM_VULNERABILITY}/query"
    try:
        features: list[dict] = []
        offset = 0
        while True:
            payload = get_json(source, url, {
                "where": "1=1", "outFields": "nom_dpto,val_vu_cc,area_ha,cod_mpio",
                "returnGeometry": "false", "resultOffset": offset,
                "resultRecordCount": 1000, "f": "json",
            })
            page = payload.get("features") if isinstance(payload, dict) else None
            if not isinstance(page, list):
                raise ValueError("ArcGIS no devolvió features de vulnerabilidad")
            features.extend(feature.get("attributes", {}) for feature in page)
            if len(page) < 1000:
                break
            offset += len(page)
        aggregate = _aggregate_vulnerability(features)
        frame = standardize(
            aggregate, "departamento", "anio", "valor", indicator, category, unit,
            source, url, code="codigo_divipola", quality=None,
        )
        _record_quality(
            quality, indicator, "En vivo", frame, source,
            "Corte único 2017. Agregado departamental como promedio ponderado por área municipal, no por población; no debe leerse como tendencia anual.",
        )
        return frame
    except Exception as live_error:
        return _snapshot_frame(
            "ideam_vulnerabilidad_cc_departamental_2017.csv", indicator, category, unit,
            source, url, quality,
            "Corte único 2017, promedio ponderado por área municipal; no es una serie temporal. Snapshot oficial 2026-11-03.",
            live_error,
        )
