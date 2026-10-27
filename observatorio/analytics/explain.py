# -*- coding: utf-8 -*-
"""Interpretabilidad agnóstica al modelo: SHAP (permutación) + importancia por permutación."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import shap
from sklearn.inspection import permutation_importance


@dataclass
class ShapResult:
    values: pd.DataFrame      # contribución de cada variable por observación
    data: pd.DataFrame        # valores de X explicados
    base_value: float

    def global_importance(self) -> pd.Series:
        return self.values.abs().mean().sort_values(ascending=True).rename("Media |SHAP|")


def shap_explain(pipeline, X: pd.DataFrame, max_background: int = 50, max_explain: int = 200,
                 seed: int = 42) -> ShapResult:
    """SHAP sobre el pipeline completo (escalado incluido), en unidades originales de X.

    Se usa PermutationExplainer: exacto en aditividad, válido para Ridge/Lasso/SVR/MLP por igual.
    """
    bg = shap.sample(X, min(max_background, len(X)), random_state=seed)
    Xe = X if len(X) <= max_explain else X.sample(max_explain, random_state=seed)
    explainer = shap.Explainer(pipeline.predict, shap.maskers.Independent(bg), algorithm="permutation",
                               seed=seed)
    sv = explainer(Xe, max_evals=max(2 * X.shape[1] + 1, 100))
    base = float(np.ravel(sv.base_values)[0])
    return ShapResult(pd.DataFrame(sv.values, index=Xe.index, columns=X.columns), Xe, base)


def permutation(pipeline, X, y, n_repeats: int = 30, seed: int = 42) -> pd.DataFrame:
    r = permutation_importance(pipeline, X, y, n_repeats=n_repeats, random_state=seed, scoring="r2")
    return (pd.DataFrame({"Variable": X.columns, "Caída de R²": r.importances_mean, "Desv.": r.importances_std})
            .sort_values("Caída de R²", ascending=False))


def narrative(res: ShapResult, row_label, top: int = 3) -> str:
    """Interpretación automática en lenguaje natural para una observación."""
    contrib = res.values.loc[row_label].sort_values(key=np.abs, ascending=False).head(top)
    pred = res.base_value + res.values.loc[row_label].sum()
    parts = [f"{v} {'eleva' if c > 0 else 'reduce'} la predicción en {abs(c):,.2f}" for v, c in contrib.items()]
    return (f"Predicción {pred:,.2f} frente a un valor base de {res.base_value:,.2f}. "
            + "; ".join(parts) + ".")
