# -*- coding: utf-8 -*-
"""Observatorio socioeconómico colombiano con énfasis en Nariño."""
from __future__ import annotations

import logging
import re
import sys
import unicodedata
from io import BytesIO
from typing import Any

import pandas as pd
import plotly.express as px
import requests
import streamlit as st

st.set_page_config(page_title="Observatorio | Nariño", page_icon="🇨🇴", layout="wide")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

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
class DataSourceError(RuntimeError):
    """Error controlado de fuente o parseo."""


def norm(text: Any) -> str:
    if text is None or pd.isna(text):
        return ""
    text = "".join(c for c in unicodedata.normalize("NFD", str(text).strip().lower())
                   if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


DEPT_LOOKUP = {norm(v): v for v in DIVIPOLA.values()}
DEPT_LOOKUP.update({norm(k): v for k, v in ALIASES.items()})


def norm_code(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    s = str(value).strip()
    if re.fullmatch(r"\d+\.0+", s):
        s = s.split(".", 1)[0]
    digits = re.sub(r"\D", "", s)
    code = digits[:2].zfill(2) if digits else None
    return code if code in DIVIPOLA else None


def norm_dept(name: Any, code: Any = None) -> tuple[str | None, str | None]:
    code = norm_code(code)
    if code:
        return DIVIPOLA[code], code
    name = DEPT_LOOKUP.get(norm(name))
    return (name, CODE[name]) if name else (None, None)


def norm_year(value: Any) -> int | None:
    if value is None or pd.isna(value):
        return None
    match = re.search(r"(?:19|20)\d{2}", str(value))
    return int(match.group()) if match else None


def to_number(series: pd.Series) -> pd.Series:
    def one(v: Any) -> float:
        if v is None or pd.isna(v):
            return float("nan")
        if isinstance(v, (float, int)):
            return float(v)
        s = str(v).strip().replace("$", "").replace("%", "").replace(" ", "")
        if "," in s and "." in s:
            s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
        elif "," in s:
            tail = s.rsplit(",", 1)[-1]
            s = s.replace(",", ".") if len(tail) <= 2 else s.replace(",", "")
        try:
            return float(s)
        except ValueError:
            return float("nan")
    return series.map(one)


def source_error(source: str, url: str, exc: Exception, action: str) -> DataSourceError:
    return DataSourceError(
        f"FALLÓ LA FUENTE: {source}\nURL: {url}\n"
        f"Error técnico: {type(exc).__name__}: {exc}\nAcción: {action}"
    )


def get_json(source: str, url: str, params: dict | None = None) -> Any:
    try:
        response = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
        response.raise_for_status()
        data = response.json()
        if isinstance(data, dict) and data.get("error"):
            raise ValueError(f"servicio reporta: {data['error']}")
        return data
    except Exception as exc:
        raise source_error(source, response.url if "response" in locals() else url, exc,
                           "verifica conectividad, endpoint, estado HTTP y campos de consulta.") from exc


def get_bytes(source: str, url: str) -> bytes:
    try:
        response = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        response.raise_for_status()
        if not response.content:
            raise ValueError("respuesta vacía")
        return response.content
    except Exception as exc:
        raise source_error(source, response.url if "response" in locals() else url, exc,
                           "verifica que el anexo DANE siga publicado y sea un XLSX.") from exc


def soda_all(dataset: str, source: str, fields: str) -> list[dict]:
    url = f"{SODA}/{dataset}.json"
    result, offset = [], 0
    while True:
        data = get_json(source, url, {
            "$select": fields, "$limit": LIMIT, "$offset": offset, "$order": ":id"
        })
        if not isinstance(data, list):
            raise source_error(source, url, ValueError("SODA no devolvió una lista"),
                               "actualiza el diccionario de campos del dataset.")
        result.extend(data)
        if len(data) < LIMIT:
            break
        offset += LIMIT
    if not result:
        raise source_error(source, url, ValueError("cero registros"),
                           "verifica disponibilidad y filtros de la consulta.")
    return result


BASE = ["departamento","codigo_divipola","anio","indicador","categoria",
        "valor","unidad","fuente","fuente_url"]


def standardize(df: pd.DataFrame, dept: str, year: str, value: str, indicator: str,
                category: str, unit: str, source: str, url: str,
                code: str | None = None, quality: list | None = None) -> pd.DataFrame:
    need = [dept, year, value] + ([code] if code else [])
    missing = [c for c in need if c not in df]
    if missing or df.empty:
        raise ValueError(f"{indicator}: faltan columnas {missing} o el DataFrame está vacío")
    out = pd.DataFrame(index=df.index)
    geo = [norm_dept(df.at[i, dept], df.at[i, code] if code else None) for i in df.index]
    out["departamento"] = [x[0] for x in geo]
    out["codigo_divipola"] = [x[1] for x in geo]
    out["anio"] = df[year].map(norm_year)
    out["valor"] = to_number(df[value])
    out["indicador"], out["categoria"], out["unidad"] = indicator, category, unit
    out["fuente"], out["fuente_url"] = source, url
    before = len(out)
    miss_val = int(out["valor"].isna().sum())
    miss_geo = int(out["departamento"].isna().sum())
    miss_year = int(out["anio"].isna().sum())
    out = out.dropna(subset=["departamento","codigo_divipola","anio","valor"]).copy()
    out["anio"] = out["anio"].astype(int)
    if quality is not None:
        quality.append({
            "Indicador": indicator, "Filas fuente": before,
            "Nulos de valor descartados": miss_val,
            "Geografía no homologada": miss_geo,
            "Periodo inválido": miss_year, "Filas válidas": len(out),
            "Fuente": source,
        })
    if out.empty:
        raise ValueError(f"{indicator}: no quedaron filas válidas")
    return out[BASE]


def load_population(quality: list) -> pd.DataFrame:
    source = "DANE - proyecciones departamentales de población"
    content = get_bytes(source, POP_XLSX)
    try:
        sheets = pd.read_excel(BytesIO(content), sheet_name=None, header=None, engine="openpyxl")
    except Exception as exc:
        raise source_error(source, POP_XLSX, exc, "revisa el formato del anexo XLSX.") from exc
    for sheet_name, raw in sheets.items():
        for h in range(min(30, len(raw))):
            header = ["" if pd.isna(x) else str(x).strip() for x in raw.iloc[h]]
            labels = [norm(x).replace(" ", "") for x in header]
            dept_i = next((i for i,x in enumerate(labels) if x in
                           {"departamento","nombredepartamento","dpto","nomdpto"}), None)
            code_i = next((i for i,x in enumerate(labels) if x in
                           {"codigodepartamento","coddepartamento","coddpto","codigodane","divipola","codigo"}), None)
            years = [(i,norm_year(x)) for i,x in enumerate(header)
                     if norm_year(x) and 1980 <= norm_year(x) <= 2100]
            if (dept_i is None and code_i is None) or len(years) < 2:
                continue
            data = raw.iloc[h+1:].copy()
            year_i = {i for i,_ in years}
            other_i = set(range(data.shape[1])) - year_i - {i for i in (dept_i,code_i) if i is not None}
            for i in other_i:
                label = labels[i] if i < len(labels) else ""
                if any(x in label for x in ("area","sexo","edad","total")):
                    vals = data.iloc[:,i].dropna().astype(str).map(norm)
                    if vals.str.fullmatch(r"total(?: general| poblacion)?").any():
                        keep = data.iloc[:,i].astype(str).map(norm).str.fullmatch(r"total(?: general| poblacion)?")
                        data = data.loc[keep]
            rows = []
            for _, row in data.iterrows():
                name = row.iloc[dept_i] if dept_i is not None else None
                raw_code = row.iloc[code_i] if code_i is not None else None
                d, c = norm_dept(name, raw_code)
                if not d:
                    continue
                for i, year in years:
                    v = to_number(pd.Series([row.iloc[i]])).iloc[0]
                    if pd.notna(v):
                        rows.append({"departamento":d,"codigo_divipola":c,"anio":year,"valor":v})
            pop = pd.DataFrame(rows)
            if pop.empty:
                continue
            duplicate = pop.duplicated(["codigo_divipola","anio"], keep=False)
            if duplicate.any():
                raise source_error(source, POP_XLSX,
                    ValueError(f"duplicados en hoja {sheet_name}: {pop.loc[duplicate,['departamento','anio']].drop_duplicates().head().to_dict('records')}"),
                    "inspecciona dimensiones del XLSX y conserva la fila Total correcta.")
            quality.append({"Indicador":"Población de referencia","Filas fuente":len(pop),
                            "Nulos de valor descartados":0,"Geografía no homologada":0,
                            "Periodo inválido":0,"Filas válidas":len(pop),
                            "Fuente":f"{source} | {sheet_name}"})
            return pop
    raise source_error(source, POP_XLSX,
                       ValueError(f"no se reconoció tabla de población; hojas: {list(sheets)}"),
                       "revisa encabezados de Departamento, DIVIPOLA y años en el anexo.")



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
        (POVERTY,"DANE - incidencia de pobreza monetaria",r"^IP_AM_(\d{4})$",
         "Pobreza monetaria","Porcentaje",
         "https://geoportal.dane.gov.co/mparcgis/rest/services/INDICADORES_COND_DE_VIDA/Serv_Deptos_Pobreza_2012_2020/MapServer"),
        (GINI,"DANE - coeficiente de Gini",r"^GINI_(\d{4})$",
         "Coeficiente de Gini","Coeficiente (0 a 1)",
         "https://geoportal.dane.gov.co/mparcgis/rest/services/INDICADORES_COND_DE_VIDA/Serv_Deptos_CoeficienteGini_2012_2020/MapServer"),
    ]
    result = []
    for endpoint,source,pattern,indicator,unit,public_url in specs:
        payload = get_json(source,endpoint,{
            "where":"1=1","outFields":"*","returnGeometry":"false","f":"json"
        })
        features = payload.get("features") if isinstance(payload,dict) else None
        if not features:
            raise source_error(source,endpoint,ValueError("ArcGIS devolvió cero entidades"),
                               "revisa disponibilidad del servicio y el ID de capa.")
        records = []
        for feature in features:
            attrs = feature.get("attributes",{})
            dept,code = norm_dept(attrs.get("DPTO_CNMBR"),attrs.get("DPTO_CCDGO"))
            if not dept:
                continue
            for field,value in attrs.items():
                match = re.match(pattern,str(field),flags=re.I)
                if match:
                    records.append({"departamento":dept,"codigo_divipola":code,
                                    "anio":int(match.group(1)),"valor":value})
        if not records:
            raise source_error(source,endpoint,ValueError("no hay campos anuales esperados"),
                               "inspecciona los campos ArcGIS y actualiza el patrón.")
        result.append(standardize(
            pd.DataFrame(records),"departamento","anio","valor",indicator,
            "Pobreza y desigualdad",unit,source,public_url,
            code="codigo_divipola",quality=quality,
        ))
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


@st.cache_data(ttl=21600,show_spinner="Consultando fuentes oficiales y preparando indicadores…")
def load_all() -> tuple[pd.DataFrame,pd.DataFrame]:
    quality = []
    population = load_population(quality)
    parts = []
    parts += load_gdp(population,quality)
    parts += load_homicides(population,quality)
    parts += load_finance(population,quality)
    parts += load_poverty_gini(quality)
    parts += load_education(quality)
    parts += load_ctei(quality)
    master = pd.concat(parts,ignore_index=True)
    master["anio"] = pd.to_numeric(master["anio"],errors="coerce")
    master["valor"] = pd.to_numeric(master["valor"],errors="coerce")
    master = master.dropna(subset=["departamento","codigo_divipola","anio","valor"])
    master["anio"] = master["anio"].astype(int)
    if master.empty:
        raise DataSourceError("FALLÓ EL PIPELINE: cero indicadores válidos. Revisa las fuentes y sus campos.")
    return master.sort_values(["categoria","indicador","departamento","anio"]),pd.DataFrame(quality)


def show_value(value: float, unit: str) -> str:
    if pd.isna(value):
        return "Sin dato"
    if unit == "Porcentaje":
        return f"{value:,.1f}%"
    if unit.startswith("Coeficiente"):
        return f"{value:.3f}"
    if unit == "Grupos (conteo)" or unit == "Víctimas":
        return f"{value:,.0f}"
    return f"{value:,.2f}"


def reference(master: pd.DataFrame, indicator: str, year: int) -> tuple[float | None,str]:
    data = master[(master.indicador==indicator)&(master.anio==year)].copy()
    data["key"] = data.departamento.map(norm)
    national = data[data.key.isin({"colombia","nacional","total nacional"})]
    if not national.empty:
        return float(national.valor.iloc[0]),"Dato nacional publicado"
    other = data[data.departamento!="Nariño"].drop_duplicates("codigo_divipola")
    return (float(other.valor.mean()),"Promedio simple de otros departamentos") if not other.empty else (None,"Sin referencia")


def latest(master: pd.DataFrame, indicator: str) -> pd.Series | None:
    data = master[(master.indicador==indicator)&(master.departamento=="Nariño")].sort_values("anio")
    return None if data.empty else data.iloc[-1]


def pending() -> list[dict[str,str]]:
    return [
        {"Dimensión":"Mercado laboral GEIH","Estado":"Pendiente",
         "Nota":"Integrar anexos DANE y validar periodos, cobertura y comparabilidad.",
         "Fuente":"https://www.dane.gov.co/index.php/estadisticas-por-tema/mercado-laboral/mercado-laboral-por-departamentos/mercado-laboral-por-departamento-historicos"},
        {"Dimensión":"IDC","Estado":"Pendiente",
         "Nota":"Conectar la serie anual del Índice Departamental de Competitividad.",
         "Fuente":"https://compite.com.co/"},
        {"Dimensión":"Saber 11","Estado":"Pendiente",
         "Nota":"Se incluye cobertura MEN, no resultados departamentales de Saber 11.",
         "Fuente":"https://www.datos.gov.co/"},
        {"Dimensión":"Salud","Estado":"Pendiente",
         "Nota":"Faltan series departamentales con definición y denominador comprobados.",
         "Fuente":"https://www.dane.gov.co/index.php/estadisticas-por-tema/salud"},
        {"Dimensión":"Deforestación","Estado":"Pendiente",
         "Nota":"Confirmar campos, periodo y nivel geográfico del dataset IDEAM.",
         "Fuente":"https://www.datos.gov.co/Ambiente-y-Desarrollo-Sostenible/Monitoreo-de-bosques/pb29-gexz"},
        {"Dimensión":"CTeI - inversión I+D","Estado":"Parcial",
         "Nota":"Grupos reconocidos miden capacidad científica, no gasto en I+D.",
         "Fuente":"https://minciencias.gov.co/ciudadano/datosabiertos"},
    ]


st.title("🇨🇴 Observatorio Socioeconómico y de Competitividad")
st.subheader("Colombia con énfasis analítico en Nariño")
st.caption("Fuentes oficiales/públicas, sin datos sintéticos. La cobertura varía por indicador.")
try:
    master,quality = load_all()
except DataSourceError as exc:
    logging.error("%s",exc)
    st.error("La carga se detuvo porque falló una fuente requerida.")
    st.code(str(exc),language="text")
    st.stop()
except Exception as exc:
    logging.exception("Falla de procesamiento")
    st.error("La carga se detuvo por un error inesperado; no se muestran datos parciales.")
    st.code(f"Error técnico: {type(exc).__name__}: {exc}\nAcción: revisa la traza y los campos de la fuente oficial.",language="text")
    st.stop()

with st.sidebar:
    st.header("Explorar")
    mode = st.radio("Filtro de enfoque",["Vista Nacional General","Vista de Análisis Profundo: Nariño"],index=1)
    categories = sorted(master.categoria.unique())
    category = st.selectbox("Dimensión",categories)
    cat = master[master.categoria==category]
    indicator = st.selectbox("Indicador",sorted(cat.indicador.unique()))
    depts = sorted(master.departamento.unique())
    defaults = [d for d in ["Nariño","Cauca","Valle del Cauca","Putumayo"] if d in depts] if mode.endswith("Nariño") else depts
    chosen_depts = st.multiselect("Departamentos",depts,default=defaults)
    years = sorted(master.loc[master.indicador==indicator,"anio"].unique())
    ymin,ymax = int(min(years)),int(max(years))
    period = st.slider("Rango de años",ymin,ymax,(ymin,ymax)) if ymin<ymax else (ymin,ymax)

view = master[(master.categoria==category)&(master.indicador==indicator)&master.anio.between(*period)]
if chosen_depts:
    view = view[view.departamento.isin(chosen_depts)]

st.markdown("### Indicadores clave de Nariño")
kpis = [x for x in ["PIB por habitante","Homicidios por 100.000 habitantes","Pobreza monetaria","Coeficiente de Gini"] if x in set(master.indicador)]
for col,name in zip(st.columns(max(1,len(kpis))),kpis):
    row = latest(master,name)
    if row is None:
        col.metric(name,"Sin dato")
    else:
        ref,ref_name = reference(master,name,int(row.anio))
        delta = None if ref is None else f"{row.valor-ref:+,.2f} vs ref."
        col.metric(f"{name} · {int(row.anio)}",show_value(row.valor,row.unidad),delta,
                   help=f"{ref_name}: {show_value(ref,row.unidad)}" if ref is not None else "Sin referencia")
st.caption("Si no hay dato nacional publicado, la referencia es la media simple de otros departamentos, no un agregado ponderado nacional.")

st.markdown("### Comparativa territorial")
if view.empty:
    st.info("No hay registros para estos filtros.")
else:
    trend = master[master.indicador==indicator]
    regional = trend[trend.departamento.isin(chosen_depts)][["anio","departamento","valor"]].copy()
    national = trend[trend.departamento.map(norm).isin({"colombia","nacional","total nacional"})]
    if national.empty:
        refline = trend[trend.departamento!="Nariño"].groupby("anio",as_index=False).valor.mean()
        refline["departamento"] = "Promedio simple de otros departamentos"
    else:
        refline = national[["anio","valor"]].copy()
        refline["departamento"] = "Colombia (dato publicado)"
    chart = pd.concat([regional,refline],ignore_index=True)
    chart = chart[chart.anio.between(*period)]
    fig = px.line(chart,x="anio",y="valor",color="departamento",markers=True,
                  title=f"Evolución: {indicator}",template="plotly_white",
                  labels={"anio":"Año","valor":view.unidad.iloc[0],"departamento":"Territorio"})
    fig.update_layout(hovermode="x unified",legend_title_text="")
    st.plotly_chart(fig,use_container_width=True)

tab1,tab2,tab3 = st.tabs(["Ranking","Dispersión","Datos y calidad"])
with tab1:
    choices = sorted(master.loc[master.indicador==indicator,"anio"].unique())
    year = st.selectbox("Vigencia",choices,index=len(choices)-1,key="rank_year")
    rank = master[(master.indicador==indicator)&(master.anio==year)].nlargest(15,"valor").sort_values("valor")
    fig = px.bar(rank,x="valor",y="departamento",orientation="h",color="valor",
                 color_continuous_scale="Blues",template="plotly_white",
                 title=f"Mayores valores · {year}")
    fig.update_layout(yaxis={"categoryorder":"total ascending"})
    st.plotly_chart(fig,use_container_width=True)
with tab2:
    all_ind = sorted(master.indicador.unique())
    xcol,ycol,yrc = st.columns([2,2,1])
    xind = xcol.selectbox("Eje X",all_ind,key="xind")
    yind = ycol.selectbox("Eje Y",all_ind,index=all_ind.index(indicator),key="yind")
    common = sorted(set(master.loc[master.indicador==xind,"anio"]) & set(master.loc[master.indicador==yind,"anio"]))
    if common:
        y = yrc.selectbox("Año",common,index=len(common)-1,key="scatter_year")
        xdf = master[(master.indicador==xind)&(master.anio==y)][["departamento","valor"]].rename(columns={"valor":"x"})
        ydf = master[(master.indicador==yind)&(master.anio==y)][["departamento","valor"]].rename(columns={"valor":"y"})
        scatter = xdf.merge(ydf,on="departamento")
        fig = px.scatter(scatter,x="x",y="y",text="departamento",hover_name="departamento",
                         template="plotly_white",title=f"{yind} vs {xind} · {y}")
        fig.update_traces(textposition="top center")
        st.plotly_chart(fig,use_container_width=True)
    else:
        st.info("Los indicadores no comparten vigencia.")
with tab3:
    st.dataframe(view.sort_values(["departamento","anio"]),use_container_width=True,hide_index=True)
    st.download_button("Descargar CSV",view.to_csv(index=False).encode("utf-8-sig"),
                       "observatorio_narino.csv","text/csv")
    st.markdown("#### Calidad de los datos")
    st.dataframe(quality,use_container_width=True,hide_index=True)

with st.expander("Cobertura, límites y fuentes"):
    st.markdown("Integrados: PIB, homicidios/tasa, recursos DNP, pobreza y Gini, coberturas/deserción MEN, grupos de investigación MinCiencias.")
    st.markdown("El PIB integrado procede de un dataset publicado por Gobernación de Caldas en datos.gov.co, no de una API directa DANE. Los grupos MinCiencias son capacidad científica, no inversión en I+D.")
    st.dataframe(pd.DataFrame(pending()),use_container_width=True,hide_index=True)
    st.markdown("Las fuentes activas son obligatorias: una caída o cambio de esquema detiene la carga y muestra error técnico y recomendación.")
st.caption("Caché de seis horas. Los datos se consultan desde las fuentes enlazadas al cargar.");
