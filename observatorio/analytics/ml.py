# -*- coding: utf-8 -*-
"""Aprendizaje supervisado: Ridge, Lasso, SVR (SVM) y red neuronal (MLP).

Diseño para paneles pequeños (≈33 departamentos × pocos años):
- Escalado dentro del Pipeline (sin fuga de información en la validación).
- Validación por grupos (departamento no visto) o temporal (años futuros).
- Opción de rezagar X un año: X_{t-1} -> y_t, que es predicción real y no ajuste contemporáneo.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.linear_model import LassoCV, RidgeCV
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GridSearchCV, GroupKFold
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVR

from observatorio.core.http import InsufficientDataError

SEED = 42


def make_model(kind: str) -> Pipeline:
    alphas = np.logspace(-3, 3, 50)
    est = {
        "Ridge": RidgeCV(alphas=alphas),
        "Lasso": LassoCV(alphas=alphas, max_iter=50_000, random_state=SEED, cv=5),
        "SVR (SVM)": GridSearchCV(SVR(), {"C": [0.1, 1, 10, 100], "epsilon": [0.01, 0.1, 0.5],
                                          "kernel": ["rbf", "linear"]}, cv=4),
        "Red neuronal (MLP)": MLPRegressor(hidden_layer_sizes=(32, 16), activation="relu", alpha=1e-2,
                                           learning_rate_init=1e-3, max_iter=3000, early_stopping=True,
                                           validation_fraction=0.2, n_iter_no_change=50, random_state=SEED),
    }[kind]
    return Pipeline([("scaler", StandardScaler()), ("model", est)])


MODELS = ["Ridge", "Lasso", "SVR (SVM)", "Red neuronal (MLP)"]


def supervised_frame(wide: pd.DataFrame, target: str, features: list[str], lag: int = 0
                     ) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    """Devuelve X, y y grupos (departamento). Con lag>0, X se rezaga dentro de cada departamento."""
    df = wide[[target] + features].copy().sort_index()
    if lag:
        X = df[features].groupby(level="codigo_divipola").shift(lag)
        X.columns = [f"{c} (t-{lag})" for c in features]
        df = pd.concat([df[[target]], X], axis=1)
    df = df.dropna()
    if len(df) < 20:
        raise InsufficientDataError(f"Solo {len(df)} observaciones tras rezagos/faltantes (mínimo 20).")
    return df.drop(columns=target), df[target], df.index.get_level_values("codigo_divipola").to_series(index=df.index)


@dataclass
class FitResult:
    kind: str
    pipeline: Pipeline
    X: pd.DataFrame
    y: pd.Series
    cv_scores: pd.DataFrame
    oof_pred: pd.Series
    coefs: pd.Series | None = None
    notes: list[str] = field(default_factory=list)


def _metrics(y, p) -> dict:
    return {"R²": r2_score(y, p), "RMSE": mean_squared_error(y, p) ** .5, "MAE": mean_absolute_error(y, p)}


def fit_evaluate(X: pd.DataFrame, y: pd.Series, groups: pd.Series, kind: str,
                 scheme: str = "Por departamento", n_splits: int = 5) -> FitResult:
    pipe = make_model(kind)
    years = X.index.get_level_values("anio")
    if scheme == "Temporal":
        cut = np.quantile(np.unique(years), .75)
        splits = [(np.where(years <= cut)[0], np.where(years > cut)[0])]
    else:
        splits = list(GroupKFold(n_splits=min(n_splits, groups.nunique())).split(X, y, groups))
    oof = pd.Series(np.nan, index=X.index)
    rows = []
    for k, (tr, te) in enumerate(splits, 1):
        m = clone(pipe).fit(X.iloc[tr], y.iloc[tr])
        pred = m.predict(X.iloc[te])
        oof.iloc[te] = pred
        rows.append({"Pliegue": k, "n prueba": len(te), **_metrics(y.iloc[te], pred)})
    final = pipe.fit(X, y)
    coefs, notes = None, []
    est = final.named_steps["model"]
    if hasattr(est, "coef_"):
        coefs = pd.Series(np.ravel(est.coef_), index=X.columns, name="Coef. estandarizado")
        if kind == "Lasso":
            zero = int((coefs == 0).sum())
            notes.append(f"Lasso (α={est.alpha_:.4g}) eliminó {zero} de {len(coefs)} variables.")
        else:
            notes.append(f"Ridge eligió α={est.alpha_:.4g} por validación cruzada interna.")
    if kind.startswith("SVR"):
        notes.append(f"Mejores hiperparámetros SVR: {est.best_params_}.")
    if kind.startswith("Red"):
        notes.append(f"MLP convergió en {est.n_iter_} épocas. Con n≈{len(X)} la red es un benchmark, "
                     "no un modelo superior por defecto: compárala con Ridge.")
    return FitResult(kind, final, X, y, pd.DataFrame(rows), oof, coefs, notes)


def compare(X, y, groups, scheme: str) -> pd.DataFrame:
    """Tabla resumen de todos los modelos con el mismo esquema de validación."""
    out = []
    for k in MODELS:
        r = fit_evaluate(X, y, groups, k, scheme)
        mask = r.oof_pred.notna()
        out.append({"Modelo": k, **_metrics(y[mask], r.oof_pred[mask])})
    return pd.DataFrame(out).sort_values("RMSE")
