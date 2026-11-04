"""
features.py — construction des variables explicatives.

RÈGLE D'OR : une variable à la ligne t ne doit utiliser que des informations
disponibles à la CLÔTURE de la barre t (données <= t). Jamais t+1.
Le test `tests/test_lab.py::test_features_are_causal` le vérifie automatiquement :
il recalcule les variables sur des données tronquées et exige des valeurs identiques.

Variables V1
------------
ret1        rendement logarithmique de la barre : ln(C_t / C_{t-1})
atr         Average True Range (moyenne simple sur `atr_window` barres), en USD
rv_fast     volatilité réalisée sur ~1 jour (écart-type des ret1 sur 288 barres)
rv_slow     volatilité réalisée sur ~20 jours (5760 barres)
vol_regime  rv_fast / rv_slow : > 1 = journée plus agitée que d'habitude.
            Comme la fenêtre rapide couvre une journée entière, ce ratio est peu
            pollué par la saisonnalité intrajournalière (Andersen & Bollerslev 1997).
hour        heure UTC de la barre
session     asia / london / overlap / ny (heures UTC, approximation fixe)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

SESSIONS = [("asia", 22, 7), ("london", 7, 12), ("overlap", 12, 16), ("ny", 16, 22)]


def true_range(bars: pd.DataFrame) -> pd.Series:
    prev_close = bars["close"].shift(1)
    return pd.concat([bars["high"] - bars["low"],
                      (bars["high"] - prev_close).abs(),
                      (bars["low"] - prev_close).abs()], axis=1).max(axis=1)


def session_of_hour(hour: np.ndarray) -> np.ndarray:
    out = np.empty(len(hour), dtype=object)
    for name, start, end in SESSIONS:
        m = (hour >= start) & (hour < end) if start < end else (hour >= start) | (hour < end)
        out[m] = name
    return out


def build_features(bars: pd.DataFrame, cfg_features: dict) -> pd.DataFrame:
    """Variables communes à toutes les stratégies (calculées une seule fois)."""
    f = pd.DataFrame(index=bars.index)
    f["ret1"] = np.log(bars["close"]).diff()
    f["atr"] = true_range(bars).rolling(int(cfg_features["atr_window"])).mean()
    fast, slow = int(cfg_features["vol_fast_bars"]), int(cfg_features["vol_slow_bars"])
    f["rv_fast"] = f["ret1"].rolling(fast, min_periods=fast).std()
    f["rv_slow"] = f["ret1"].rolling(slow, min_periods=slow // 2).std()
    f["vol_regime"] = f["rv_fast"] / f["rv_slow"]
    f["hour"] = bars.index.hour
    f["session"] = session_of_hour(f["hour"].to_numpy())
    return f


def donchian(bars: pd.DataFrame, lookback: int) -> tuple[pd.Series, pd.Series]:
    """Plus haut / plus bas des `lookback` barres PRÉCÉDENTES (la barre t est exclue
    grâce au shift(1), sinon une clôture ne pourrait jamais dépasser son propre plus haut)."""
    hi = bars["high"].shift(1).rolling(lookback, min_periods=lookback).max()
    lo = bars["low"].shift(1).rolling(lookback, min_periods=lookback).min()
    return hi, lo
