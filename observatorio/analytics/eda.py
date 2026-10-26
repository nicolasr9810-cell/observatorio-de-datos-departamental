# -*- coding: utf-8 -*-
"""EDA automatizado sobre el contrato largo o una matriz ancha."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats


def coverage(master: pd.DataFrame) -> pd.DataFrame:
    """Departamentos con dato por indicador y año (mapa de calor de cobertura)."""
    return master.pivot_table(index="indicador", columns="anio", values="codigo_divipola",
                              aggfunc="nunique").fillna(0).astype(int)


def profile(wide: pd.DataFrame) -> pd.DataFrame:
    """Estadísticos descriptivos + forma + normalidad + atípicos por variable."""
    rows = []
    for col in wide.columns:
        s = wide[col].dropna()
        if len(s) < 3:
            continue
        q1, q3 = s.quantile([.25, .75])
        iqr = q3 - q1
        out = ((s < q1 - 1.5 * iqr) | (s > q3 + 1.5 * iqr)).sum()
        jb_p = stats.jarque_bera(s).pvalue if len(s) >= 8 else np.nan
        sw_p = stats.shapiro(s).pvalue if 3 <= len(s) <= 5000 else np.nan
        rows.append({
            "Variable": col, "n": len(s), "Faltantes": int(wide[col].isna().sum()),
            "Media": s.mean(), "Mediana": s.median(), "Desv. est.": s.std(),
            "CV": s.std() / abs(s.mean()) if s.mean() else np.nan,
            "Mín": s.min(), "Máx": s.max(), "Asimetría": stats.skew(s), "Curtosis": stats.kurtosis(s),
            "Atípicos IQR": int(out), "p Shapiro-Wilk": sw_p, "p Jarque-Bera": jb_p,
            "¿Normal (5%)?": "Sí" if sw_p >= .05 else "No" if pd.notna(sw_p) else "—",
        })
    return pd.DataFrame(rows)


def correlations(wide: pd.DataFrame, method: str = "spearman") -> tuple[pd.DataFrame, pd.DataFrame]:
    """Matriz de correlación y matriz de p-valores (pares completos)."""
    cols = list(wide.columns)
    r = pd.DataFrame(np.nan, index=cols, columns=cols)
    p = r.copy()
    fn = stats.spearmanr if method == "spearman" else stats.pearsonr
    for i, a in enumerate(cols):
        for b in cols[i:]:
            pair = wide[[a, b]].dropna()
            if len(pair) < 4:
                continue
            if a == b:
                r.loc[a, b], p.loc[a, b] = 1.0, 0.0
                continue
            res = fn(pair[a], pair[b])
            r.loc[a, b] = r.loc[b, a] = res.statistic
            p.loc[a, b] = p.loc[b, a] = res.pvalue
    return r, p


def vif(wide: pd.DataFrame) -> pd.DataFrame:
    """Factor de inflación de varianza: alerta de multicolinealidad antes de regresar."""
    from statsmodels.stats.outliers_influence import variance_inflation_factor
    from statsmodels.tools import add_constant
    X = add_constant(wide.dropna())
    return pd.DataFrame({"Variable": wide.columns,
                         "VIF": [variance_inflation_factor(X.values, i + 1) for i in range(wide.shape[1])]})


def auto_insights(prof: pd.DataFrame, corr: pd.DataFrame, top: int = 3) -> list[str]:
    """Hallazgos en texto plano para la UI."""
    msgs = []
    for _, r in prof.iterrows():
        if abs(r["Asimetría"]) > 1:
            msgs.append(f"**{r['Variable']}** es muy asimétrica ({r['Asimetría']:.2f}); considera log antes de modelar.")
        if r["Atípicos IQR"]:
            msgs.append(f"**{r['Variable']}** tiene {r['Atípicos IQR']} atípicos por IQR.")
    tri = corr.where(np.triu(np.ones(corr.shape, bool), 1)).stack()
    for (a, b), v in tri.abs().sort_values(ascending=False).head(top).items():
        msgs.append(f"Correlación fuerte entre **{a}** y **{b}**: {corr.loc[a, b]:+.2f}.")
    return msgs
