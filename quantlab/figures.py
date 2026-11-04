"""
figures.py — figures du rapport (lit runs/ et results.csv, n'évalue rien lui-même).

    python figures.py        -> runs/fig_ci_summary.png, runs/fig_cumulative_net.png
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parent
RUNS = ROOT / "runs"
# Palette catégorielle validée (ordre fixe, CVD-safe pour 3 séries) + encre / grille
SERIES = {"E01": "#2a78d6", "E02": "#eb6834", "E03": "#1baf7a"}
INK, INK2, GRID, AXIS, SURFACE = "#0b0b0b", "#52514e", "#e1e0d9", "#c3c2b7", "#fcfcfb"
NAMES = {"E01": "E01 cassure (référence)", "E02": "E02 cassure + vol. haute", "E03": "E03 cassure + vol. basse"}


def _style(ax):
    ax.set_facecolor(SURFACE)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(AXIS)
    ax.tick_params(colors=INK2, labelsize=9)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def ci_summary(out: Path):
    null = pd.read_csv(ROOT / "results.csv")
    pos = pd.read_csv(RUNS / "controls" / "positive_control.csv")
    panels = [("Monde nul (DÉMO, aucun avantage)", null[null["split"] == "DEV"]),
              ("Contrôle positif (DÉMO, momentum planté)", pos)]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6), sharey=True, facecolor=SURFACE)
    top = max(float(df["ci_high_bps"].max()) for _, df in panels)
    bottom = min(float(df["ci_low_bps"].min()) for _, df in panels)
    axes[0].set_ylim(bottom - 0.5, top + 2.2)
    for ax, (title, df) in zip(axes, panels):
        _style(ax)
        rows = []
        for e in ("E01", "E02", "E03"):
            r = df[(df["exp_id"] == e) & (df["split"] == "DEV")]
            if len(r):
                rows.append((f"{e}\ndév.", r.iloc[-1], SERIES[e]))
        t = df[(df["exp_id"] == "E02") & (df["split"] == "TEST")]
        if len(t):
            rows.append(("E02\ntest final", t.iloc[-1], SERIES["E02"]))
        for i, (lab, r, col) in enumerate(rows):
            filled = r["decision"] == "ACCEPT_CANDIDATE"
            ax.plot([i, i], [r["ci_low_bps"], r["ci_high_bps"]], color=col, linewidth=2, solid_capstyle="round")
            ax.plot(i, r["net_exp_bps"], "o", markersize=9, color=col,
                    markerfacecolor=col if filled else SURFACE, markeredgewidth=2)
            ax.annotate(f"{r['net_exp_bps']:+.2f}\n{r['decision'].replace('_CANDIDATE', '')}",
                        (i, r["ci_high_bps"]), xytext=(0, 6), textcoords="offset points",
                        ha="center", va="bottom", fontsize=8, color=INK2)
        ax.axhline(0, color=AXIS, linewidth=1)
        ax.set_xticks(range(len(rows)), [r[0] for r in rows])
        ax.set_xlim(-0.6, len(rows) - 0.4)
        ax.set_title(title, fontsize=10, color=INK, loc="left", pad=8)
    axes[0].set_ylabel("Espérance nette par trade (bps)\npoint = moyenne, trait = IC 95 % bootstrap", color=INK2, fontsize=9)
    fig.suptitle("Ce que le labo conclut : rond plein = ACCEPT, rond vide = rejet / non concluant",
                 fontsize=11, color=INK, x=0.01, ha="left")
    fig.text(0.01, 0.005, "DONNÉES SYNTHÉTIQUES — aucun résultat de marché réel. XAUUSD M5 simulé, coûts inclus.",
             fontsize=8, color=INK2)
    fig.tight_layout(rect=(0, 0.03, 1, 0.95))
    fig.savefig(out, dpi=150, facecolor=SURFACE)
    plt.close(fig)


def cumulative(out: Path):
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), sharey=True, facecolor=SURFACE)
    for ax, col, title in zip(axes, ("gross_bps", "net_bps"), ("Avant coûts (brut)", "Après coûts (net)")):
        _style(ax)
        for e in ("E01", "E02", "E03"):
            p = RUNS / e / "trades.csv"
            if not p.exists():
                continue
            t = pd.read_csv(p, parse_dates=["exit_time"])
            y = t[col].cumsum()
            ax.plot(t["exit_time"], y, color=SERIES[e], linewidth=2, label=NAMES[e])
            ax.annotate(f"{e} {y.iloc[-1]:+,.0f}", (t["exit_time"].iloc[-1], y.iloc[-1]),
                        xytext=(4, 0), textcoords="offset points", fontsize=8, color=INK2, va="center")
        ax.axhline(0, color=AXIS, linewidth=1)
        ax.set_title(title, fontsize=10, color=INK, loc="left", pad=8)
        ax.tick_params(axis="x", rotation=30)
    axes[0].set_ylabel("Somme cumulée des rendements par trade (bps)", color=INK2, fontsize=9)
    axes[1].legend(frameon=False, fontsize=8, loc="lower left", labelcolor=INK2)
    fig.suptitle("Monde nul (DÉMO) — trades hors échantillon des 4 plis walk-forward : "
                 "sans signal, les coûts font la pente", fontsize=11, color=INK, x=0.01, ha="left")
    fig.text(0.01, 0.005, "DONNÉES SYNTHÉTIQUES — aucun résultat de marché réel.", fontsize=8, color=INK2)
    fig.tight_layout(rect=(0, 0.03, 1, 0.95))
    fig.savefig(out, dpi=150, facecolor=SURFACE)
    plt.close(fig)


if __name__ == "__main__":
    ci_summary(RUNS / "fig_ci_summary.png")
    cumulative(RUNS / "fig_cumulative_net.png")
    print("figures écrites dans runs/")
