# -*- coding: utf-8 -*-
"""Contrato de datos largo: una fila = territorio × año × indicador."""
from __future__ import annotations

import pandas as pd

from observatorio.core.normalize import norm_dept, norm_year, to_number

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
