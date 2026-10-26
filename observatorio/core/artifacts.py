# -*- coding: utf-8 -*-
"""Persistencia de modelos entrenados en Colab para servirlos en la app.

Colab entrena (costoso) -> save_model(...) -> artifacts/<nombre>.joblib -> GitHub
App -> load_model(...) con st.cache_resource. Se guarda la huella de los datos para
detectar si el modelo quedó desactualizado frente al master vigente.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

ROOT = Path(__file__).resolve().parents[2] / "artifacts"


def data_fingerprint(df: pd.DataFrame) -> str:
    return hashlib.sha256(pd.util.hash_pandas_object(df, index=True).values.tobytes()).hexdigest()[:16]


def save_model(name: str, model: Any, train_data: pd.DataFrame, meta: dict | None = None) -> Path:
    ROOT.mkdir(exist_ok=True)
    path = ROOT / f"{name}.joblib"
    joblib.dump(model, path)
    info = {"name": name, "fingerprint": data_fingerprint(train_data),
            "rows": len(train_data), "columns": list(map(str, train_data.columns)),
            "saved_utc": datetime.now(timezone.utc).isoformat(), **(meta or {})}
    (ROOT / f"{name}.json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_model(name: str) -> tuple[Any, dict]:
    path = ROOT / f"{name}.joblib"
    if not path.exists():
        raise FileNotFoundError(f"No existe {path}. Entrénalo en Colab con save_model('{name}', ...).")
    meta = json.loads((ROOT / f"{name}.json").read_text(encoding="utf-8"))
    return joblib.load(path), meta
