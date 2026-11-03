# -*- coding: utf-8 -*-
"""Conectores de fuentes activas (migrados sin cambios desde app.py)."""
from __future__ import annotations

import logging
import re
from io import BytesIO

import pandas as pd

from observatorio.config import (DANE_BACKUP_DIR, GINI, GINI_MIRROR, POP_XLSX, POVERTY,
                                 POVERTY_MIRROR, SODA, LIMIT)
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
