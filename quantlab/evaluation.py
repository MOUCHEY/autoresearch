"""
evaluation.py — évaluateur et protocole de validation.  *** FICHIER PROTÉGÉ ***

Pourquoi « protégé » ?  Un agent (humain ou IA) qui cherche à améliorer un score est
tenté de modifier la règle de mesure plutôt que la stratégie. Ce fichier fixe donc :
  - le découpage chronologique train / validation / test (walk-forward, purge, embargo) ;
  - les métriques ;
  - les tests statistiques (bootstrap, entrées aléatoires, Deflated Sharpe, Holm) ;
  - la règle de décision (ACCEPT_CANDIDATE / INCONCLUSIVE / REJECT / INSUFFICIENT_DATA).
Son empreinte SHA-256 (avec celle de backtest.py) est figée dans evaluation.lock ;
experiment_runner.py refuse de tourner si elle ne correspond plus. Ce n'est pas une
sécurité absolue : la vraie garantie reste l'historique Git relu par un humain.

Références des méthodes (voir literature_review.md) :
  bootstrap stationnaire ........ Politis & Romano (1994)
  data snooping ................. White (2000), Sullivan, Timmermann & White (1999)
  Deflated Sharpe Ratio ......... Bailey & López de Prado (2014)
  purge / embargo ............... López de Prado (2018)
  correction de Holm ............ Holm (1979)
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

PROTECTED_FILES = ("evaluation.py", "backtest.py")
LOCK_FILE = "evaluation.lock"
EULER_GAMMA = 0.5772156649015329


# =============================================================================
# 1. Intégrité de l'évaluateur
# =============================================================================
def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def current_hashes(root: Path) -> dict:
    return {f: sha256_file(root / f) for f in PROTECTED_FILES}


def evaluator_hash(root: Path) -> str:
    h = current_hashes(root)
    return hashlib.sha256(json.dumps(h, sort_keys=True).encode()).hexdigest()[:12]


def verify_lock(root: Path) -> tuple[bool, str]:
    lock = root / LOCK_FILE
    if not lock.exists():
        return False, f"{LOCK_FILE} absent : l'évaluateur n'a jamais été verrouillé"
    saved = json.loads(lock.read_text())["files"]
    now = current_hashes(root)
    changed = [f for f in PROTECTED_FILES if saved.get(f) != now[f]]
    if changed:
        return False, ("fichiers protégés modifiés depuis le verrouillage : " + ", ".join(changed)
                       + ". Un humain doit relire le diff puis lancer "
                         "`python experiment_runner.py --relock \"raison\"`.")
    return True, "évaluateur intact"


def write_lock(root: Path, reason: str) -> dict:
    data = {"files": current_hashes(root), "locked_at_utc": datetime.now(timezone.utc).isoformat(),
            "reason": reason}
    (root / LOCK_FILE).write_text(json.dumps(data, indent=2) + "\n")
    return data


# =============================================================================
# 2. Découpage chronologique : développement (walk-forward) + test final verrouillé
# =============================================================================
@dataclass(frozen=True)
class Fold:
    k: int
    train: tuple[int, int]      # [début, fin[ en positions de barres
    val: tuple[int, int]


@dataclass(frozen=True)
class Splits:
    dev: tuple[int, int]
    test: tuple[int, int]
    folds: tuple[Fold, ...]
    embargo: int


def make_splits(n: int, test_fraction: float, n_folds: int, embargo: int) -> Splits:
    """Walk-forward à fenêtre croissante.

    |<-------------------- développement -------------------->|emb|<--- TEST --->|
    | bloc 0 | bloc 1 | bloc 2 | bloc 3 | bloc 4 |
    pli 1 : train = bloc 0            (moins l'embargo)   val = bloc 1
    pli 2 : train = blocs 0-1         (moins l'embargo)   val = bloc 2   ... etc.

    Purge + embargo : les `embargo` dernières barres du train sont retirées, de sorte
    qu'aucune observation d'entraînement (ni son horizon de détention) ne chevauche la
    validation. Le même écart sépare le développement du test final.
    """
    dev_end = int(n * (1 - test_fraction))
    edges = np.linspace(0, dev_end, n_folds + 2).astype(int)
    folds = tuple(Fold(k, (0, int(edges[k]) - embargo), (int(edges[k]), int(edges[k + 1])))
                  for k in range(1, n_folds + 1))
    return Splits(dev=(0, dev_end), test=(dev_end + embargo, n), folds=folds, embargo=embargo)


# =============================================================================
# 3. Outils statistiques
# =============================================================================
def stationary_bootstrap_means(x: np.ndarray, n_boot: int, block: float, seed: int) -> np.ndarray:
    """Moyennes bootstrap (Politis & Romano 1994) : rééchantillonne des blocs de longueur
    géométrique (moyenne `block`) pour respecter une éventuelle dépendance entre trades."""
    x = np.asarray(x, dtype=float)
    n = len(x)
    if n == 0:
        return np.array([np.nan])
    rng = np.random.default_rng(seed)
    p = 1.0 / max(block, 1.0)
    idx = rng.integers(0, n, n_boot)
    total = x[idx].copy()
    for _ in range(1, n):
        restart = rng.random(n_boot) < p
        idx = np.where(restart, rng.integers(0, n, n_boot), (idx + 1) % n)
        total += x[idx]
    return total / n


def random_entry_null(long_bps: np.ndarray, short_bps: np.ndarray, eligible: np.ndarray,
                      directions: np.ndarray, n_sims: int, seed: int,
                      bar_strata: np.ndarray | None = None,
                      trade_strata: np.ndarray | None = None) -> np.ndarray:
    """Distribution de l'espérance nette d'une stratégie qui entrerait AU HASARD,
    avec le même nombre de trades, le même horizon, la même proportion achat/vente,
    les mêmes coûts et sur les mêmes périodes. Contrôle la dérive du marché (l'or a
    souvent monté : une stratégie « toujours acheteuse » paraîtrait bonne sans aucun talent).

    Stratification (si bar_strata / trade_strata sont fournis) : les entrées aléatoires
    respectent la répartition des vrais trades par strate (régime de volatilité x session).
    La question devient : « le TIMING du signal apporte-t-il quelque chose, à régime et
    heure comparables ? ». Sans cela, une stratégie filtrée sur la forte volatilité serait
    comparée à un hasard moins dispersé, ce qui rendrait les p-values trop optimistes."""
    rng = np.random.default_rng(seed)
    k = len(directions)
    pool = np.flatnonzero(eligible)
    if k == 0 or len(pool) < k:
        return np.array([np.nan])
    if bar_strata is None or trade_strata is None:
        plan = [(pool, k)]
    else:
        plan = []
        for s_val, cnt in zip(*np.unique(trade_strata, return_counts=True)):
            p = pool[bar_strata[pool] == s_val]
            plan.append((p if len(p) else pool, int(cnt)))
    out = np.empty(n_sims)
    for s in range(n_sims):
        pick = np.concatenate([rng.choice(p, size=c, replace=len(p) < c) for p, c in plan])
        d = rng.permutation(directions)
        out[s] = np.where(d > 0, long_bps[pick], short_bps[pick]).mean()
    return out


def deflated_sharpe(returns: np.ndarray, n_trials: int, sr_var_trials: float) -> dict:
    """Deflated Sharpe Ratio (Bailey & López de Prado 2014), à la fréquence des TRADES.

    Probabilité que le vrai Sharpe soit > au Sharpe maximal attendu parmi `n_trials`
    essais SANS talent. n_trials = 1 -> Probabilistic Sharpe Ratio (seuil 0).
    """
    r = np.asarray(returns, dtype=float)
    T = len(r)
    if T < 3 or r.std(ddof=1) == 0:
        return {"sr_trade": np.nan, "sr0": np.nan, "dsr": np.nan}
    sr = r.mean() / r.std(ddof=1)
    skew = stats.skew(r)
    kurt = stats.kurtosis(r, fisher=False)
    if n_trials > 1 and sr_var_trials > 0:
        emax = ((1 - EULER_GAMMA) * stats.norm.ppf(1 - 1 / n_trials)
                + EULER_GAMMA * stats.norm.ppf(1 - 1 / (n_trials * np.e)))
        sr0 = np.sqrt(sr_var_trials) * emax
    else:
        sr0 = 0.0
    denom = np.sqrt(max(1 - skew * sr + (kurt - 1) / 4 * sr ** 2, 1e-12))
    return {"sr_trade": float(sr), "sr0": float(sr0),
            "dsr": float(stats.norm.cdf((sr - sr0) * np.sqrt(T - 1) / denom))}


def holm_adjust(pvals) -> np.ndarray:
    """Correction de Holm-Bonferroni : contrôle la probabilité d'au moins un faux positif
    parmi TOUTES les hypothèses testées (tests multiples)."""
    p = np.asarray(pvals, dtype=float)
    m = len(p)
    order = np.argsort(p)
    adj = np.empty(m)
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, (m - rank) * p[i])
        adj[i] = min(running, 1.0)
    return adj


# =============================================================================
# 4. Métriques
# =============================================================================
def _max_consecutive(mask: np.ndarray) -> int:
    best = cur = 0
    for v in mask:
        cur = cur + 1 if v else 0
        best = max(best, cur)
    return best


def daily_returns(eq: pd.DataFrame) -> pd.Series:
    if len(eq) == 0:
        return pd.Series(dtype=float)
    r = (1 + eq["ret"]).groupby(eq.index.normalize()).prod() - 1
    days = pd.bdate_range(r.index.min(), r.index.max(), tz=r.index.tz)
    return r.reindex(days, fill_value=0.0)


def trade_metrics(trades: pd.DataFrame, eq: pd.DataFrame, ann_days: int) -> dict:
    n = len(trades)
    m: dict = {"n_trades": n}
    if n == 0:
        return m
    net, gross, cost = trades["net_bps"].to_numpy(), trades["gross_bps"].to_numpy(), trades["cost_bps"].to_numpy()
    wins, losses = net[net > 0], net[net <= 0]
    sd = net.std(ddof=1) if n > 1 else np.nan
    m.update({
        "long_frac": float((trades["direction"] > 0).mean()),
        "net_exp_bps": float(net.mean()),
        "gross_exp_bps": float(gross.mean()),
        "cost_bps": float(cost.mean()),
        "net_std_bps": float(sd),
        "t_stat": float(net.mean() / (sd / np.sqrt(n))) if n > 1 and sd > 0 else np.nan,
        "gross_t_stat": float(gross.mean() / (gross.std(ddof=1) / np.sqrt(n))) if n > 1 else np.nan,
        "net_exp_usd_per_oz": float(trades["net_pnl"].mean()),
        "win_rate": float((net > 0).mean()),
        "avg_win_bps": float(wins.mean()) if len(wins) else 0.0,
        "avg_loss_bps": float(losses.mean()) if len(losses) else 0.0,
        "payoff_ratio": float(wins.mean() / -losses.mean()) if len(wins) and len(losses) and losses.mean() < 0 else np.nan,
        "profit_factor": float(wins.sum() / -losses.sum()) if len(losses) and losses.sum() < 0 else np.inf,
        "max_consec_losses": _max_consecutive(net <= 0),
        "cost_share_of_abs_gross": float(cost.sum() / max(np.abs(gross).sum(), 1e-12)),
    })
    span_days = max((trades["exit_time"].max() - trades["entry_time"].min()).days, 1)
    m["trades_per_day"] = float(n / (span_days * 5 / 7))
    if len(eq):
        dd = eq["equity"] / eq["equity"].cummax() - 1
        dr = daily_returns(eq)
        downside = dr[dr < 0]
        m["total_return_pct"] = float((np.prod(1 + eq["ret"]) - 1) * 100)
        m["max_dd_pct"] = float(dd.min() * 100)
        m["sharpe_ann"] = float(dr.mean() / dr.std(ddof=1) * np.sqrt(ann_days)) if dr.std(ddof=1) > 0 else np.nan
        dsd = np.sqrt((np.minimum(dr, 0) ** 2).mean())
        m["sortino_ann"] = float(dr.mean() / dsd * np.sqrt(ann_days)) if dsd > 0 else np.nan
        m["avg_leverage"] = float(eq["leverage"].mean())
        m["n_losing_days"] = int(len(downside))
    return m


def group_breakdown(trades: pd.DataFrame, col: str) -> dict:
    if len(trades) == 0 or col not in trades:
        return {}
    g = trades.groupby(col, observed=True)
    out = {}
    for key, d in g:
        x = d["net_bps"]
        out[str(key)] = {"n": int(len(d)), "net_exp_bps": round(float(x.mean()), 3),
                         "gross_exp_bps": round(float(d["gross_bps"].mean()), 3),
                         "t_stat": round(float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))), 2) if len(x) > 2 and x.std() > 0 else None}
    return out


# =============================================================================
# 5. Règle de décision (pré-enregistrée)
# =============================================================================
def decide(m: dict, rules: dict, has_baseline: bool) -> tuple[str, dict]:
    checks = {
        "enough_trades": m.get("n_trades", 0) >= rules["min_trades"],
        "net_ci_above_zero": m.get("ci_low_bps", -np.inf) > 0,
        "beats_random_entries_holm": m.get("p_null_holm", 1.0) < rules["alpha"],
        "profit_factor_ok": m.get("profit_factor", 0) >= rules["min_profit_factor"],
        "stable_across_folds": m.get("frac_folds_positive", 0) >= rules["min_fold_positive_frac"],
        "survives_combined_stress": m.get("stress_combined_net_bps", -np.inf) > 0,
    }
    if has_baseline:
        checks["beats_baseline"] = (m.get("delta_vs_baseline_bps", -np.inf) > 0
                                    and m.get("p_vs_baseline", 1.0) < rules["alpha"])
    if not checks["enough_trades"]:
        decision = "INSUFFICIENT_DATA"
    elif all(checks.values()):
        decision = "ACCEPT_CANDIDATE"
    elif m.get("net_exp_bps", -1) > 0 and checks["net_ci_above_zero"]:
        decision = "INCONCLUSIVE"
    else:
        decision = "REJECT"
    return decision, checks


def sensitivity_verdict(net_values: list[float]) -> dict:
    v = np.asarray(net_values, dtype=float)
    frac_pos = float((v > 0).mean())
    return {"frac_positive": frac_pos, "median_net_bps": float(np.median(v)),
            "min_net_bps": float(v.min()), "max_net_bps": float(v.max()),
            "verdict": "ROBUST" if frac_pos >= 0.7 and np.median(v) > 0 else "FRAGILE_OR_NULL"}
