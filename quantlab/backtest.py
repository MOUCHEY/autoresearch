"""
backtest.py — moteur de simulation reproductible.  *** FICHIER PROTÉGÉ ***

Son empreinte SHA-256 est enregistrée dans evaluation.lock. L'experiment_runner refuse
de tourner si ce fichier a été modifié sans re-verrouillage humain documenté.

Hypothèses d'exécution (documentées, volontairement conservatrices)
-------------------------------------------------------------------
1. Décision à la clôture de la barre t  ->  entrée à l'OUVERTURE de la barre t+1.
2. Sortie à l'ouverture de la barre t+1+hold (sortie temporelle, pas de stop en V1 :
   un stop intrabarre exigerait de savoir si le haut ou le bas a été touché en premier,
   ce que des barres M5 ne disent pas).
3. Prix d'exécution = prix médian (mid) -/+ demi-spread -/+ slippage, plus commission :
       coût aller-retour = (spread_entrée + spread_sortie)/2 + 2*slippage + commission
4. Un trade dont la durée réelle dépasse hold*5 min + gap_slack (pause quotidienne,
   week-end, trou de données) est REFUSÉ : on ne simule pas de positions traversant
   des périodes où l'on ne pourrait pas sortir au prix prévu.
5. Une seule position à la fois : un signal reçu pendant une position est ignoré.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class CostModel:
    spread_source: str = "data"
    fixed_spread: float = 0.25
    min_spread: float = 0.10
    commission_roundturn: float = 0.07
    slippage_per_side: float = 0.05
    spread_mult: float = 1.0
    slippage_mult: float = 1.0

    @classmethod
    def from_config(cls, c: dict, spread_mult: float = 1.0, slippage_mult: float = 1.0) -> "CostModel":
        return cls(c["spread_source"], float(c["fixed_spread"]), float(c["min_spread"]),
                   float(c["commission_roundturn"]), float(c["slippage_per_side"]),
                   spread_mult, slippage_mult)

    def spread(self, bars: pd.DataFrame) -> np.ndarray:
        use_data = (self.spread_source == "data" and "spread" in bars
                    and bars["spread"].notna().mean() > 0.5)
        if use_data:
            s = bars["spread"].to_numpy(dtype=float)
            s = np.where(np.isfinite(s), s, self.fixed_spread)
        else:
            s = np.full(len(bars), self.fixed_spread)
        return np.maximum(s, self.min_spread)


def forward_outcomes(bars: pd.DataFrame, hold: int, cost: CostModel, bar_minutes: int,
                     gap_slack_minutes: float) -> dict:
    """Pour CHAQUE barre i, le résultat d'un trade décidé à la clôture de i.

    Renvoie des tableaux de longueur n (NaN si le trade est impossible) :
      entry = i+1, exit = i+1+hold, move = O[exit]-O[entry], coûts par composante.
    Sert à la fois au backtest et au test « entrées aléatoires » de l'évaluateur.
    """
    n = len(bars)
    o = bars["open"].to_numpy(dtype=float)
    tmin = ((bars.index - bars.index[0]).total_seconds() / 60.0).to_numpy()
    spr = cost.spread(bars)
    i = np.arange(n)
    e, x = i + 1, i + 1 + hold
    ok = x < n
    ec, xc = np.minimum(e, n - 1), np.minimum(x, n - 1)
    ok &= (tmin[xc] - tmin[ec]) <= hold * bar_minutes + gap_slack_minutes
    move = np.where(ok, o[xc] - o[ec], np.nan)
    spread_cost = np.where(ok, (spr[ec] + spr[xc]) / 2.0, np.nan)
    return {"valid": ok, "entry": ec, "exit": xc, "entry_px": o[ec], "exit_px": o[xc],
            "move": move, "spread_cost": spread_cost,
            "slippage_cost": np.where(ok, 2.0 * cost.slippage_per_side, np.nan),
            "commission": np.where(ok, cost.commission_roundturn, np.nan)}


def net_bps(move, direction, spread_cost, slippage_cost, commission, entry_px,
            spread_mult=1.0, slippage_mult=1.0):
    """Rendement net en points de base (1 bp = 0.01 %) du prix d'entrée."""
    c = spread_cost * spread_mult + slippage_cost * slippage_mult + commission
    return (direction * move - c) / entry_px * 1e4


def simulate(bars: pd.DataFrame, signals: pd.Series, hold: int, cost: CostModel,
             window: tuple[int, int], bar_minutes: int = 5, gap_slack_minutes: float = 30,
             one_position: bool = True, tags: pd.DataFrame | None = None) -> pd.DataFrame:
    """Simule les trades dont la barre-signal ET la sortie sont dans [window[0], window[1])."""
    fo = forward_outcomes(bars, hold, cost, bar_minutes, gap_slack_minutes)
    sig = signals.reindex(bars.index).fillna(0).to_numpy().astype(int)
    a, b = window
    pos = np.arange(len(bars))
    cand = np.flatnonzero((sig != 0) & fo["valid"] & (pos >= a) & (fo["exit"] < b))

    chosen = []
    next_free = -1
    for i in cand:                      # boucle explicite : lisible et sans ambiguïté
        if not one_position or i >= next_free:
            chosen.append(i)
            next_free = i + hold        # prochaine entrée possible à l'ouverture de la barre de sortie
    idx = np.asarray(chosen, dtype=int)

    d = sig[idx].astype(float)
    t = pd.DataFrame({
        "bar": idx,
        "signal_time": bars.index[idx],
        "entry_time": bars.index[fo["entry"][idx]],
        "exit_time": bars.index[fo["exit"][idx]],
        "direction": d.astype(int),
        "entry_px": fo["entry_px"][idx],
        "exit_px": fo["exit_px"][idx],
        "gross_pnl": d * fo["move"][idx],
        "spread_cost": fo["spread_cost"][idx] * cost.spread_mult,
        "slippage_cost": fo["slippage_cost"][idx] * cost.slippage_mult,
        "commission": fo["commission"][idx],
    })
    t["cost"] = t["spread_cost"] + t["slippage_cost"] + t["commission"]
    t["net_pnl"] = t["gross_pnl"] - t["cost"]
    t["gross_bps"] = t["gross_pnl"] / t["entry_px"] * 1e4
    t["cost_bps"] = t["cost"] / t["entry_px"] * 1e4
    t["net_bps"] = t["net_pnl"] / t["entry_px"] * 1e4
    if tags is not None:
        for c in tags.columns:
            t[c] = tags[c].to_numpy()[idx]
    return t


def stressed_net_bps(trades: pd.DataFrame, spread_mult: float, slippage_mult: float) -> np.ndarray:
    """Recalcule le net avec des coûts dégradés (les signaux ne dépendent pas des coûts,
    donc l'ensemble des trades est identique : seul le coût change)."""
    c = trades["spread_cost"] * spread_mult + trades["slippage_cost"] * slippage_mult + trades["commission"]
    return ((trades["gross_pnl"] - c) / trades["entry_px"] * 1e4).to_numpy()


def equity_curve(trades: pd.DataFrame, initial_equity: float, risk_per_trade: float,
                 max_leverage: float) -> pd.DataFrame:
    """Courbe de capital en paper trading, taille de position normalisée par la volatilité :
    un mouvement défavorable de 1 ATR coûte `risk_per_trade` du capital (levier plafonné)."""
    if len(trades) == 0:
        return pd.DataFrame(columns=["equity", "ret", "leverage"])
    atr = trades["atr"].to_numpy() if "atr" in trades else np.full(len(trades), np.nan)
    lev = risk_per_trade * trades["entry_px"].to_numpy() / atr
    lev = np.where(np.isfinite(lev), lev, 1.0)
    lev = np.minimum(lev, max_leverage)
    r = lev * trades["net_pnl"].to_numpy() / trades["entry_px"].to_numpy()
    eq = initial_equity * np.cumprod(1.0 + r)
    return pd.DataFrame({"equity": eq, "ret": r, "leverage": lev},
                        index=pd.DatetimeIndex(trades["exit_time"]))
