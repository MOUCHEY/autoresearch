"""
experiment_runner.py — boucle AutoResearch BUDGÉTÉE (jamais illimitée).

Cycle d'une expérience
----------------------
 1. hypothèse falsifiable (écrite dans research_config.yaml AVANT le résultat)
 2. données + variables (data_loader.py, features.py)
 3. walk-forward : pour chaque pli, fit sur le train, signaux, backtest sur la validation
 4. évaluation protégée (evaluation.py) : métriques, IC bootstrap, entrées aléatoires,
    scénarios de coûts dégradés, stabilité par pli / régime / session, Deflated Sharpe,
    correction de Holm sur toutes les expériences déjà faites
 5. comparaison avec la référence -> décision (ACCEPT_CANDIDATE / INCONCLUSIVE / REJECT)
 6. traçabilité : results.csv (+ commit Git, hash évaluateur, hash données, hash config)
 7. proposition automatique de la prochaine expérience (research_memory.md)

Le jeu de TEST FINAL n'est jamais utilisé ici, sauf commande explicite --final-test,
utilisable une seule fois (trace dans runs/test_access.json).

Usage
-----
    python experiment_runner.py                  # expériences pré-enregistrées (budget)
    python experiment_runner.py --auto 2         # + jusqu'à 2 propositions automatiques
    python experiment_runner.py --only E02       # une seule expérience
    python experiment_runner.py --control positive   # contrôle positif (démo avec effet planté)
    python experiment_runner.py --final-test E02 # évaluation UNIQUE sur le test verrouillé
    python experiment_runner.py --relock "raison"    # (humain) re-verrouille l'évaluateur
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import signal
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

import backtest as bt
import evaluation as ev
from data_loader import load_config, load_market_data
from features import build_features
from strategy import make_strategy

ROOT = Path(__file__).resolve().parent
RUNS = ROOT / "runs"
RESULTS = ROOT / "results.csv"
MEMORY = ROOT / "research_memory.md"
REPORT = ROOT / "report.md"
TEST_ACCESS = RUNS / "test_access.json"

RESULT_COLUMNS = [
    "exp_id", "run_utc", "data_mode", "data_hash", "symbol", "timeframe", "split",
    "git_commit", "git_dirty", "evaluator_hash", "config_hash",
    "name", "type", "strategy", "params", "baseline", "n_trials",
    "n_trades", "long_frac", "net_exp_bps", "ci_low_bps", "ci_high_bps", "gross_exp_bps",
    "gross_t_stat", "cost_bps", "t_stat", "profit_factor", "win_rate", "payoff_ratio",
    "max_consec_losses", "trades_per_day", "max_dd_pct", "sharpe_ann", "sortino_ann",
    "frac_folds_positive", "null_mean_bps", "p_null", "p_null_holm", "sr_trade", "dsr",
    "n_trials_cumulative",
    "stress_wide_spread_net_bps", "stress_high_slippage_net_bps", "stress_combined_net_bps",
    "delta_vs_baseline_bps", "p_vs_baseline", "decision", "keep", "duration_s", "error",
    "hypothesis",
]


# =============================================================================
# Traçabilité
# =============================================================================
def git_info(root: Path) -> tuple[str, bool]:
    try:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=root,
                                capture_output=True, text=True, check=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "*.py", "*.yaml"],
                                    cwd=root, capture_output=True, text=True).stdout.strip())
        return commit, dirty
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "nogit", True


def config_hash(cfg: dict) -> str:
    return hashlib.sha256(json.dumps(cfg, sort_keys=True, default=str).encode()).hexdigest()[:12]


def load_results(path: Path) -> pd.DataFrame:
    if path.exists() and path.stat().st_size > 0:
        return pd.read_csv(path)
    return pd.DataFrame(columns=RESULT_COLUMNS)


def append_result(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame([{c: row.get(c) for c in RESULT_COLUMNS}])
    df.to_csv(path, mode="a", header=not (path.exists() and path.stat().st_size > 0), index=False)


def _round(d: dict, nd: int = 4) -> dict:
    out = {}
    for k, v in d.items():
        if isinstance(v, (float, np.floating)):
            out[k] = None if not np.isfinite(v) else round(float(v), nd)
        elif isinstance(v, (np.integer,)):
            out[k] = int(v)
        elif isinstance(v, (np.bool_,)):
            out[k] = bool(v)
        else:
            out[k] = v
    return out


@contextlib.contextmanager
def time_limit(seconds: int):
    """Coupe une expérience trop longue (budget de calcul). SIGALRM : Linux / macOS."""
    if not hasattr(signal, "SIGALRM") or seconds <= 0:
        yield
        return

    def _raise(signum, frame):
        raise TimeoutError(f"budget de {seconds} s dépassé")
    old = signal.signal(signal.SIGALRM, _raise)
    signal.alarm(int(seconds))
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)


# =============================================================================
# Laboratoire
# =============================================================================
class Lab:
    def __init__(self, cfg: dict, force_mode: str | None = None, results_path: Path = RESULTS,
                 write_docs: bool = True, label_suffix: str = ""):
        self.cfg = cfg
        self.results_path = results_path
        self.write_docs = write_docs
        ok, msg = ev.verify_lock(ROOT)
        if not ok:
            raise SystemExit(f"ARRÊT — intégrité de l'évaluateur : {msg}")
        self.evaluator_hash = ev.evaluator_hash(ROOT)
        self.commit, self.dirty = git_info(ROOT)
        self.cfg_hash = config_hash(cfg)

        t0 = time.time()
        self.md = load_market_data(cfg, ROOT, force_mode)
        self.mode = self.md.label + label_suffix
        self.bars = self.md.bars
        self.feats = build_features(self.bars, cfg["features"])
        v = cfg["validation"]
        self.splits = ev.make_splits(len(self.bars), float(v["test_fraction"]), int(v["n_folds"]),
                                     int(v["embargo_bars"]))
        self.cost = bt.CostModel.from_config(cfg["costs"])
        ex = cfg["execution"]
        self.bar_minutes, self.slack = int(ex["bar_minutes"]), float(ex["gap_slack_minutes"])
        self.one_pos = bool(ex["one_position_at_a_time"])
        self.tags = self.feats[["atr", "vol_regime", "hour", "session"]]
        # Terciles de volatilité pour l'analyse par régime : estimés sur le train du 1er pli
        tr = self.splits.folds[0].train
        vr = self.feats["vol_regime"].iloc[tr[0]:tr[1]].dropna()
        self.vol_terciles = (float(vr.quantile(1 / 3)), float(vr.quantile(2 / 3)))
        # Strates (tercile de volatilité x session) pour le test « entrées aléatoires »
        terc = np.digitize(self.feats["vol_regime"].to_numpy(), self.vol_terciles)
        sess = pd.Categorical(self.feats["session"], categories=["asia", "london", "overlap", "ny"]).codes
        self.bar_strata = terc * 10 + sess
        self.seed = int(cfg["project"]["seed"])
        self._banner(time.time() - t0)

    # ------------------------------------------------------------------ affichage
    def _banner(self, dt: float):
        b, s = self.bars, self.splits
        line = "=" * 78
        print(line)
        if self.md.is_demo:
            print("  /!\\  MODE DÉMONSTRATION — DONNÉES SYNTHÉTIQUES — AUCUNE VALEUR HISTORIQUE  /!\\")
            print("  Les performances ci-dessous NE SONT PAS des résultats de marché réels.")
        else:
            print("  DONNÉES HISTORIQUES RÉELLES")
        print(line)
        print(f"  {self.md.symbol} {self.md.timeframe} | source={self.md.source} | hash={self.md.data_hash}")
        print(f"  {len(b):,} barres du {b.index[0]} au {b.index[-1]} (chargement {dt:.1f} s)")
        for w in self.md.quality.get("warnings", []):
            print(f"  [qualité] {w}")
        print(f"  Développement : {b.index[s.dev[0]].date()} -> {b.index[s.dev[1] - 1].date()}"
              f" | TEST verrouillé : {b.index[s.test[0]].date()} -> {b.index[s.test[1] - 1].date()}")
        for f in s.folds:
            print(f"    pli {f.k}: train -> {b.index[f.train[1] - 1].date()} | "
                  f"validation {b.index[f.val[0]].date()} -> {b.index[f.val[1] - 1].date()}")
        print(f"  commit={self.commit}{' (modifs non commitées)' if self.dirty else ''} "
              f"évaluateur={self.evaluator_hash} config={self.cfg_hash}")
        print(line)

    # ------------------------------------------------------------------ simulation
    def walk_forward(self, strategy: str, params: dict, windows=None) -> tuple[pd.DataFrame, list]:
        """Pour chaque pli : fit sur le train UNIQUEMENT, backtest sur la validation."""
        trades, fitted = [], []
        plan = windows or [(f.k, f.train, f.val) for f in self.splits.folds]
        for k, train, val in plan:
            strat = make_strategy(strategy, params)
            mask = np.zeros(len(self.bars), dtype=bool)
            mask[train[0]:train[1]] = True
            strat.fit(self.bars, self.feats, mask)
            sig = strat.signals(self.bars, self.feats)
            t = bt.simulate(self.bars, sig, strat.hold, self.cost, val, self.bar_minutes,
                            self.slack, self.one_pos, self.tags)
            t["fold"] = k
            trades.append(t)
            fitted.append({"fold": k, **_round(strat.fitted_)})
        return pd.concat(trades, ignore_index=True), fitted

    def null_pool(self, hold: int, windows) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        fo = bt.forward_outcomes(self.bars, hold, self.cost, self.bar_minutes, self.slack)
        args = (fo["spread_cost"], fo["slippage_cost"], fo["commission"], fo["entry_px"])
        long_bps = bt.net_bps(fo["move"], 1.0, *args)
        short_bps = bt.net_bps(fo["move"], -1.0, *args)
        pos = np.arange(len(self.bars))
        elig = np.zeros(len(self.bars), dtype=bool)
        for a, b in windows:
            elig |= (pos >= a) & (fo["exit"] < b)
        elig &= fo["valid"] & np.isfinite(self.feats["vol_regime"].to_numpy())
        return long_bps, short_bps, elig

    # ------------------------------------------------------------------ évaluation
    def score(self, exp: dict, trades: pd.DataFrame, windows, prior: pd.DataFrame,
              baseline_trades: pd.DataFrame | None, n_trials_this: int = 1) -> tuple[dict, dict]:
        e = self.cfg["evaluation"]
        r = self.cfg["risk"]
        eq = bt.equity_curve(trades, float(r["initial_equity"]), float(r["risk_per_trade"]),
                             float(r["max_leverage"]))
        m = ev.trade_metrics(trades, eq, int(e["annualization_days"]))
        extra: dict = {}
        if len(trades) == 0:
            return m, extra
        net = trades["net_bps"].to_numpy()
        boots = ev.stationary_bootstrap_means(net, int(e["n_bootstrap"]), float(e["bootstrap_block"]), self.seed)
        a = float(e["alpha"])
        m["ci_low_bps"], m["ci_high_bps"] = (float(np.quantile(boots, a / 2)), float(np.quantile(boots, 1 - a / 2)))

        hold = int(json.loads(exp["params"])["hold"]) if isinstance(exp["params"], str) else int(exp["params"]["hold"])
        lb, sb, elig = self.null_pool(hold, windows)
        null = ev.random_entry_null(lb, sb, elig, trades["direction"].to_numpy(), int(e["n_null_sims"]), self.seed,
                                    self.bar_strata, self.bar_strata[trades["bar"].to_numpy()])
        m["null_mean_bps"] = float(np.nanmean(null))
        m["p_null"] = float((1 + np.sum(null >= m["net_exp_bps"])) / (1 + len(null)))
        extra["null_quantiles_bps"] = {q: round(float(np.quantile(null, q)), 4) for q in (0.025, 0.5, 0.975)}

        for name, sc in self.cfg["costs"]["stress"].items():
            m[f"stress_{name}_net_bps"] = float(bt.stressed_net_bps(trades, sc["spread_mult"], sc["slippage_mult"]).mean())

        per_fold = trades.groupby("fold")["net_bps"].mean()
        m["frac_folds_positive"] = float((per_fold > 0).mean())
        extra["by_fold"] = ev.group_breakdown(trades, "fold")
        extra["by_session"] = ev.group_breakdown(trades, "session")
        lo, hi = self.vol_terciles
        trades = trades.assign(vol_tercile=pd.cut(trades["vol_regime"], [-np.inf, lo, hi, np.inf],
                                                  labels=["1_low", "2_mid", "3_high"]))
        extra["by_vol_tercile"] = ev.group_breakdown(trades, "vol_tercile")
        extra["by_direction"] = ev.group_breakdown(trades, "direction")

        if baseline_trades is not None and len(baseline_trades):
            m["delta_vs_baseline_bps"] = m["net_exp_bps"] - float(baseline_trades["net_bps"].mean())
            same_entries = set(trades["entry_time"])
            comp = baseline_trades[~baseline_trades["entry_time"].isin(same_entries)]["net_bps"]
            ref = comp if len(comp) > 30 else baseline_trades["net_bps"]
            tt = ev.stats.ttest_ind(net, ref.to_numpy(), equal_var=False, alternative="greater")
            m["p_vs_baseline"] = float(tt.pvalue)
            extra["baseline_test"] = ("Welch unilatéral : trades retenus vs trades de la référence écartés "
                                      f"par le filtre (n={len(comp)})") if len(comp) > 30 else "Welch vs référence"

        # Tests multiples : TOUTES les configurations déjà évaluées sur ces données comptent.
        #  - Holm sur les p-values « entrées aléatoires » ; chaque configuration d'une analyse
        #    de sensibilité (sans p-value propre) est comptée comme un test de p = 1 (conservateur).
        #  - Deflated Sharpe : N = nombre cumulé d'essais, variance des Sharpe observés.
        prev = prior[prior["split"] == "DEV"] if len(prior) else prior
        tested = prev[prev["p_null"].notna()] if len(prev) else prev
        untested = int(prev.loc[prev["p_null"].isna(), "n_trials"].fillna(0).astype(int).sum()) if len(prev) else 0
        pvals = (list(tested["p_null"].astype(float)) if len(tested) else []) + [1.0] * untested + [m["p_null"]]
        m["p_null_holm"] = float(ev.holm_adjust(pvals)[-1])
        n_trials = (int(prev["n_trials"].fillna(1).astype(int).sum()) if len(prev) else 0) + n_trials_this
        srs = list(tested["sr_trade"].astype(float)) if len(tested) and "sr_trade" in tested else []
        dsr = ev.deflated_sharpe(net, n_trials, 0.0)
        sr_all = [s for s in srs + [dsr["sr_trade"]] if np.isfinite(s)]
        sr_var = float(np.var(sr_all, ddof=1)) if len(sr_all) > 1 else 0.0
        dsr = ev.deflated_sharpe(net, n_trials, sr_var)
        m["sr_trade"], m["dsr_sr0"], m["dsr"] = dsr["sr_trade"], dsr["sr0"], dsr["dsr"]
        m["n_trials"] = n_trials_this
        m["n_trials_cumulative"] = n_trials
        return m, extra

    # ------------------------------------------------------------------ une expérience
    def run_experiment(self, exp: dict) -> dict:
        prior = self._prior()
        t0 = time.time()
        params = exp.get("params", {})
        row = {"exp_id": exp["id"], "run_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "data_mode": self.mode, "data_hash": self.md.data_hash, "symbol": self.md.symbol,
               "timeframe": self.md.timeframe, "split": "DEV", "git_commit": self.commit,
               "git_dirty": self.dirty, "evaluator_hash": self.evaluator_hash, "config_hash": self.cfg_hash,
               "name": exp.get("name"), "type": exp.get("type", "single"), "strategy": exp.get("strategy"),
               "params": json.dumps(params, sort_keys=True), "baseline": exp.get("baseline"),
               "hypothesis": " ".join(str(exp.get("hypothesis", "")).split())}
        print(f"\n>>> {exp['id']} {exp.get('name')} [{row['type']}] {row['strategy']} {row['params']}")
        summary: dict = {"experiment": {k: v for k, v in exp.items()}, "data_mode": self.mode,
                         "data_hash": self.md.data_hash, "is_demo": self.md.is_demo}
        try:
            with time_limit(int(self.cfg["budget"]["max_seconds_per_experiment"])):
                if row["type"] == "sensitivity":
                    m, extra = self._run_sensitivity(exp, prior)
                else:
                    m, extra = self._run_single(exp, prior)
            row.update(_round(m, 6))
            summary["metrics"] = _round(m, 6)
            summary.update(extra)
        except Exception as exc:  # une erreur est un résultat : on la trace
            row["decision"], row["keep"] = "ERROR", False
            row["error"] = f"{type(exc).__name__}: {exc}"
            summary["error"] = traceback.format_exc()
            print(f"    ERREUR : {row['error']}")
        if row["type"] == "sensitivity":
            row["strategy"] = exp.get("strategy")
            row["params"] = json.dumps({"base": exp.get("base"), "grid": exp.get("grid")}, sort_keys=True)
        row["duration_s"] = round(time.time() - t0, 2)
        out = RUNS / exp["id"]
        out.mkdir(parents=True, exist_ok=True)
        summary["row"] = row
        (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str, ensure_ascii=False))
        append_result(self.results_path, row)
        self._print_row(row)
        return row

    def _windows(self):
        return [f.val for f in self.splits.folds]

    def _run_single(self, exp, prior):
        trades, fitted = self.walk_forward(exp["strategy"], exp["params"])
        (RUNS / exp["id"]).mkdir(parents=True, exist_ok=True)
        trades.to_csv(RUNS / exp["id"] / "trades.csv", index=False)
        base_trades = None
        if exp.get("baseline"):
            bspec = self._find_spec(exp["baseline"])
            base_trades, _ = self.walk_forward(bspec["strategy"], bspec["params"])
        m, extra = self.score(exp, trades, self._windows(), prior, base_trades)
        decision, checks = ev.decide(m, self.cfg["evaluation"], base_trades is not None)
        m["decision"], m["keep"] = decision, decision == "ACCEPT_CANDIDATE"
        extra["checks"] = checks
        extra["fitted_per_fold"] = fitted
        extra["trades_path"] = str((RUNS / exp["id"] / "trades.csv").relative_to(ROOT))
        return m, extra

    def _run_sensitivity(self, exp, prior):
        base = self._find_spec(exp["base"])
        grid = exp["grid"]
        keys = sorted(grid)
        table = []
        for combo in product(*[grid[k] for k in keys]):
            params = {**base["params"], **dict(zip(keys, combo))}
            t, _ = self.walk_forward(base["strategy"], params)
            table.append({**dict(zip(keys, combo)), "n_trades": int(len(t)),
                          "net_exp_bps": round(float(t["net_bps"].mean()), 4) if len(t) else None,
                          "gross_exp_bps": round(float(t["gross_bps"].mean()), 4) if len(t) else None,
                          "t_stat": round(float(t["net_bps"].mean() / (t["net_bps"].std(ddof=1) / np.sqrt(len(t)))), 2) if len(t) > 2 else None})
            print(f"    {dict(zip(keys, combo))}: n={len(t)} net={table[-1]['net_exp_bps']} bps")
        verdict = ev.sensitivity_verdict([r["net_exp_bps"] for r in table if r["net_exp_bps"] is not None])
        m = {"n_trades": int(sum(r["n_trades"] for r in table)),
             "net_exp_bps": verdict["median_net_bps"], "n_trials": len(table),
             "decision": verdict["verdict"], "keep": False}
        exp["strategy"], exp["params"] = base["strategy"], base["params"]
        return m, {"grid_table": table, "sensitivity": verdict, "base_experiment": exp["base"]}

    # ------------------------------------------------------------------ test final
    def final_test(self, exp_id: str, force: bool = False, allow_retest: bool = False) -> dict:
        if TEST_ACCESS.exists() and not allow_retest:
            raise SystemExit(f"Le test final a déjà été utilisé ({TEST_ACCESS.read_text().strip()}). "
                             "Le réutiliser le contaminerait. --allow-retest pour forcer (sera tracé).")
        prior = self._prior()
        row = prior[(prior["exp_id"] == exp_id) & (prior["split"] == "DEV")]
        if row.empty:
            raise SystemExit(f"{exp_id} n'a pas été évaluée en développement.")
        if row.iloc[-1]["decision"] != "ACCEPT_CANDIDATE" and not force:
            raise SystemExit(f"{exp_id} n'est pas ACCEPT_CANDIDATE ({row.iloc[-1]['decision']}) : "
                             "le test final est réservé aux candidats validés (--force pour passer outre, tracé).")
        spec = self._find_spec(exp_id)
        dev, test = self.splits.dev, self.splits.test
        windows = [(0, (0, dev[1] - self.splits.embargo), test)]
        trades, fitted = self.walk_forward(spec["strategy"], spec["params"], windows)
        m, extra = self.score(spec, trades, [test], pd.DataFrame(), None)
        decision, checks = ev.decide({**m, "p_null_holm": m["p_null"], "frac_folds_positive": 1.0},
                                     self.cfg["evaluation"], False)
        out = {"exp_id": exp_id, "split": "TEST", "decision": decision, "forced": force, **_round(m)}
        TEST_ACCESS.parent.mkdir(parents=True, exist_ok=True)
        TEST_ACCESS.write_text(json.dumps({"exp_id": exp_id, "utc": datetime.now(timezone.utc).isoformat(),
                                           "data_hash": self.md.data_hash, "forced": force}) + "\n")
        append_result(self.results_path, {**out, "run_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                          "data_mode": self.mode, "data_hash": self.md.data_hash,
                                          "git_commit": self.commit, "evaluator_hash": self.evaluator_hash,
                                          "config_hash": self.cfg_hash, "strategy": spec["strategy"],
                                          "params": json.dumps(spec["params"], sort_keys=True),
                                          "keep": decision == "ACCEPT_CANDIDATE"})
        print(json.dumps({**out, "checks": checks}, indent=2, default=str))
        return out

    # ------------------------------------------------------------------ utilitaires
    def _prior(self) -> pd.DataFrame:
        df = load_results(self.results_path)
        if len(df):
            df = df[df["data_hash"].astype(str) == self.md.data_hash]
        return df

    def _find_spec(self, exp_id: str) -> dict:
        for e in self.cfg["experiments"]:
            if e["id"] == exp_id:
                return e
        p = RUNS / exp_id / "summary.json"
        if p.exists():
            return json.loads(p.read_text())["experiment"]
        raise KeyError(f"expérience {exp_id} introuvable")

    @staticmethod
    def _print_row(r: dict):
        if r.get("decision") == "ERROR":
            return

        def f(key, nd=2):
            v = r.get(key)
            if v is None or (isinstance(v, float) and not np.isfinite(v)):
                return "—"
            return f"{v:.{nd}f}" if isinstance(v, (float, int)) else str(v)
        print(f"    trades={r.get('n_trades')} net={f('net_exp_bps', 3)} bps "
              f"[IC95 {f('ci_low_bps', 3)} ; {f('ci_high_bps', 3)}] brut={f('gross_exp_bps', 3)} "
              f"coût={f('cost_bps', 3)} PF={f('profit_factor')} p_hasard={f('p_null', 3)} "
              f"p_holm={f('p_null_holm', 3)} DSR={f('dsr', 3)}")
        print(f"    -> DÉCISION : {r.get('decision')}  ({r.get('duration_s')} s)")


# =============================================================================
# Proposition automatique de la prochaine expérience (règles explicites)
# =============================================================================
def propose_next(prior: pd.DataFrame, cfg: dict) -> list[dict]:
    """Règles déterministes et lisibles : pas de « boîte noire ». Chaque proposition
    porte sa justification. Les propositions `auto: True` sont exécutables par --auto ;
    les autres demandent du nouveau code (à écrire par l'agent ou par toi)."""
    dev = prior[(prior["split"] == "DEV") & (prior["decision"] != "ERROR")] if len(prior) else prior
    props: list[dict] = []
    if dev.empty:
        return props
    done_ids = set(prior["exp_id"])
    next_num = 1 + max(int(str(i)[1:]) for i in done_ids if str(i)[1:].isdigit())
    nid = lambda k: f"E{next_num + k:02d}"
    singles = dev[dev["type"].fillna("single") == "single"]
    sens_done = set(dev[dev["type"] == "sensitivity"]["name"].fillna(""))

    def already(strategy, params):
        return any((r["strategy"] == strategy) and (json.loads(r["params"]) == params) for _, r in singles.iterrows())

    accepted = singles[singles["decision"] == "ACCEPT_CANDIDATE"]
    if len(accepted):
        best = accepted.sort_values("net_exp_bps", ascending=False).iloc[0]
        if f"sensitivity_{best['exp_id']}" not in sens_done:
            props.append({"type": "sensitivity", "name": f"sensitivity_{best['exp_id']}", "base": best["exp_id"],
                          "grid": {"lookback": [10, 20, 40], "hold": [6, 12, 24]}, "auto": True,
                          "rationale": f"{best['exp_id']} est candidate : vérifier que le résultat ne dépend pas "
                                       "d'un choix de paramètres « chanceux » avant tout test final."})
        else:
            props.append({"type": "final_test", "base": best["exp_id"], "auto": False,
                          "rationale": f"Candidate robuste : test final UNIQUE "
                                       f"`python experiment_runner.py --final-test {best['exp_id']}` (décision humaine)."})
    main = singles[singles["strategy"] == "vol_breakout"]
    main_id = main.iloc[0]["exp_id"] if len(main) else singles.iloc[0]["exp_id"]
    if not len(accepted) and f"sensitivity_{main_id}" not in sens_done:
        props.append({"type": "sensitivity", "name": f"sensitivity_{main_id}", "base": main_id,
                      "grid": {"lookback": [10, 20, 40], "hold": [6, 12, 24]}, "auto": True,
                      "rationale": f"Aucune hypothèse acceptée. Vérifier que le rejet de {main_id} (hypothèse "
                                   "principale) ne tient pas à un choix arbitraire de paramètres. Les 9 "
                                   "configurations comptent comme 9 essais (Deflated Sharpe)."})
    gross_t = singles["gross_t_stat"].astype(float)
    if len(singles) and (gross_t.abs() < 2).all():
        p = {**json.loads(singles.iloc[0]["params"]), "mode": "fade"}
        if not already(singles.iloc[0]["strategy"], p):
            props.append({"type": "single", "name": "breakout_fade", "strategy": singles.iloc[0]["strategy"],
                          "params": p, "baseline": singles.iloc[0]["exp_id"], "auto": True,
                          "hypothesis": "Famille B (retour à la moyenne) : prendre la position OPPOSÉE à la cassure "
                                        "donne une espérance nette > 0.",
                          "rationale": "Aucun signal brut détectable (|t brut| < 2 partout) : optimiser les paramètres "
                                       "d'un signal nul serait du data snooping. On teste l'hypothèse concurrente "
                                       "(retour à la moyenne), en sachant qu'un signal brut nul inversé reste nul."})
    pos_gross = singles[(gross_t > 2) & (singles["net_exp_bps"].astype(float) <= 0)]
    for _, r in pos_gross.iterrows():
        p = json.loads(r["params"])
        p2 = {**p, "hold": int(p["hold"]) * 2}
        if not already(r["strategy"], p2):
            props.append({"type": "single", "name": f"{r['name']}_hold{p2['hold']}", "strategy": r["strategy"],
                          "params": p2, "baseline": r["exp_id"], "auto": True,
                          "hypothesis": f"Doubler l'horizon de {r['exp_id']} réduit la part des coûts et rend l'espérance nette > 0.",
                          "rationale": f"{r['exp_id']} a un avantage BRUT significatif mais mangé par les coûts : "
                                       "allonger la détention réduit le turnover."})
    props += [
        {"type": "code", "auto": False, "name": "session_effects",
         "rationale": "Mesurer l'effet heure/session (C. microstructure) : rendement, volatilité et spread par "
                      "tranche de 30 min, avant de construire une stratégie horaire."},
        {"type": "code", "auto": False, "name": "variance_ratio_diagnostic",
         "rationale": "Test du ratio de variance (Lo & MacKinlay 1988) et autocorrélation des rendements M1/M5 par "
                      "régime : diagnostic direct de momentum vs retour à la moyenne, sans stratégie."},
        {"type": "code", "auto": False, "name": "logistic_baseline",
         "rationale": "Famille D : régression logistique (scikit-learn) sur variables causales, labels à horizon fixe, "
                      "purge + embargo. Uniquement après des diagnostics montrant une structure exploitable."},
    ]
    for k, p in enumerate([p for p in props if p.get("auto")]):
        p["id"] = nid(k)
    return props


# =============================================================================
# Mémoire de recherche et rapport (blocs générés automatiquement)
# =============================================================================
AUTO_START, AUTO_END = "<!-- AUTO:START -->", "<!-- AUTO:END -->"


def _replace_auto_block(path: Path, content: str):
    text = path.read_text(encoding="utf-8") if path.exists() else f"{AUTO_START}\n{AUTO_END}\n"
    if AUTO_START not in text:
        text += f"\n{AUTO_START}\n{AUTO_END}\n"
    head, rest = text.split(AUTO_START, 1)
    _, tail = rest.split(AUTO_END, 1)
    path.write_text(f"{head}{AUTO_START}\n{content.strip()}\n{AUTO_END}{tail}", encoding="utf-8")


def results_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_aucune expérience_"
    cols = ["exp_id", "split", "data_mode", "name", "n_trades", "gross_exp_bps", "cost_bps", "net_exp_bps",
            "ci_low_bps", "ci_high_bps", "profit_factor", "win_rate", "max_dd_pct", "sharpe_ann",
            "frac_folds_positive", "p_null", "p_null_holm", "dsr", "stress_combined_net_bps", "decision"]
    d = df[[c for c in cols if c in df]].copy()
    for c in d.columns:
        if d[c].dtype.kind == "f":
            d[c] = d[c].map(lambda v: "" if pd.isna(v) else f"{v:.3f}")
    lines = ["| " + " | ".join(d.columns) + " |", "|" + "---|" * len(d.columns)]
    lines += ["| " + " | ".join(str(v) for v in r) + " |" for r in d.astype(str).itertuples(index=False)]
    return "\n".join(lines)


def update_docs(lab: Lab, props: list[dict]):
    df = lab._prior()
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    warn = ("> **MODE DÉMO — données synthétiques. Aucun chiffre ci-dessous n'est un résultat de marché réel.**\n"
            if lab.md.is_demo else "> Données historiques réelles.\n")
    journal = [f"### Journal automatique (mis à jour {stamp})", "", warn,
               f"Données : `{lab.md.source}` — hash `{lab.md.data_hash}` — "
               f"{len(lab.bars):,} barres {lab.md.timeframe}", "", results_table(df), ""]
    errs = df[df["decision"] == "ERROR"] if len(df) else df
    if len(errs):
        journal += ["#### Erreurs rencontrées", ""] + [f"- {r.exp_id} : {r.error}" for r in errs.itertuples()] + [""]
    journal += ["### Prochaines expériences proposées (règles de `propose_next`)", ""]
    for p in props:
        tag = f"`{p['id']}` (auto)" if p.get("auto") else "(manuel / nouveau code)"
        journal.append(f"- {tag} **{p.get('name', p['type'])}** — {p['rationale']}")
    _replace_auto_block(MEMORY, "\n".join(journal))
    _replace_auto_block(REPORT, "\n".join([f"_Tableau régénéré automatiquement le {stamp}._", "", warn,
                                           results_table(df)]))


# =============================================================================
# Main
# =============================================================================
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", help="n'exécuter que cet identifiant")
    ap.add_argument("--auto", type=int, default=0, help="nb max de propositions automatiques à exécuter")
    ap.add_argument("--mode", choices=["auto", "real", "demo"], help="force le mode de données")
    ap.add_argument("--rerun", action="store_true", help="ré-exécuter même si déjà fait (compte dans le budget)")
    ap.add_argument("--control", choices=["positive"], help="contrôle positif : démo avec effet planté")
    ap.add_argument("--final-test", metavar="EXP_ID")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--allow-retest", action="store_true")
    ap.add_argument("--relock", metavar="RAISON", help="(humain) re-verrouille evaluation.py / backtest.py")
    args = ap.parse_args(argv)

    if args.relock:
        data = ev.write_lock(ROOT, args.relock)
        print(f"évaluateur verrouillé : {json.dumps(data, indent=2)}")
        return 0

    cfg = load_config(ROOT / "research_config.yaml")
    np.random.seed(int(cfg["project"]["seed"]))
    results_path, write_docs, mode, suffix = RESULTS, True, args.mode, ""
    if args.control == "positive":
        cfg["data"]["demo"]["planted_edge"] = float(cfg["data"]["demo"].get("positive_control_edge", 0.3))
        results_path, write_docs, mode, suffix = RUNS / "controls" / "positive_control.csv", False, "demo", "_POSITIVE_CONTROL"
        globals()["RUNS"] = RUNS / "controls"
    lab = Lab(cfg, force_mode=mode, results_path=results_path, write_docs=write_docs, label_suffix=suffix)

    if args.final_test:
        lab.final_test(args.final_test, args.force, args.allow_retest)
        return 0

    budget = cfg["budget"]
    t_start = time.time()
    queue = [e for e in cfg["experiments"] if not args.only or e["id"] == args.only]

    def budget_left() -> int:
        prior = lab._prior()
        used = int((prior["split"] == "DEV").sum()) if len(prior) else 0
        return int(budget["max_experiments"]) - used

    def run_queue(items):
        for exp in items:
            prior = lab._prior()
            if not args.rerun and len(prior) and (prior["exp_id"] == exp["id"]).any():
                print(f"--- {exp['id']} déjà évaluée sur ces données : ignorée (--rerun pour refaire)")
                continue
            if budget_left() <= 0:
                print(f"!!! Budget atteint ({budget['max_experiments']} expériences sur ces données). Arrêt.")
                return False
            if time.time() - t_start > float(budget["max_total_seconds"]):
                print("!!! Budget de temps total atteint. Arrêt.")
                return False
            lab.run_experiment(dict(exp))
        return True

    ok = run_queue(queue)
    props = propose_next(lab._prior(), cfg)
    n_auto = 0
    while ok and n_auto < args.auto:
        runnable = [p for p in props if p.get("auto")]
        if not runnable:
            break
        p = runnable[0]
        print(f"\n[auto] proposition retenue : {p['id']} {p.get('name')} — {p['rationale']}")
        ok = run_queue([p])
        n_auto += 1
        props = propose_next(lab._prior(), cfg)

    if write_docs:
        update_docs(lab, props)
    print("\nProchaines expériences proposées :")
    for p in props:
        print(f"  - [{'auto' if p.get('auto') else 'manuel'}] {p.get('id', '')} {p.get('name', p['type'])}: {p['rationale']}")
    print(f"\nBudget restant : {budget_left()} expérience(s) sur ces données. Durée : {time.time() - t_start:.1f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
