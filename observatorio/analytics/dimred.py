# -*- coding: utf-8 -*-
"""PCA (reducción de dimensionalidad, índice sintético) y clustering no supervisado."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler


@dataclass
class PCAResult:
    explained: pd.DataFrame
    loadings: pd.DataFrame
    scores: pd.DataFrame
    index: pd.Series          # CP1 reescalado 0–100
    kmo_note: str


def run_pca(wide: pd.DataFrame, n_components: int | None = None, orient_by: str | None = None) -> PCAResult:
    Z = StandardScaler().fit_transform(wide)
    k = n_components or wide.shape[1]
    pca = PCA(n_components=k).fit(Z)
    names = [f"CP{i+1}" for i in range(k)]
    load = pd.DataFrame(pca.components_.T * np.sqrt(pca.explained_variance_), index=wide.columns, columns=names)
    scores = pd.DataFrame(pca.transform(Z), index=wide.index, columns=names)
    # El signo de un componente es arbitrario: se orienta para que 'orient_by' cargue positivo.
    ref = orient_by if orient_by in load.index else load["CP1"].abs().idxmax()
    if load.loc[ref, "CP1"] < 0:
        load["CP1"] *= -1
        scores["CP1"] *= -1
    s = scores["CP1"]
    idx = 100 * (s - s.min()) / (s.max() - s.min())
    exp = pd.DataFrame({"Componente": names, "Varianza explicada": pca.explained_variance_ratio_,
                        "Acumulada": np.cumsum(pca.explained_variance_ratio_),
                        "Autovalor": pca.explained_variance_})
    det = np.linalg.det(np.corrcoef(Z, rowvar=False))
    note = (f"Determinante de la matriz de correlación = {det:.3g}. "
            f"Criterio de Kaiser: retener {int((pca.explained_variance_ > 1).sum())} componentes (autovalor > 1).")
    return PCAResult(exp, load, scores, idx.rename("Índice sintético (0–100)"), note)


def cluster(scores: pd.DataFrame, k_range=range(2, 7)) -> tuple[pd.Series, pd.DataFrame]:
    """K-means sobre componentes; k elegido por silueta."""
    sil = []
    for k in k_range:
        if k >= len(scores):
            break
        lab = KMeans(k, n_init=20, random_state=42).fit_predict(scores)
        sil.append({"k": k, "Silueta": silhouette_score(scores, lab)})
    sil = pd.DataFrame(sil)
    best = int(sil.loc[sil["Silueta"].idxmax(), "k"])
    labels = KMeans(best, n_init=20, random_state=42).fit_predict(scores)
    return pd.Series(labels, index=scores.index, name="Clúster").astype(str), sil
