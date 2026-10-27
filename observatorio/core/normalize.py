# -*- coding: utf-8 -*-
"""Homologación de texto, códigos DIVIPOLA, años y números."""
from __future__ import annotations

import re
import unicodedata
from typing import Any

import pandas as pd

from observatorio.config import ALIASES, CODE, DIVIPOLA

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
