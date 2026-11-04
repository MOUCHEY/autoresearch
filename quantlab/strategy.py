"""
strategy.py — stratégies expérimentales (fichier MODIFIABLE par l'agent de recherche).

Contrat d'une stratégie
-----------------------
- `fit(bars, feats, train_mask)` : apprend ses paramètres UNIQUEMENT sur les barres
  où train_mask est vrai (ex. un seuil de volatilité). Ne touche jamais au futur.
- `signals(bars, feats)` : renvoie une série d'entiers {-1, 0, +1} indexée comme `bars`.
  signal[t] = décision prise à la CLÔTURE de la barre t. Le moteur de backtest
  l'exécute à l'OUVERTURE de la barre t+1 (jamais au prix de clôture déjà « vu »).
- `hold` : durée de détention en barres (sortie à l'ouverture de t+1+hold).

Ce fichier ne calcule ni P&L ni métrique : c'est le rôle de backtest.py et
evaluation.py, protégés contre les modifications (voir evaluation.lock).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from features import donchian


class Strategy:
    name = "base"

    def __init__(self, **params):
        self.params = dict(params)
        self.fitted_: dict = {}

    @property
    def hold(self) -> int:
        return int(self.params["hold"])

    def fit(self, bars: pd.DataFrame, feats: pd.DataFrame, train_mask: np.ndarray) -> "Strategy":
        return self

    def signals(self, bars: pd.DataFrame, feats: pd.DataFrame) -> pd.Series:
        raise NotImplementedError


class Breakout(Strategy):
    """Cassure de canal de Donchian.

    mode="follow" : achat si clôture > plus haut des N barres précédentes, vente si < plus bas
                    (hypothèse A : momentum / continuation).
    mode="fade"   : signe inversé (hypothèse B : retour à la moyenne après un extrême).
    """
    name = "breakout"

    def signals(self, bars, feats):
        n = int(self.params["lookback"])
        hi, lo = donchian(bars, n)
        s = np.where(bars["close"] > hi, 1, np.where(bars["close"] < lo, -1, 0))
        if self.params.get("mode", "follow") == "fade":
            s = -s
        return pd.Series(s.astype(np.int8), index=bars.index)


class VolFilteredBreakout(Breakout):
    """Même cassure, filtrée par le régime de volatilité.

    Le seuil est le quantile `quantile` de feats['vol_regime'] calculé sur le TRAIN
    du pli courant (walk-forward) : il n'est jamais estimé sur la période évaluée.
    regime="high" : on ne garde que vol_regime > seuil ; regime="low" : vol_regime < seuil.
    """
    name = "vol_breakout"

    def fit(self, bars, feats, train_mask):
        v = feats["vol_regime"].to_numpy()[train_mask]
        v = v[np.isfinite(v)]
        if len(v) < 1000:
            raise ValueError("pas assez de barres d'entraînement pour estimer le seuil de volatilité")
        self.fitted_["threshold"] = float(np.quantile(v, float(self.params["quantile"])))
        return self

    def signals(self, bars, feats):
        base = super().signals(bars, feats).to_numpy()
        v = feats["vol_regime"].to_numpy()
        thr = self.fitted_["threshold"]
        keep = (v > thr) if self.params["regime"] == "high" else (v < thr)
        keep &= np.isfinite(v)
        return pd.Series(np.where(keep, base, 0).astype(np.int8), index=bars.index)


REGISTRY = {cls.name: cls for cls in (Breakout, VolFilteredBreakout)}


def make_strategy(name: str, params: dict) -> Strategy:
    if name not in REGISTRY:
        raise KeyError(f"stratégie inconnue '{name}'. Disponibles : {sorted(REGISTRY)}")
    return REGISTRY[name](**params)
