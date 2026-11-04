"""
experiment_runner.py — La boucle AutoResearch du laboratoire.

Commandes (depuis le dossier biolab/, environnement activé) :
    python experiment_runner.py describe   # contrôle qualité des données + figures
    python experiment_runner.py run        # exécute les expériences en attente
    python experiment_runner.py final      # évaluation UNIQUE sur le test verrouillé
    python experiment_runner.py status     # état du laboratoire

Pour chaque expérience de research_config.yaml, la boucle :
  1. lit l'hypothèse et sa justification ;
  2. construit la configuration = champion actuel + UNE modification ;
  3. vérifie que cette configuration n'a pas déjà été testée (empreinte) ;
  4. entraîne sur 5 graines x 2 types de split (entraînement seulement) ;
  5. mesure MAE / RMSE / R² sur la VALIDATION (le test reste verrouillé) ;
  6. compare au champion graine par graine (comparaison appariée) ;
  7. applique la règle de décision pré-enregistrée (garder / rejeter) ;
  8. enregistre tout : results.csv, runs/<ID>.json, research_memory.md,
     scientific_hypotheses.md (y compris les résultats négatifs) ;
  9. propose les expériences suivantes.
"""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import platform
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

import data_loader
import evaluate
import model as models
import molecule_features as mf

LAB = Path(__file__).resolve().parent
RUNS = LAB / "runs"
FIG = LAB / "figures"
STATE_PATH = RUNS / "state.json"
LIT_ID = "LIT-ESOL"  # prédictions publiées de l'équation ESOL (Delaney 2004)


# ---------------------------------------------------------------------------
# Utilitaires : état, traçabilité
# ---------------------------------------------------------------------------
def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def git_commit() -> str:
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=LAB,
                             capture_output=True, text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--", "*.py", "*.yaml"], cwd=LAB,
                               capture_output=True, text=True).stdout.strip()
        return sha + ("+modifs" if dirty else "")
    except Exception:
        return "inconnu"


def environment() -> dict:
    import rdkit
    import sklearn
    return {"python": platform.python_version(), "platform": platform.platform(),
            "numpy": np.__version__, "pandas": pd.__version__,
            "scikit-learn": sklearn.__version__, "rdkit": rdkit.__version__}


def config_hash(c: dict) -> str:
    blob = json.dumps({k: c[k] for k in ("features", "model", "params")}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:10]


def load_state(cfg: dict) -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {"mission_id": cfg["project"]["mission_id"], "champion": None, "experiments": {},
            "order": [], "total_seconds": 0.0, "test_evaluations": [], "literature": {}}


def save_state(state: dict) -> None:
    RUNS.mkdir(exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=1, ensure_ascii=False), encoding="utf-8")


def resolve_config(exp: dict, state: dict) -> tuple[dict, str | None]:
    """Configuration effective = champion actuel + modification (`change`)."""
    if exp.get("base") is None:
        return copy.deepcopy(exp["config"]), None
    champ_id = state["champion"]
    base = copy.deepcopy(state["experiments"][champ_id]["config"])
    ch = exp["change"]
    if "model" in ch:
        base["model"] = ch["model"]
        base["params"] = ch.get("params", {})
    elif "params" in ch:
        base["params"] = ch["params"]
    if "features" in ch:
        base["features"] = list(ch["features"])
    if "features_add" in ch:
        base["features"] = base["features"] + [f for f in ch["features_add"] if f not in base["features"]]
    return base, champ_id


def describe_change(old: dict | None, new: dict) -> str:
    if old is None:
        return "configuration de départ"
    parts = []
    for k in ("features", "model", "params"):
        if old[k] != new[k]:
            parts.append(f"{k}: {old[k]} → {new[k]}")
    return " ; ".join(parts) or "aucun changement"


# ---------------------------------------------------------------------------
# Préparation des données et des découpages
# ---------------------------------------------------------------------------
def prepare(cfg: dict):
    df, report = data_loader.load_dataset(cfg)
    p = cfg["protocol"]
    splits = {(st, s): data_loader.make_split(df, st, s, p["fractions"])
              for st in p["split_types"] for s in p["seeds"]}
    return df, report, splits


def fit_predict(c: dict, X: np.ndarray, df: pd.DataFrame, split: dict, seed: int, n_jobs: int,
                eval_sets: tuple[str, ...]):
    """Entraîne sur `train` seulement et prédit sur les ensembles demandés."""
    tr = split["train"]
    m = models.build_model(c["model"], c["params"], seed=seed, n_jobs=n_jobs)
    groups = df["scaffold"].to_numpy()[tr]
    models.fit_model(m, X[tr], df["y"].to_numpy()[tr], groups=groups)
    preds = {k: m.predict(X[split[k]]) for k in eval_sets}
    return m, preds


# ---------------------------------------------------------------------------
# Commande `describe`
# ---------------------------------------------------------------------------
def cmd_describe(cfg: dict) -> None:
    df, report, splits = prepare(cfg)
    RUNS.mkdir(exist_ok=True); FIG.mkdir(exist_ok=True)
    report["split_sizes"] = {f"{k[0]}_seed{k[1]}": {n: int(len(v)) for n, v in s.items()}
                             for k, s in splits.items()}
    (RUNS / "data_quality.json").write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    evaluate.plot_dataset(df["y"].to_numpy(), FIG / "fig01_distribution_solubilite.png")
    # Galerie de molécules : du plus soluble au moins soluble.
    from rdkit import Chem
    from rdkit.Chem import Draw
    picks = df.sort_values("y").iloc[np.linspace(0, len(df) - 1, 8).astype(int)]
    img = Draw.MolsToGridImage([Chem.MolFromSmiles(s) for s in picks["smiles"]], molsPerRow=4,
                               subImgSize=(260, 200),
                               legends=[f"{n.split(' | ')[0][:22]}  logS={y:.2f}" for n, y in zip(picks["name"], picks["y"])])
    img.save(FIG / "fig00_exemples_molecules.png")
    print(f"{report['n_clean_molecules']} molécules propres ; rapport : runs/data_quality.json")


# ---------------------------------------------------------------------------
# Commande `run` : la boucle AutoResearch
# ---------------------------------------------------------------------------
def run_experiment(exp: dict, c: dict, df, splits, cfg) -> dict:
    budget = cfg["budget"]
    X, cols = mf.build_features(df["smiles"].tolist(), c["features"])
    t0 = time.perf_counter()
    per_seed, pred_rows, extra = {}, [], {}
    for (st, seed), split in splits.items():
        m, preds = fit_predict(c, X, df, split, seed, budget["n_jobs"], eval_sets=("valid",))  # test JAMAIS utilisé
        yv = df["y"].to_numpy()[split["valid"]]
        per_seed[f"{st}|{seed}"] = evaluate.regression_metrics(yv, preds["valid"])
        pred_rows += [{"split_type": st, "seed": seed, "mol_index": int(i), "y": float(a), "y_pred": float(b)}
                      for i, a, b in zip(split["valid"], yv, preds["valid"])]
        if isinstance(m, models.TunedModel):
            extra[f"{st}|{seed}"] = m.best_params_
        if time.perf_counter() - t0 > budget["max_seconds_per_experiment"]:
            return {"status": "budget_exceeded", "seconds": time.perf_counter() - t0}
    seconds = time.perf_counter() - t0
    summary = {}
    for st in cfg["protocol"]["split_types"]:
        summary[st] = evaluate.aggregate([v for k, v in per_seed.items() if k.startswith(st + "|")])
    (RUNS / "predictions").mkdir(parents=True, exist_ok=True)
    pd.DataFrame(pred_rows).to_csv(RUNS / "predictions" / f"{exp['id']}_valid.csv", index=False)
    return {"status": "done", "seconds": seconds, "n_features": len(cols),
            "per_seed": per_seed, "summary": summary, "tuned_params": extra}


def literature_reference(df, splits, cfg, sets=("valid",)) -> dict:
    """Prédictions publiées d'ESOL : aucun entraînement ici, simple lecture."""
    out = {}
    for name in sets:
        per_seed = {}
        for (st, seed), split in splits.items():
            idx = split[name]
            per_seed[f"{st}|{seed}"] = evaluate.regression_metrics(df["y"].to_numpy()[idx],
                                                                   df["esol_literature_pred"].to_numpy()[idx])
        out[name] = {"per_seed": per_seed, "summary": {st: evaluate.aggregate(
            [v for k, v in per_seed.items() if k.startswith(st + "|")]) for st in cfg["protocol"]["split_types"]}}
    return out


def rmse_map(res: dict) -> dict:
    return {tuple([k.split("|")[0], int(k.split("|")[1])]): v["rmse"] for k, v in res["per_seed"].items()}


def cmd_run(cfg: dict, only: str | None = None) -> None:
    df, report, splits = prepare(cfg)
    state = load_state(cfg)
    budget, rule = cfg["budget"], cfg["protocol"]["decision_rule"]
    if not state["literature"]:
        state["literature"] = literature_reference(df, splits, cfg)
    print(f"Budget : {budget['max_experiments']} expériences max, "
          f"{budget['max_seconds_per_experiment']} s/expérience, {budget['max_total_seconds']} s au total.")
    for exp in cfg["experiments"]:
        eid = exp["id"]
        if only and eid != only:
            continue
        if eid in state["experiments"]:
            print(f"[{eid}] déjà réalisée — ignorée (supprimez runs/ pour tout recommencer).")
            continue
        n_done = sum(1 for e in state["experiments"].values() if e["status"] == "done")
        if n_done >= budget["max_experiments"]:
            print("Budget atteint : nombre maximal d'expériences."); break
        if state["total_seconds"] >= budget["max_total_seconds"]:
            print("Budget atteint : temps de calcul total."); break
        if exp.get("base") == "champion" and state["champion"] is None:
            print(f"[{eid}] impossible : aucun champion encore établi."); continue

        c, ref_id = resolve_config(exp, state)
        h = config_hash(c)
        same = [k for k, v in state["experiments"].items() if v["config_hash"] == h]
        if same:
            print(f"[{eid}] configuration identique à {same[0]} : hypothèse déjà testée, ignorée.")
            state["experiments"][eid] = {"status": "duplicate", "duplicate_of": same[0], "config": c,
                                         "config_hash": h, "title": exp["title"]}
            state["order"].append(eid); save_state(state); continue

        print(f"[{eid}] {exp['title']}\n      changement : "
              f"{describe_change(state['experiments'][ref_id]['config'] if ref_id else None, c)}")
        res = run_experiment(exp, c, df, splits, cfg)
        state["total_seconds"] += res["seconds"]
        entry = {"title": exp["title"], "hypothesis": exp["hypothesis"].strip(),
                 "justification": str(exp.get("justification", "")).strip(), "config": c,
                 "config_hash": h, "compared_to": ref_id, "timestamp": now_utc(),
                 "git_commit": git_commit(), "environment": environment(),
                 "change": describe_change(state["experiments"][ref_id]["config"] if ref_id else None, c), **res}
        if res["status"] != "done":
            entry["decision"] = "reject"
            print(f"      ABANDON : budget de temps dépassé ({res['seconds']:.0f} s).")
        elif ref_id is None:
            entry["decision"] = "reference"
            state["champion"] = eid
        else:
            dec = evaluate.paired_decision(rmse_map(res), rmse_map(state["experiments"][ref_id]), rule)
            entry.update(dec)
            if dec["decision"] == "keep":
                state["champion"] = eid
        state["experiments"][eid] = entry
        state["order"].append(eid)
        (RUNS / f"{eid}.json").write_text(json.dumps(entry, indent=1, ensure_ascii=False), encoding="utf-8")
        save_state(state)
        if res["status"] == "done":
            s = res["summary"]
            msg = (f"      validation RMSE : aléatoire {s['random']['rmse_mean']:.3f}±{s['random']['rmse_std']:.3f}"
                   f" | scaffold {s['scaffold']['rmse_mean']:.3f}±{s['scaffold']['rmse_std']:.3f}"
                   f"  ({res['seconds']:.1f} s)")
            if ref_id:
                msg += (f"\n      vs {ref_id} : Δ={entry['delta_rmse_mean']:+.3f}, "
                        f"{entry['win_fraction']:.0%} des paires améliorées → {entry['decision'].upper()}")
            print(msg)
    write_outputs(cfg, state)
    print(f"\nChampion actuel : {state['champion']}  |  temps total : {state['total_seconds']:.0f} s")


# ---------------------------------------------------------------------------
# Commande `final` : test verrouillé + analyse d'erreurs
# ---------------------------------------------------------------------------
def permutation_importance_grouped(m, X, y, cols, seed, n_repeats=5) -> tuple[list, np.ndarray, np.ndarray]:
    """Importance par permutation : on mélange une variable et on regarde de
    combien l'erreur augmente. Les bits de Morgan sont permutés ensemble."""
    groups: dict[str, list[int]] = {}
    for i, c in enumerate(cols):
        groups.setdefault("Morgan (2048 bits, groupés)" if c.startswith("morgan_") else c, []).append(i)
    rng = np.random.default_rng(seed)
    base = evaluate.regression_metrics(y, m.predict(X))["rmse"]
    names, means, stds = [], [], []
    for g, idx in groups.items():
        incs = []
        for _ in range(n_repeats):
            Xp = X.copy()
            Xp[:, idx] = Xp[rng.permutation(len(X))][:, idx]
            incs.append(evaluate.regression_metrics(y, m.predict(Xp))["rmse"] - base)
        names.append(g); means.append(np.mean(incs)); stds.append(np.std(incs))
    return names, np.array(means), np.array(stds)


def cmd_final(cfg: dict, force: bool = False) -> None:
    from scipy.stats import spearmanr
    state = load_state(cfg)
    if not state["champion"]:
        sys.exit("Aucune expérience réalisée : lancez d'abord `python experiment_runner.py run`.")
    if state["test_evaluations"] and not force:
        sys.exit("Le test a DÉJÀ été évalué. Une seconde évaluation après modification transforme le test "
                 "en ensemble de validation. Utilisez --force seulement si rien n'a changé (et ce sera tracé).")
    df, report, splits = prepare(cfg)
    budget = cfg["budget"]
    champ = state["champion"]
    final_ids = list(dict.fromkeys(["E01", "E02", "E03", "E04", champ]))
    final_ids = [i for i in final_ids if i in state["experiments"] and state["experiments"][i]["status"] == "done"]
    state["test_evaluations"].append({"timestamp": now_utc(), "champion": champ, "models": final_ids,
                                      "git_commit": git_commit()})
    final = {"champion": champ, "models": {}}
    champ_detail = {}
    for eid in final_ids:
        c = state["experiments"][eid]["config"]
        X, cols = mf.build_features(df["smiles"].tolist(), c["features"])
        per_seed = {}
        for (st, seed), split in splits.items():
            m, preds = fit_predict(c, X, df, split, seed, budget["n_jobs"], eval_sets=("valid", "test"))
            yt = df["y"].to_numpy()[split["test"]]
            per_seed[f"{st}|{seed}"] = evaluate.regression_metrics(yt, preds["test"])
            if eid == champ:
                champ_detail[(st, seed)] = {"model": m, "preds": preds, "X": X, "cols": cols}
        final["models"][eid] = {"per_seed": per_seed, "summary": {st: evaluate.aggregate(
            [v for k, v in per_seed.items() if k.startswith(st + "|")]) for st in cfg["protocol"]["split_types"]}}
        print(f"[test] {eid} : " + " | ".join(
            f"{st} RMSE {final['models'][eid]['summary'][st]['rmse_mean']:.3f}" for st in ("random", "scaffold")))
    final["models"][LIT_ID] = literature_reference(df, splits, cfg, sets=("test",))["test"]

    # --- Figure de parité (test) du champion ---------------------------------
    FIG.mkdir(exist_ok=True)
    par = {}
    for st in ("random", "scaffold"):
        ys, yh = [], []
        for (s2, seed), d in champ_detail.items():
            if s2 == st:
                ys.append(df["y"].to_numpy()[splits[(st, seed)]["test"]]); yh.append(d["preds"]["test"])
        par[st] = (np.concatenate(ys), np.concatenate(yh), final["models"][champ]["summary"][st])
    evaluate.plot_parity(par, FIG / "fig03_parite_test_champion.png",
                         f"Test final verrouillé — champion {champ} (5 graines empilées)")

    # --- Analyse d'erreurs sur la VALIDATION (pas sur le test) ---------------
    analysis, err_fig, top_rows = {}, {}, []
    for st in ("random", "scaffold"):
        ys, res, sims, unc, idxs = [], [], [], [], []
        for (s2, seed), d in champ_detail.items():
            if s2 != st:
                continue
            sp = splits[(st, seed)]
            yv = df["y"].to_numpy()[sp["valid"]]
            ys.append(yv); res.append(d["preds"]["valid"] - yv); idxs.append(sp["valid"])
            sims.append(evaluate.max_similarity_to_train(df["smiles"].iloc[sp["valid"]].tolist(),
                                                         df["smiles"].iloc[sp["train"]].tolist()))
            u = models.per_tree_std(d["model"], d["X"][sp["valid"]])
            unc.append(u if u is not None else np.full(len(yv), np.nan))
        y, r, sim, u, ix = map(np.concatenate, (ys, res, sims, unc, idxs))
        err_fig[st] = {"y": y, "residual": r, "sim": sim}
        bins = {"sim<0.3": sim < 0.3, "0.3-0.5": (sim >= 0.3) & (sim < 0.5), "0.5-0.7": (sim >= 0.5) & (sim < 0.7),
                "sim>=0.7": sim >= 0.7}
        sol_bins = {"logS<-6": y < -6, "-6<=logS<-2": (y >= -6) & (y < -2), "logS>=-2": y >= -2}
        a = {
            "n_predictions": int(len(y)),
            "residual_vs_measured_slope": float(np.polyfit(y, r, 1)[0]),
            "spearman_abs_error_vs_similarity": float(spearmanr(sim, np.abs(r)).statistic),
            "rmse_by_similarity": {k: {"n": int(v.sum()), "rmse": float(np.sqrt(np.mean(r[v] ** 2))) if v.sum() else None}
                                   for k, v in bins.items()},
            "rmse_by_solubility": {k: {"n": int(v.sum()), "rmse": float(np.sqrt(np.mean(r[v] ** 2))) if v.sum() else None}
                                   for k, v in sol_bins.items()},
        }
        if not np.isnan(u).all():
            a["spearman_abs_error_vs_tree_std"] = float(spearmanr(u, np.abs(r)).statistic)
            q = np.quantile(u, [0.0, 0.5, 1.0])
            lo, hi = u <= q[1], u > q[1]
            a["rmse_low_vs_high_uncertainty"] = {"faible_incertitude": float(np.sqrt(np.mean(r[lo] ** 2))),
                                                 "forte_incertitude": float(np.sqrt(np.mean(r[hi] ** 2)))}
        analysis[st] = a
        tmp = pd.DataFrame({"mol_index": ix, "residual": r, "sim": sim})
        g = tmp.groupby("mol_index").agg(residual=("residual", "mean"), n=("residual", "size"), sim=("sim", "mean"))
        g = g.reindex(g["residual"].abs().sort_values(ascending=False).index).head(15)
        for i, row in g.iterrows():
            top_rows.append({"split_type": st, "name": df.at[i, "name"], "smiles": df.at[i, "smiles"],
                             "y_measured": round(df.at[i, "y"], 2), "residual_mean": round(row["residual"], 2),
                             "n_validation_appearances": int(row["n"]), "max_sim_train": round(row["sim"], 2),
                             "scaffold": df.at[i, "scaffold"] or "(acyclique)"})
    evaluate.plot_error_analysis(err_fig, FIG / "fig04_analyse_erreurs_validation.png")
    pd.DataFrame(top_rows).to_csv(RUNS / "top_errors_validation.csv", index=False)

    # --- Importance des variables (validation, split aléatoire, graine 0) ----
    d = champ_detail[("random", 0)]
    sp = splits[("random", 0)]
    if d["cols"]:
        names, mean, std = permutation_importance_grouped(d["model"], d["X"][sp["valid"]],
                                                          df["y"].to_numpy()[sp["valid"]], d["cols"], seed=0)
        evaluate.plot_importance(names, mean, std, FIG / "fig05_importance_variables.png")
        order = np.argsort(mean)[::-1][:10]
        analysis["permutation_importance_top10"] = [{"variable": names[i], "delta_rmse": round(float(mean[i]), 4)}
                                                    for i in order]
    final["error_analysis_validation"] = analysis
    (RUNS / "final_test.json").write_text(json.dumps(final, indent=1, ensure_ascii=False), encoding="utf-8")
    state["final"] = final
    save_state(state)
    write_outputs(cfg, state)
    print("Évaluation finale enregistrée : runs/final_test.json, figures/fig03-05, results.csv")


# ---------------------------------------------------------------------------
# Sorties : results.csv, mémoire, hypothèses, figure, propositions
# ---------------------------------------------------------------------------
def results_rows(state: dict) -> list[dict]:
    rows = []
    for eid in state["order"]:
        e = state["experiments"][eid]
        if e["status"] != "done":
            rows.append({"stage": "validation", "experiment_id": eid, "title": e["title"], "decision": e.get("decision", e["status"]),
                         "config_hash": e["config_hash"], "note": e.get("duplicate_of", e["status"])})
            continue
        for st, s in e["summary"].items():
            ps = e.get("per_split", {}).get(st, {})
            rows.append({"stage": "validation", "experiment_id": eid, "title": e["title"], "split_type": st,
                         "n_seeds": 5, "features": "+".join(e["config"]["features"]) or "(aucune)",
                         "n_features": e["n_features"], "model": e["config"]["model"],
                         "params": json.dumps(e["config"]["params"], sort_keys=True),
                         **{k: round(v, 4) for k, v in s.items()},
                         "compared_to": e["compared_to"] or "",
                         "delta_rmse_vs_ref": round(ps["delta_rmse_mean"], 4) if ps else "",
                         "win_fraction_vs_ref": round(ps["win_fraction"], 2) if ps else "",
                         "decision": e["decision"], "seconds": round(e["seconds"], 1),
                         "config_hash": e["config_hash"], "git_commit": e["git_commit"], "timestamp_utc": e["timestamp"]})
    for st, s in state.get("literature", {}).get("valid", {}).get("summary", {}).items():
        rows.append({"stage": "validation", "experiment_id": LIT_ID, "title": "Prédictions ESOL publiées (Delaney 2004) — non ré-entraînées",
                     "split_type": st, "n_seeds": 5, **{k: round(v, 4) for k, v in s.items()}, "decision": "littérature"})
    if "final" in state:
        for eid, r in state["final"]["models"].items():
            for st, s in r["summary"].items():
                title = state["experiments"][eid]["title"] if eid in state["experiments"] else "Prédictions ESOL publiées"
                rows.append({"stage": "final_test", "experiment_id": eid, "title": title, "split_type": st,
                             "n_seeds": 5, **{k: round(v, 4) for k, v in s.items()},
                             "decision": "champion" if eid == state["final"]["champion"] else "comparaison",
                             "timestamp_utc": state["test_evaluations"][-1]["timestamp"]})
    return rows


def propose_next(state: dict) -> list[str]:
    """Propositions automatiques fondées sur des règles simples et explicites.
    Ce sont des PISTES à évaluer, pas des conclusions."""
    ex = state["experiments"]
    champ = ex[state["champion"]]
    s = champ["summary"]
    out = []
    gap = s["scaffold"]["rmse_mean"] - s["random"]["rmse_mean"]
    if gap > 0.1:
        out.append(f"Écart scaffold − aléatoire = {gap:+.2f} log : le modèle généralise moins bien aux nouvelles "
                   "familles chimiques. Piste : validation externe sur AqSolDB (Sorkun et al. 2019), après "
                   "retrait des molécules déjà présentes dans ESOL (nouvelle mission, nouveau protocole).")
    rejected = [k for k, v in ex.items() if v.get("decision") == "reject"]
    if any("morgan" in "".join(ex[k]["config"]["features"]) for k in rejected):
        out.append("Les empreintes de Morgan binaires n'ont pas aidé : tester des empreintes de COMPTAGE "
                   "(nombre d'occurrences) ou un rayon 1, une seule modification à la fois.")
    tuned = [k for k, v in ex.items() if v["config"]["model"] == "random_forest_tuned"]
    if tuned and ex[tuned[0]].get("decision") == "reject":
        out.append("Le réglage d'hyperparamètres n'apporte pas de gain robuste : ne plus investir de calcul ici "
                   "tant que la représentation n'a pas changé.")
    fa = state.get("final", {}).get("error_analysis_validation", {})
    if fa:
        slope = fa["random"]["residual_vs_measured_slope"]
        if slope < -0.1:
            out.append(f"Les résidus diminuent avec la solubilité mesurée (pente {slope:.2f}) : les molécules très peu "
                       "solubles sont surestimées. Hypothèse (équation générale de solubilité) : il manque "
                       "l'information sur le cristal (point de fusion). Piste : descripteurs de symétrie/planéité, "
                       "ou un jeu de données incluant le point de fusion.")
        sp = fa["random"].get("spearman_abs_error_vs_tree_std")
        if sp is not None and sp > 0.2:
            out.append(f"L'incertitude de la forêt (écart-type entre arbres) est corrélée à l'erreur (Spearman {sp:.2f}) : "
                       "piste d'un indicateur de fiabilité à afficher avec chaque prédiction ; à calibrer.")
    out.append("Phase A suivante : lipophilie (jeu Lipophilicity de MoleculeNet, ~4200 molécules) avec "
               "exactement le même protocole, pour vérifier si les conclusions se transfèrent.")
    out.append("Comparer avec un modèle de graphe (ex. Chemprop) seulement si le gain attendu justifie le coût : "
               "à évaluer d'abord sur Google Colab (gratuit), aucune dépense sans accord.")
    return out


def _replace_block(path: Path, tag: str, content: str) -> None:
    start, end = f"<!-- AUTO:{tag}:START -->", f"<!-- AUTO:{tag}:END -->"
    text = path.read_text(encoding="utf-8") if path.exists() else f"{start}\n{end}\n"
    if start not in text:
        text += f"\n{start}\n{end}\n"
    before, rest = text.split(start, 1)
    _, after = rest.split(end, 1)
    path.write_text(f"{before}{start}\n{content}\n{end}{after}", encoding="utf-8")


def fmt(s: dict, st: str, m: str = "rmse") -> str:
    return f"{s[st][m + '_mean']:.3f} ± {s[st][m + '_std']:.3f}"


def write_outputs(cfg: dict, state: dict) -> None:
    pd.DataFrame(results_rows(state)).to_csv(LAB / "results.csv", index=False)
    labels = {"keep": "✅ CONSERVÉE", "reject": "❌ REJETÉE", "reference": "🔵 RÉFÉRENCE"}
    journal, hyp = [], ["| ID | Hypothèse | Statut | Preuve (validation, 10 paires) |", "|---|---|---|---|"]
    for eid in state["order"]:
        e = state["experiments"][eid]
        if e["status"] == "duplicate":
            journal.append(f"### {eid} — {e['title']} — ⚪ DÉJÀ TESTÉE (identique à {e['duplicate_of']})\n")
            continue
        lines = [f"### {eid} — {e['title']} — {labels.get(e['decision'], e['decision'])}",
                 f"- Date : {e['timestamp']} · commit `{e['git_commit']}` · durée {e['seconds']:.1f} s · empreinte `{e['config_hash']}`",
                 f"- Hypothèse : {e['hypothesis']}",
                 f"- Justification : {e['justification']}",
                 f"- Modification (vs {e['compared_to'] or '—'}) : {e['change']}"]
        if e["status"] == "done":
            s = e["summary"]
            lines.append(f"- RMSE validation : aléatoire {fmt(s, 'random')} | scaffold {fmt(s, 'scaffold')}")
            lines.append(f"- R² validation : aléatoire {fmt(s, 'random', 'r2')} | scaffold {fmt(s, 'scaffold', 'r2')}")
            if e.get("compared_to"):
                lines.append(f"- Comparaison appariée : Δ RMSE = {e['delta_rmse_mean']:+.3f} ± {e['delta_rmse_std']:.3f}, "
                             f"{e['win_fraction']:.0%} des paires améliorées → **{e['decision']}**")
            if e.get("tuned_params"):
                lines.append(f"- Hyperparamètres choisis (CV interne) : {json.dumps(e['tuned_params'], ensure_ascii=False)}")
        journal.append("\n".join(lines) + "\n")
        status = {"keep": "Soutenue (modification conservée)", "reject": "Non soutenue (rejetée)",
                  "reference": "Référence"}[e["decision"]]
        if e["status"] != "done":
            proof = "budget de temps dépassé"
        elif e.get("compared_to"):
            proof = f"Δ RMSE {e['delta_rmse_mean']:+.3f} vs {e['compared_to']}, {e['win_fraction']:.0%} des paires améliorées"
        else:
            proof = (f"RMSE alé. {e['summary']['random']['rmse_mean']:.2f} / "
                     f"scaf. {e['summary']['scaffold']['rmse_mean']:.2f}")
        hyp.append(f"| {eid} | {e['hypothesis'].splitlines()[0][:150]} | {status} | {proof} |")
    tested = set(state["experiments"])
    for exp in cfg["experiments"]:
        if exp["id"] not in tested:
            hyp.append(f"| {exp['id']} | {exp['hypothesis'].strip()[:150]} | Non testée | — |")
    journal.append(f"**Champion actuel : {state['champion']}** · temps de calcul cumulé : {state['total_seconds']:.0f} s "
                   f"/ {cfg['budget']['max_total_seconds']} s · évaluations du test : {len(state['test_evaluations'])}")
    _replace_block(LAB / "research_memory.md", "JOURNAL", "\n".join(journal))
    _replace_block(LAB / "research_memory.md", "NEXT", "\n".join(f"{i+1}. {p}" for i, p in enumerate(propose_next(state))))
    _replace_block(LAB / "scientific_hypotheses.md", "HYPOTHESES", "\n".join(hyp))
    done = [r for r in results_rows(state) if r["stage"] == "validation" and r.get("split_type") and r["experiment_id"] != LIT_ID]
    if done:
        FIG.mkdir(exist_ok=True)
        keep_ids = {k for k, v in state["experiments"].items() if v.get("decision") in ("keep", "reference")}
        evaluate.plot_experiments(done, keep_ids, FIG / "fig02_boucle_experiences.png")


def cmd_status(cfg: dict) -> None:
    state = load_state(cfg)
    print(f"Mission {state['mission_id']} — champion : {state['champion']} — "
          f"{state['total_seconds']:.0f} s de calcul — test évalué {len(state['test_evaluations'])} fois")
    for eid in state["order"]:
        e = state["experiments"][eid]
        if e["status"] == "done":
            print(f"  {eid} {e['decision']:9s} scaffold RMSE {e['summary']['scaffold']['rmse_mean']:.3f}  "
                  f"random RMSE {e['summary']['random']['rmse_mean']:.3f}  {e['title']}")
        else:
            print(f"  {eid} {e['status']}  {e['title']}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Boucle AutoResearch — mission solubilité")
    ap.add_argument("command", choices=["describe", "run", "final", "status"])
    ap.add_argument("--only", help="n'exécuter que cette expérience (ex. E04)")
    ap.add_argument("--force", action="store_true", help="ré-évaluer le test (tracé dans l'état)")
    ap.add_argument("--config", default=str(LAB / "research_config.yaml"))
    a = ap.parse_args()
    cfg = data_loader.load_config(a.config)
    if a.command == "describe":
        cmd_describe(cfg)
    elif a.command == "run":
        cmd_describe(cfg)
        cmd_run(cfg, a.only)
    elif a.command == "final":
        cmd_final(cfg, a.force)
    else:
        cmd_status(cfg)


if __name__ == "__main__":
    main()
