# program.md — consignes de l'agent de recherche QuantLab

Ce fichier joue pour la recherche quantitative le rôle que `../program.md` joue pour
l'entraînement de LLM : il programme l'**organisation de recherche**, pas le code.

## Rôles (une seule personne ou un seul agent peut les tenir tous, mais pas en même temps)

| Rôle | Responsabilité | Fichiers |
|---|---|---|
| Quant Researcher | hypothèse falsifiable, revue de littérature | `literature_review.md`, `research_config.yaml` |
| Quant Developer | variables et stratégies | `features.py`, `strategy.py` |
| Statistician | protocole et décision — **ne change qu'avant une expérience** | `evaluation.py` 🔒 |
| Risk Manager | coûts, stress, taille de position, séries de pertes | `research_config.yaml › costs/risk`, `backtest.py` 🔒 |
| Research Orchestrator | budget, file d'expériences, mémoire, rapport | `experiment_runner.py`, `research_memory.md`, `report.md` |

## Ce que tu PEUX faire

- Écrire une hypothèse dans `research_config.yaml › experiments` (nouvel `id`), **avant** de la lancer.
- Modifier `strategy.py` et `features.py` (une idée à la fois), puis committer.
- Lancer `python experiment_runner.py [--auto N]` dans la limite du budget.
- Ajouter des diagnostics, des tests et des pistes dans `research_memory.md`.

## Ce que tu ne dois JAMAIS faire

- Modifier `evaluation.py` ou `backtest.py` pour améliorer un score. Un changement de protocole
  se justifie par écrit, intervient **avant** les expériences concernées et passe par
  `--relock "raison"` après relecture humaine.
- Utiliser le test final pendant l'optimisation, ou le réutiliser (`runs/test_access.json`).
- Réécrire ou supprimer une ligne de `results.csv`. Une expérience refaite = une nouvelle ligne.
- Inverser le signe d'une stratégie perdante, ou garder la meilleure case d'une grille, sans
  la déclarer comme nouvel essai.
- Présenter un résultat DÉMO comme un résultat de marché.
- Inventer une publication ou un chiffre, ou citer un article sans l'avoir lu.
- Télécharger des données payantes, ou se connecter à un compte de courtage.
- Dépasser le budget (`budget.max_experiments`, temps par expérience, temps total).

## Boucle

```
1. Lire research_memory.md (pistes proposées, erreurs passées)
2. Choisir UNE hypothèse ; l'écrire dans research_config.yaml ; commit
3. python -m pytest -q      (doit passer)
4. python experiment_runner.py --only <ID>
5. Lire runs/<ID>/summary.json : checks, by_fold, by_session, by_vol_tercile, stress
6. Conserver (ACCEPT_CANDIDATE) ou rejeter ; consigner la leçon dans research_memory.md ; commit
7. Recommencer tant que le budget le permet, puis écrire report.md et S'ARRÊTER
```

**Critère de simplicité** : à résultat égal, la version la plus simple gagne. Un gain non
significatif qui ajoute de la complexité est rejeté.
