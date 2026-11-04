# Mémoire de recherche — QuantLab

Ce fichier est la **mémoire longue** du laboratoire : ce qu'on a appris, les erreurs commises
(et corrigées) et les pistes suivantes. La partie entre `AUTO:START` et `AUTO:END` est régénérée
par `experiment_runner.py` à chaque run. Le reste est écrit à la main et n'est jamais effacé :
on y **ajoute**.

---

## 1. Règles permanentes (apprises ou imposées)

1. **Aucune performance DÉMO n'est un résultat de marché.** Le jeu démo est un *instrument de
   contrôle* : un monde sans avantage (contrôle négatif) ou avec un avantage planté connu
   (contrôle positif).
2. **Le test final ne sert qu'une fois**, et seulement pour un candidat `ACCEPT_CANDIDATE`.
   Le runner le refuse sinon (vérifié : `--final-test E02` refusé sur le monde nul).
3. **Toute modification de `evaluation.py` / `backtest.py` passe par `--relock` avec une raison
   écrite**, et doit intervenir *avant* les expériences qu'elle concerne. Chaque ligne de
   `results.csv` porte le hash de l'évaluateur utilisé.
4. **Tout essai compte** : chaque configuration testée (sensibilité comprise) entre dans la
   correction de Holm et dans le N du Deflated Sharpe.
5. **On n'inverse pas le signe d'une stratégie après coup** parce qu'elle perd. Le « fade »
   (famille B) n'est proposé automatiquement que si aucun signal brut n'est détectable, et il
   est alors traité comme une hypothèse concurrente, comptée comme un essai de plus.

## 2. Découvertes (sur DÉMO : elles valident l'instrument, pas le marché)

| Date | Constat | Preuve | Portée |
|---|---|---|---|
| 2026-11-04 | Sur un monde sans avantage, le protocole rejette E01–E03 et classe la sensibilité « FRAGILE_OR_NULL » (9/9 configurations à espérance nette < 0) | `results.csv`, `runs/E04/summary.json` | Instrument |
| 2026-11-04 | Taux de faux positifs mesuré : **0/30** hypothèses acceptées sur 10 autres mondes nuls (t brut : moyenne 0,21, écart-type 0,88, extrêmes −1,91 / +1,77) | `runs/controls/null_calibration.csv` | Instrument (borne sup. ≈ 10 % à 95 %, règle des 3/n) |
| 2026-11-04 | Le labo **détecte** un momentum planté : E01 et E02 acceptées, E02 > E01, E03 rejetée, sensibilité ROBUST 9/9 | `runs/controls/positive_control.csv` | Instrument (puissance) |
| 2026-11-04 | **Mais le candidat E02 du contrôle positif échoue au test final** (net −0,54 bps, IC [−2,82 ; +1,86]) : le régime qui porte l'effet était actif 60 % du temps en développement et **21 %** sur la période de test | Rejeu du générateur (`report.md`, §6.2) | Leçon générale : **non-stationnarité** |
| 2026-11-04 | La variable `vol_regime` (vol. 1 j / vol. 20 j) est un ratio **relatif**. Elle ne mesure pas le niveau **absolu** de volatilité lente qui portait l'effet planté. Le filtre filtrait donc « à côté » | Construction du générateur vs `features.py` | Piste : tester un filtre de niveau absolu |
| 2026-11-04 | Le coût d'environ 1 bp par aller-retour, multiplié par 12 trades/jour (E01), suffit à détruire une stratégie : c'est −51 % de drawdown en 21 mois à un levier moyen de 0,9× | `results.csv` (E01) | Général : **le turnover est un risque** |

## 3. Erreurs commises et corrections (traçabilité)

| # | Erreur | Détectée par | Correction | Impact sur les décisions |
|---|---|---|---|---|
| 1 | Test « entrées aléatoires » non stratifié : une stratégie filtrée sur la forte volatilité était comparée à un hasard moins dispersé → p-values trop optimistes | Relecture pendant le contrôle positif, **avant** le run officiel | Stratification tercile de vol × session (`evaluation.random_entry_null`) ; relock | Aucune (corrigé avant les expériences) |
| 2 | Taille de position « 0,25 % par ATR M5 » : pour un trade tenu 12 barres, le risque réel était ≈ √12 ≈ 3,5 fois plus grand qu'annoncé (levier effectif ≈ 3,6×, drawdown E01 −92 %) | Risk Manager, après le run officiel V1.0 | V1.1 : ATR × √hold + Monte Carlo des séries de pertes ; relock ; run V1.0 **archivé** dans `runs/archive/v1.0/` | Aucune (métrique principale et trades identiques) |
| 3 | Chemins des fichiers de trades et de `test_access.json` mal construits hors du dossier principal (contrôles) | Calibration du monde nul | Chemins explicites depuis `ROOT` | Aucune |
| 4 | t brut = −2,0 pour E01 dans le monde nul, sans aucun signal | Lecture des résultats | **Pas une erreur** : sur 10 autres mondes nuls, t varie de −1,9 à +1,8. Un |t| ≈ 2 arrive par hasard ; ne jamais conclure sur un t isolé | — |

## 4. Pièges identifiés pour la suite (données réelles)

- **Dérive de l'or** : l'or a fortement monté sur 2023–2026. Une stratégie à biais acheteur
  paraîtra bonne. Seule la comparaison aux **entrées aléatoires de même ratio achat/vente**
  (déjà implémentée) neutralise cet effet.
- **Saisonnalité** : un filtre de volatilité M5 brut est un filtre horaire déguisé. Toujours
  regarder la ventilation par session (`by_session` dans `summary.json`).
- **Spread des exports MT5** : la colonne `<SPREAD>` est souvent le spread **minimum** de la
  barre → coûts sous-estimés. Garder le plancher `min_spread` et regarder les scénarios de stress.
- **Heure serveur MT5** : décalage fixe dans la config (UTC+2 / +3), changement d'heure non géré
  en V1 → erreur possible d'1 h sur les sessions pendant une partie de l'année.
- **Annonces macro** (NFP, CPI, FOMC) : spreads et slippage explosent. Ils ne sont pas modélisés
  en V1 : les scénarios « combined » (spread × 2, slippage × 4) ne sont qu'un proxy.

## 5. Questions ouvertes

1. Sur **données réelles** XAUUSD M5, E01–E03 se comportent-elles comme dans le monde nul ?
   (C'est la seule question qui compte pour la suite.)
2. Quelle est la **puissance** du protocole pour un effet plus faible (par exemple +1 bp net) ?
   Rejouer le contrôle positif avec `positive_control_edge` = 0,1 / 0,15 / 0,2.
3. La structure du marché réel (autocorrélation, ratio de variance par session) justifie-t-elle
   la famille A (momentum) ou plutôt la famille B (retour à la moyenne) ?

---

<!-- AUTO:START -->
### Journal automatique (mis à jour 2026-11-04T01:18:08+00:00)

> **MODE DÉMO — données synthétiques. Aucun chiffre ci-dessous n'est un résultat de marché réel.**

Données : `SYNTHETIC_DEMO(seed=42,planted_edge=0.0)` — hash `636e8307230d031c` — 213,961 barres M5

| exp_id | split | data_mode | name | n_trades | gross_exp_bps | cost_bps | net_exp_bps | ci_low_bps | ci_high_bps | profit_factor | win_rate | max_dd_pct | sharpe_ann | frac_folds_positive | p_null | p_null_holm | dsr | stress_combined_net_bps | decision |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| E01 | DEV | DEMO | baseline_breakout | 5753 | -0.779 | 1.066 | -1.845 | -2.582 | -1.073 | 0.828 | 0.466 | -51.431 | -4.078 | 0.000 | 0.981 | 0.981 | 0.000 | -3.282 | REJECT |
| E02 | DEV | DEMO | breakout_high_vol | 1768 | -0.634 | 1.102 | -1.735 | -3.495 | 0.009 | 0.873 | 0.475 | -17.953 | -2.053 | 0.000 | 0.772 | 1.000 | 0.012 | -3.207 | REJECT |
| E03 | DEV | DEMO | breakout_low_vol | 1526 | 0.302 | 0.993 | -0.692 | -1.567 | 0.159 | 0.902 | 0.473 | -16.829 | -1.813 | 0.250 | 0.295 | 0.884 | 0.033 | -2.052 | REJECT |
| E04 | DEV | DEMO | sensitivity_E02 | 15876 |  |  | -1.187 |  |  |  |  |  |  |  |  |  |  |  | FRAGILE_OR_NULL |

### Prochaines expériences proposées (règles de `propose_next`)

- (manuel / nouveau code) **session_effects** — Mesurer l'effet heure/session (C. microstructure) : rendement, volatilité et spread par tranche de 30 min, avant de construire une stratégie horaire.
- (manuel / nouveau code) **variance_ratio_diagnostic** — Test du ratio de variance (Lo & MacKinlay 1988) et autocorrélation des rendements M1/M5 par régime : diagnostic direct de momentum vs retour à la moyenne, sans stratégie.
- (manuel / nouveau code) **logistic_baseline** — Famille D : régression logistique (scikit-learn) sur variables causales, labels à horizon fixe, purge + embargo. Uniquement après des diagnostics montrant une structure exploitable.
<!-- AUTO:END -->
