# -*- coding: utf-8 -*-
"""Acceso HTTP fail-fast a fuentes oficiales."""
from __future__ import annotations

from typing import Any

import requests

from observatorio.config import HEADERS, LIMIT, SODA, TIMEOUT


class DataSourceError(RuntimeError):
    """Error controlado de fuente o parseo."""


class InsufficientDataError(ValueError):
    """Los datos válidos no alcanzan para estimar un modelo con rigor."""


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
