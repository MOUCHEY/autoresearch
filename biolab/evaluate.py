"""
evaluate.py — Mesurer, comparer, décider, visualiser.

Trois métriques de régression (toutes en unités log10(mol/L)) :
  MAE  = moyenne des |erreur|              -> "de combien je me trompe en moyenne"
  RMSE = racine de la moyenne des erreur²  -> pénalise davantage les grosses erreurs
  R²   = 1 - (erreur du modèle / erreur de la moyenne) -> 1 = parfait, 0 = pas mieux
         que de prédire la moyenne, < 0 = pire que la moyenne.

Repère : une erreur de 1 unité log = un facteur 10 sur la solubilité.
"""

from __future__ import annotations

import numpy as np
from rdkit import Chem, DataStructs
from rdkit.Chem import rdFingerprintGenerator
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

# Palette (validée daltonisme, voir skill dataviz) : bleu = random, orange = scaffold.
COLORS = {"random": "#2a78d6", "scaffold": "#eb6834", "accent": "#1baf7a",
          "ink": "#0b0b0b", "ink2": "#52514e", "grid": "#e4e3df", "surface": "#fcfcfb"}
SPLIT_LABELS = {"random": "split aléatoire", "scaffold": "split par échafaudage"}


# ---------------------------------------------------------------------------
# Métriques
# ---------------------------------------------------------------------------
def regression_metrics(y_true, y_pred) -> dict[str, float]:
    return {
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "rmse": float(np.sqrt(mean_squared_error(y_true, y_pred))),
        "r2": float(r2_score(y_true, y_pred)),
    }


def aggregate(per_seed: list[dict]) -> dict[str, float]:
    """Moyenne et écart-type (sur les graines) de chaque métrique."""
    out = {}
    for m in ("mae", "rmse", "r2"):
        v = np.array([r[m] for r in per_seed])
        out[f"{m}_mean"] = float(v.mean())
        out[f"{m}_std"] = float(v.std(ddof=1)) if len(v) > 1 else 0.0
    return out


# ---------------------------------------------------------------------------
# Décision : garder ou rejeter une modification ?
# ---------------------------------------------------------------------------
def paired_decision(new: dict, ref: dict, rule: dict) -> dict:
    """Compare deux expériences sur les MÊMES découpages (comparaison appariée).

    `new` et `ref` : {(split_type, seed): rmse_validation}.
    On regarde la différence graine par graine : c'est beaucoup plus sensible
    que de comparer deux moyennes, car la difficulté propre à chaque découpage
    s'annule dans la différence.
    """
    keys = sorted(ref)
    d = np.array([new[k] - ref[k] for k in keys])
    delta = float(d.mean())
    wins = float((d < 0).mean())
    keep = (delta <= -rule["min_delta_rmse"]) and (wins >= rule["min_win_fraction"])
    per_split = {}
    for st in sorted({k[0] for k in keys}):
        ds = np.array([new[k] - ref[k] for k in keys if k[0] == st])
        per_split[st] = {"delta_rmse_mean": float(ds.mean()), "win_fraction": float((ds < 0).mean())}
    return {"delta_rmse_mean": delta, "delta_rmse_std": float(d.std(ddof=1)),
            "win_fraction": wins, "decision": "keep" if keep else "reject",
            "per_split": per_split}


# ---------------------------------------------------------------------------
# Domaine d'applicabilité : la molécule ressemble-t-elle à l'entraînement ?
# ---------------------------------------------------------------------------
_FPGEN = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048)


def max_similarity_to_train(smiles_eval: list[str], smiles_train: list[str]) -> np.ndarray:
    """Similarité de Tanimoto maximale entre chaque molécule évaluée et
    l'ensemble d'entraînement (1 = molécule identique, 0 = rien en commun)."""
    fps_train = [_FPGEN.GetFingerprint(Chem.MolFromSmiles(s)) for s in smiles_train]
    out = []
    for s in smiles_eval:
        fp = _FPGEN.GetFingerprint(Chem.MolFromSmiles(s))
        out.append(max(DataStructs.BulkTanimotoSimilarity(fp, fps_train)))
    return np.array(out)


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------
def _style(ax):
    ax.set_facecolor(COLORS["surface"])
    ax.grid(True, color=COLORS["grid"], linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(COLORS["ink2"])
    ax.tick_params(colors=COLORS["ink2"])


def plot_experiments(rows: list[dict], champion_ids: set[str], path) -> None:
    """RMSE de validation (moyenne ± écart-type) de chaque expérience."""
    import matplotlib.pyplot as plt
    ids = sorted({r["experiment_id"] for r in rows})
    fig, ax = plt.subplots(figsize=(10, 5.2), dpi=150)
    fig.patch.set_facecolor(COLORS["surface"])
    _style(ax)
    x = np.arange(len(ids))
    for j, st in enumerate(("random", "scaffold")):
        m = [next(r for r in rows if r["experiment_id"] == i and r["split_type"] == st) for i in ids]
        ax.errorbar(x + (j - 0.5) * 0.28, [r["rmse_mean"] for r in m], yerr=[r["rmse_std"] for r in m],
                    fmt="o", ms=8, lw=2, capsize=4, color=COLORS[st], label=SPLIT_LABELS[st],
                    markeredgecolor=COLORS["surface"], markeredgewidth=2)
    ax.set_xticks(x)
    ax.set_xticklabels([f"{i}\n{'gardée' if i in champion_ids else 'rejetée'}" for i in ids],
                       color=COLORS["ink2"], fontsize=9)
    ax.set_ylabel("RMSE en validation (log mol/L) — plus bas = mieux", color=COLORS["ink"])
    ax.set_title("Boucle AutoResearch : erreur de validation par expérience (5 graines)",
                 color=COLORS["ink"], loc="left", fontsize=12)
    ax.legend(frameon=False, labelcolor=COLORS["ink"])
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def plot_parity(results: dict, path, title: str) -> None:
    """Prédit vs mesuré sur le test final. `results[split_type] = (y, yhat, metrics)`."""
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(10, 5), dpi=150, sharex=True, sharey=True)
    fig.patch.set_facecolor(COLORS["surface"])
    for ax, st in zip(axes, ("random", "scaffold")):
        y, yhat, m = results[st]
        _style(ax)
        lo, hi = -12, 2.5
        ax.plot([lo, hi], [lo, hi], color=COLORS["ink2"], lw=1, ls="--", label="prédiction parfaite")
        ax.fill_between([lo, hi], [lo - 1, hi - 1], [lo + 1, hi + 1], color=COLORS["grid"],
                        alpha=0.6, lw=0, label="± 1 log (facteur 10)")
        ax.scatter(y, yhat, s=18, alpha=0.75, color=COLORS[st], edgecolors=COLORS["surface"], linewidths=0.5)
        ax.set_xlim(lo, hi); ax.set_ylim(lo, hi)
        ax.set_title(f"{SPLIT_LABELS[st]}\nRMSE={m['rmse_mean']:.2f}±{m['rmse_std']:.2f}  "
                     f"R²={m['r2_mean']:.2f}", color=COLORS["ink"], fontsize=10, loc="left")
        ax.set_xlabel("log S mesuré", color=COLORS["ink"])
    axes[0].set_ylabel("log S prédit", color=COLORS["ink"])
    axes[0].legend(frameon=False, loc="upper left", fontsize=8, labelcolor=COLORS["ink"])
    fig.suptitle(title, color=COLORS["ink"], x=0.01, ha="left", fontsize=12)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def plot_error_analysis(err: dict, path) -> None:
    """Deux panneaux : erreur vs solubilité mesurée, erreur vs similarité à l'entraînement."""
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6), dpi=150)
    fig.patch.set_facecolor(COLORS["surface"])
    for st in ("random", "scaffold"):
        e = err[st]
        _style(axes[0]); _style(axes[1])
        axes[0].scatter(e["y"], e["residual"], s=12, alpha=0.5, color=COLORS[st], label=SPLIT_LABELS[st])
        axes[1].scatter(e["sim"], np.abs(e["residual"]), s=12, alpha=0.5, color=COLORS[st], label=SPLIT_LABELS[st])
    axes[0].axhline(0, color=COLORS["ink2"], lw=1)
    axes[0].set_xlabel("log S mesuré", color=COLORS["ink"])
    axes[0].set_ylabel("résidu = prédit − mesuré", color=COLORS["ink"])
    axes[0].set_title("Les extrêmes sont « tirés vers la moyenne »", color=COLORS["ink"], loc="left", fontsize=10)
    axes[1].set_xlabel("similarité max. (Tanimoto) avec l'entraînement", color=COLORS["ink"])
    axes[1].set_ylabel("|erreur|", color=COLORS["ink"])
    axes[1].set_title("Molécules peu similaires = erreurs plus grandes ?", color=COLORS["ink"], loc="left", fontsize=10)
    axes[1].legend(frameon=False, labelcolor=COLORS["ink"])
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def plot_importance(names: list[str], mean: np.ndarray, std: np.ndarray, path, top: int = 15) -> None:
    import matplotlib.pyplot as plt
    order = np.argsort(mean)[::-1][:top][::-1]
    fig, ax = plt.subplots(figsize=(8, 5.5), dpi=150)
    fig.patch.set_facecolor(COLORS["surface"])
    _style(ax)
    ax.barh(np.arange(len(order)), mean[order], xerr=std[order], color=COLORS["random"], height=0.6,
            error_kw={"ecolor": COLORS["ink2"], "lw": 1})
    ax.set_yticks(np.arange(len(order)))
    ax.set_yticklabels([names[i] for i in order], color=COLORS["ink"], fontsize=9)
    ax.set_xlabel("hausse du RMSE quand la variable est mélangée (validation)", color=COLORS["ink"])
    ax.set_title("Importance par permutation (modèle champion, split aléatoire)", color=COLORS["ink"],
                 loc="left", fontsize=11)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def plot_dataset(y: np.ndarray, path) -> None:
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(8, 4), dpi=150)
    fig.patch.set_facecolor(COLORS["surface"])
    _style(ax)
    ax.hist(y, bins=40, color=COLORS["random"], edgecolor=COLORS["surface"], linewidth=1)
    ax.set_xlabel("log S mesuré (log10 mol/L) — à droite = plus soluble", color=COLORS["ink"])
    ax.set_ylabel("nombre de molécules", color=COLORS["ink"])
    ax.set_title(f"Distribution de la solubilité dans ESOL nettoyé (n={len(y)})", color=COLORS["ink"],
                 loc="left", fontsize=11)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
