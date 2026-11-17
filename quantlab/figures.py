"""
figures.py — figures du rapport (lit runs/ et results.csv, n'évalue rien lui-même).

Chaque jeu de données a ses figures dans runs/<data_hash>/, et chaque titre dit DÉMO ou RÉEL
d'après la colonne data_mode : un chiffre réel ne peut pas apparaître sous une étiquette
démo, ni l'inverse.

    python figures.py                  -> tous les jeux de results.csv + la synthèse des contrôles DÉMO
    python figures.py --mode real      -> seulement les jeux RÉELS
    python figures.py --hash <hash>    -> un seul jeu

Fichiers écrits :
    runs/<data_hash>/fig_ci.png               espérance nette et IC 95 % par expérience
    runs/<data_hash>/fig_cumulative_net.png   somme cumulée brute / nette (si les trades.csv existent)
    runs/fig_demo_controls.png                monde nul vs contrôle positif (DÉMO uniquement)
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parent
RUNS = ROOT / "runs"
# Palette catégorielle validée (ordre fixe, CVD-safe pour 3 séries) + encre / grille
SERIES = {"E01": "#2a78d6", "E02": "#eb6834", "E03": "#1baf7a"}
OTHER = "#52514e"                     # expériences proposées automatiquement (E04...)
INK, INK2, GRID, AXIS, SURFACE = "#0b0b0b", "#52514e", "#e1e0d9", "#c3c2b7", "#fcfcfb"
NAMES = {"E01": "E01 cassure (référence)", "E02": "E02 cassure + vol. haute", "E03": "E03 cassure + vol. basse"}
FOOTER = {"DÉMO": "DONNÉES SYNTHÉTIQUES — aucun résultat de marché réel. XAUUSD M5 simulé, coûts inclus.",
          "RÉEL": "DONNÉES HISTORIQUES RÉELLES — XAUUSD M5, coûts modélisés inclus. Recherche uniquement, "
                  "pas une recommandation."}


def data_label(data_mode) -> str:
    """'DÉMO' pour tout mode synthétique (DEMO, DEMO_POSITIVE_CONTROL, DEMO_NULL_WORLD), sinon 'RÉEL'."""
    return "DÉMO" if str(data_mode).upper().startswith("DEMO") else "RÉEL"


def _style(ax):
    ax.set_facecolor(SURFACE)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(AXIS)
    ax.tick_params(colors=INK2, labelsize=9)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def _ci_rows(df: pd.DataFrame) -> list:
    """Expériences simples ayant un IC (les analyses de sensibilité n'en ont pas), puis tests finaux."""
    rows = []
    dev = df[(df["split"] == "DEV") & df["ci_low_bps"].notna()]
    for e in dict.fromkeys(dev["exp_id"]):
        rows.append((f"{e}\ndév.", dev[dev["exp_id"] == e].iloc[-1], SERIES.get(e, OTHER)))
    test = df[(df["split"] == "TEST") & df["ci_low_bps"].notna()]
    for e in dict.fromkeys(test["exp_id"]):
        rows.append((f"{e}\ntest final", test[test["exp_id"] == e].iloc[-1], SERIES.get(e, OTHER)))
    return rows


def _ci_panel(ax, df: pd.DataFrame, title: str):
    _style(ax)
    rows = _ci_rows(df)
    for i, (lab, r, col) in enumerate(rows):
        filled = r["decision"] == "ACCEPT_CANDIDATE"
        ax.plot([i, i], [r["ci_low_bps"], r["ci_high_bps"]], color=col, linewidth=2, solid_capstyle="round")
        ax.plot(i, r["net_exp_bps"], "o", markersize=9, color=col,
                markerfacecolor=col if filled else SURFACE, markeredgewidth=2)
        ax.annotate(f"{r['net_exp_bps']:+.2f}\n{str(r['decision']).replace('_CANDIDATE', '')}",
                    (i, r["ci_high_bps"]), xytext=(0, 6), textcoords="offset points",
                    ha="center", va="bottom", fontsize=8, color=INK2)
    ax.axhline(0, color=AXIS, linewidth=1)
    ax.set_xticks(range(len(rows)), [r[0] for r in rows])
    ax.set_xlim(-0.6, max(len(rows), 1) - 0.4)
    ax.set_title(title, fontsize=10, color=INK, loc="left", pad=8)
    return rows


def _finish(fig, suptitle: str, label: str, out: Path) -> str:
    fig.suptitle(suptitle, fontsize=11, color=INK, x=0.01, ha="left")
    fig.text(0.01, 0.005, FOOTER[label], fontsize=8, color=INK2)
    fig.tight_layout(rect=(0, 0.03, 1, 0.95))
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150, facecolor=SURFACE)
    plt.close(fig)
    return suptitle


def ci_figure(df: pd.DataFrame, data_hash: str, out: Path) -> str:
    """Espérance nette (point) et IC 95 % (trait) de chaque expérience d'UN jeu de données."""
    label = data_label(df["data_mode"].iloc[-1])
    fig, ax = plt.subplots(figsize=(8, 4.6), facecolor=SURFACE)
    rows = _ci_panel(ax, df, f"Jeu de données {data_hash} ({label})")
    if rows:
        lo = min(float(r["ci_low_bps"]) for _, r, _ in rows)
        hi = max(float(r["ci_high_bps"]) for _, r, _ in rows)
        ax.set_ylim(min(lo, 0) - 0.5, max(hi, 0) + 2.2)
    ax.set_ylabel("Espérance nette par trade (bps)\npoint = moyenne, trait = IC 95 % bootstrap", color=INK2, fontsize=9)
    return _finish(fig, f"{label} — ce que le labo conclut : rond plein = ACCEPT, rond vide = rejet / non concluant",
                   label, out)


def cumulative_figure(df: pd.DataFrame, data_hash: str, out: Path, runs_root: Path = RUNS) -> str | None:
    """Somme cumulée des rendements par trade (brut et net) des expériences simples d'UN jeu.
    Retourne None (et n'écrit rien) si aucun trades.csv n'est disponible : ils ne sont pas
    versionnés et se régénèrent en relançant l'expérience."""
    label = data_label(df["data_mode"].iloc[-1])
    exps = [e for e in dict.fromkeys(df[(df["split"] == "DEV") & df["ci_low_bps"].notna()]["exp_id"])
            if (runs_root / data_hash / e / "trades.csv").exists()]
    if not exps:
        return None
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), sharey=True, facecolor=SURFACE)
    for ax, col, title in zip(axes, ("gross_bps", "net_bps"), ("Avant coûts (brut)", "Après coûts (net)")):
        _style(ax)
        for e in exps:
            t = pd.read_csv(runs_root / data_hash / e / "trades.csv", parse_dates=["exit_time"])
            y = t[col].cumsum()
            ax.plot(t["exit_time"], y, color=SERIES.get(e, OTHER), linewidth=2, label=NAMES.get(e, e))
            ax.annotate(f"{e} {y.iloc[-1]:+,.0f}", (t["exit_time"].iloc[-1], y.iloc[-1]),
                        xytext=(4, 0), textcoords="offset points", fontsize=8, color=INK2, va="center")
        ax.axhline(0, color=AXIS, linewidth=1)
        ax.set_title(title, fontsize=10, color=INK, loc="left", pad=8)
        ax.tick_params(axis="x", rotation=30)
    axes[0].set_ylabel("Somme cumulée des rendements par trade (bps)", color=INK2, fontsize=9)
    axes[1].legend(frameon=False, fontsize=8, loc="lower left", labelcolor=INK2)
    return _finish(fig, f"{label} — jeu {data_hash} — trades hors échantillon des 4 plis walk-forward",
                   label, out)


def demo_controls_figure(results: pd.DataFrame, positive: pd.DataFrame, out: Path) -> str | None:
    """Monde nul (DÉMO) à gauche, contrôle positif (DÉMO) à droite. Seules les lignes DÉMO sont
    lues : le monde nul est le dernier jeu dont data_mode vaut exactement 'DEMO'."""
    null_all = results[results["data_mode"].astype(str) == "DEMO"]
    pos = positive[positive["data_mode"].astype(str).str.upper().str.startswith("DEMO")]
    if null_all.empty or pos.empty:
        return None
    null = null_all[null_all["data_hash"] == null_all["data_hash"].iloc[-1]]
    panels = [(f"Monde nul (DÉMO, aucun avantage) — {null['data_hash'].iloc[0]}", null),
              (f"Contrôle positif (DÉMO, momentum planté) — {pos['data_hash'].iloc[0]}", pos)]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6), sharey=True, facecolor=SURFACE)
    top = max(float(df["ci_high_bps"].max()) for _, df in panels)
    bottom = min(float(df["ci_low_bps"].min()) for _, df in panels)
    axes[0].set_ylim(bottom - 0.5, top + 2.2)
    for ax, (title, df) in zip(axes, panels):
        _ci_panel(ax, df, title)
    axes[0].set_ylabel("Espérance nette par trade (bps)\npoint = moyenne, trait = IC 95 % bootstrap", color=INK2, fontsize=9)
    return _finish(fig, "DÉMO — contrôles du labo : rond plein = ACCEPT, rond vide = rejet / non concluant",
                   "DÉMO", out)


def dataset_figures(results: pd.DataFrame, runs_root: Path = RUNS, mode: str = "all",
                    data_hash: str | None = None) -> dict[str, list[tuple[Path, str]]]:
    """Écrit les figures de chaque jeu retenu (filtre par mode DÉMO/RÉEL et/ou par hash).
    Retourne {data_hash: [(fichier, titre), ...]}."""
    written: dict[str, list[tuple[Path, str]]] = {}
    for h, g in results.groupby(results["data_hash"].astype(str), sort=False):
        label = data_label(g["data_mode"].iloc[-1])
        if (data_hash and h != data_hash) or (mode == "real" and label != "RÉEL") or \
                (mode == "demo" and label != "DÉMO"):
            continue
        d = runs_root / h
        written[h] = [(d / "fig_ci.png", ci_figure(g, h, d / "fig_ci.png"))]
        t = cumulative_figure(g, h, d / "fig_cumulative_net.png", runs_root)
        if t is None:
            print(f"  {h} ({label}) : aucun trades.csv -> figure cumulée non régénérée")
        else:
            written[h].append((d / "fig_cumulative_net.png", t))
    return written


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=["all", "real", "demo"], default="all")
    ap.add_argument("--hash", dest="data_hash")
    args = ap.parse_args(argv)
    results = pd.read_csv(ROOT / "results.csv")
    for h, files in dataset_figures(results, RUNS, args.mode, args.data_hash).items():
        for p, title in files:
            print(f"  {p.relative_to(ROOT)} — {title}")
    pos_path = RUNS / "controls" / "positive_control.csv"
    if args.mode in ("all", "demo") and not args.data_hash and pos_path.exists():
        out = RUNS / "fig_demo_controls.png"
        if demo_controls_figure(results, pd.read_csv(pos_path), out):
            print(f"  {out.relative_to(ROOT)} — contrôles DÉMO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
