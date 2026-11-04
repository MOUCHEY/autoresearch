# QuantLab — laboratoire AutoResearch de trading quantitatif (V1)

Un laboratoire **minimal, reproductible et contrôlable** pour tester des hypothèses de trading
comme on teste des hypothèses scientifiques : on cherche à **réfuter**, pas à confirmer.

> 🔒 **Recherche et paper trading uniquement.** Aucun code de ce dossier ne se connecte à un
> courtier ni n'envoie d'ordre. Ne l'y connecte pas sans validation préalable explicite.

> ⚠️ **État actuel : résultats sur données DÉMO (synthétiques).** Les données réelles n'étaient
> pas téléchargeables depuis l'environnement de construction. Voir [Données réelles](#2-données-réelles).

---

## 1. Démarrage (iMac Intel, macOS, CPU)

```bash
cd quantlab
python3 -m venv .venv && source .venv/bin/activate     # Python 3.10+ (3.11 recommandé)
pip install -r requirements.txt
python -m pytest -q                                    # 15 tests doivent passer
python experiment_runner.py                            # expériences pré-enregistrées (budget 10)
```

Une expérience prend environ 1 seconde sur 214 000 barres M5, plus quelques secondes de
chargement (mesuré sur un conteneur cloud à 4 cœurs ; compte 2 à 3 fois plus sur un iMac 2017).
Pic mémoire mesuré : environ 0,5 Go. Tes 32 Go laissent une marge énorme.

## 2. Données réelles

Trois options, de la plus simple à la plus fiable pour toi :

| Option | Commande / action | Spread réel ? |
|---|---|---|
| **Dukascopy** (gratuit, bid + ask M1) | `python data_loader.py fetch --start 2023-01-01 --end 2026-10-31` → `data/XAUUSD_M1.csv` (reprise possible si coupure) | ✅ ask − bid |
| **Export MetaTrader 5** de ton courtier | Outils → Symboles → XAUUSD → Barres → M1 ou M5 → Exporter → `data/XAUUSD_M1.csv`. Régler `source_utc_offset_hours` (heure serveur, souvent 2 ou 3) et `point_size` (souvent 0,01) | ≈ (souvent le minimum de la barre) |
| **HistData.com** (M1, compte gratuit) | Fichier ASCII → `data/XAUUSD_M1.csv`, `source_utc_offset_hours: -5` | ❌ spread fixe de la config |

Puis vérifie la qualité : `python data_loader.py check`, et passe `data.mode: real` dans
`research_config.yaml` (le labo refusera alors de tomber silencieusement en mode démo).
Les données ne sont **jamais** versionnées (`data/` est dans `.gitignore`).

## 3. Architecture

```
research_config.yaml ──► data_loader.py ──► features.py ──► strategy.py ─┐
 (hypothèses, budget,     (CSV/MT5/Dukascopy   (variables      (signaux,     │
  coûts, protocole)        ou DÉMO + qualité)   causales)       modifiable)   │
                                                                              ▼
 research_memory.md ◄── experiment_runner.py ◄── evaluation.py ◄── backtest.py
 report.md, results.csv   (boucle budgétée,       🔒 protégé :      🔒 protégé :
 runs/<id>/summary.json    walk-forward,          métriques, tests,  exécution t+1,
                           propositions)          décision           coûts, refus des trous
```

| Fichier | Rôle | Qui le modifie |
|---|---|---|
| `research_config.yaml` | paramètres, coûts, budget, **expériences pré-enregistrées** | humain / agent (versionné) |
| `literature_review.md` | publications, limites, banque d'hypothèses | humain / agent |
| `data_loader.py` | lecture, UTC, M1→M5, contrôle qualité, démo, téléchargement Dukascopy | rarement |
| `features.py` | variables explicatives **causales** (≤ t) | agent |
| `strategy.py` | stratégies (`fit` sur train seulement, `signals`) | **agent : le fichier d'expérimentation** |
| `backtest.py` | moteur de simulation | 🔒 **jamais sans `--relock` humain** |
| `evaluation.py` | protocole, métriques, statistiques, règle de décision | 🔒 **jamais sans `--relock` humain** |
| `experiment_runner.py` | boucle de recherche, traçabilité, propositions | rarement |
| `results.csv` | historique de toutes les expériences (avec commit, hashes) | automatique, **append-only** |
| `research_memory.md` | découvertes, erreurs, pistes | humain + bloc automatique |
| `report.md` | rapport scientifique | humain + bloc automatique |
| `figures.py` | figures du rapport | — |
| `tests/test_lab.py` | anti-fuite, exécution, protocole, intégrité | à enrichir |

## 4. Commandes

```bash
python experiment_runner.py                     # file pré-enregistrée (saute ce qui est déjà fait)
python experiment_runner.py --auto 2            # + jusqu'à 2 propositions automatiques
python experiment_runner.py --only E02 --rerun  # refaire une expérience (compte dans le budget)
python experiment_runner.py --control positive  # contrôle positif : le labo voit-il un effet planté ?
python experiment_runner.py --calibrate-null 10 # contrôle négatif : taux de faux positifs
python experiment_runner.py --final-test E02    # TEST FINAL, une seule fois, candidats acceptés seulement
python experiment_runner.py --relock "raison"   # (humain) re-verrouille l'évaluateur après relecture
python figures.py                               # régénère les figures
```

## 5. Le cycle d'une expérience (et où il vit dans le code)

1. **Hypothèse falsifiable** écrite *avant* le résultat → `research_config.yaml › experiments`
2. **Données** contrôlées → `data_loader.load_market_data` + `quality_report`
3. **Métrique principale** : espérance nette par trade en bps, après coûts → `evaluation.trade_metrics`
4. **Référence** : E01 (cassure simple) **et** le hasard (entrées aléatoires stratifiées) → `evaluation.random_entry_null`
5. **Une seule modification** à la fois (E02 = E01 + filtre de volatilité)
6. **Backtest** walk-forward (4 plis, purge et embargo) → `Lab.walk_forward`, `backtest.simulate`
7. **Traçabilité** → `results.csv` (commit Git, hash évaluateur, hash données, hash config, durée, erreurs)
8. **Comparaison** → Welch vs les trades que le filtre écarte
9. **Décision** → `evaluation.decide` (tous les critères, sinon rejet)
10. **Prochaine expérience** → `experiment_runner.propose_next` (règles explicites, écrites dans `research_memory.md`)

## 6. Ce que tu dois apprendre pour refaire tout cela toi-même

Ordre conseillé ; chaque point correspond à du code du labo que tu peux lire :

1. **Python + pandas** : `DataFrame`, index temporel, `shift`, `rolling`, `resample`
   → lis `data_loader.resample_ohlc` et `features.build_features`. Exercice : recalcule l'ATR à la main sur 20 barres.
2. **Fuite du futur** : pourquoi `shift(1)` dans `features.donchian`, pourquoi l'entrée à t+1
   → lis puis casse volontairement `tests/test_lab.py::test_features_are_causal` (retire le `shift`).
3. **Probabilités / statistiques** : moyenne, écart-type, loi de Student, intervalle de confiance,
   p-value, **bootstrap** → `evaluation.stationary_bootstrap_means`.
   Exercice : calcule à la main le t de E01 = moyenne / (écart-type / √n).
4. **Tests multiples** : pourquoi 20 tests à 5 % donnent en moyenne un faux positif → Holm, Deflated Sharpe.
5. **Microstructure** : bid/ask, spread, slippage, sessions → `backtest.py` (en-tête) et Roll (1984).
6. **Validation temporelle** : walk-forward, purge, embargo → `evaluation.make_splits` (schéma dans la docstring).
7. **Seulement ensuite, le machine learning** (scikit-learn) : régression logistique, puis arbres.

Livres : *Advances in Financial Machine Learning* (López de Prado), *Evidence-Based Technical
Analysis* (Aronson), *Python for Data Analysis* (McKinney).

## 7. Règles pour un agent AutoResearch (humain ou IA)

Voir [`program.md`](program.md).
