# AutoResearch Biology — laboratoire de biologie computationnelle (V1)

Un laboratoire de recherche **computationnelle, reproductible et pédagogique**.
Il tourne sur un ordinateur personnel (CPU, sans GPU) et mène des expériences
avec la boucle « hypothèse → expérience → mesure → décision → mémoire ».

**Première mission (terminée)** : prédire la solubilité aqueuse d'une molécule
à partir de sa structure (jeu ESOL). → Lire **[scientific_report.md](scientific_report.md)**.

| Résultat clé (test verrouillé, 5 graines) | Split aléatoire | Split par échafaudage |
|---|---|---|
| Référence naïve (moyenne) | RMSE 2.03 | RMSE 2.22 |
| Équation ESOL publiée (Delaney 2004) | RMSE 0.87 | RMSE 0.97 |
| **Champion E05 : forêt aléatoire, 19 descripteurs RDKit** | **RMSE 0.65, R² 0.90** | **RMSE 0.88, R² 0.82** |

## Démarrage rapide

```bash
cd biolab
uv venv --python 3.12 && source .venv/bin/activate
uv pip sync requirements.txt
python -m pytest -q                    # 17 tests
python experiment_runner.py status     # état du laboratoire
```
Installation détaillée pour iMac Intel : **[INSTALL.md](INSTALL.md)**.

## Organisation

| Fichier | Rôle |
|---|---|
| `research_config.yaml` | question, données (SHA-256), **protocole figé**, budget, file d'expériences |
| `data_loader.py` | téléchargement vérifié, contrôle qualité, doublons, splits aléatoire / scaffold, anti-fuite |
| `molecule_features.py` | représentations : logP, ESOL, 19 descripteurs, ~217 descripteurs, empreintes de Morgan |
| `model.py` | modèles scikit-learn (moyenne, linéaire, forêt, forêt réglée, boosting) |
| `evaluate.py` | métriques, règle de décision appariée, domaine d'applicabilité, figures |
| `experiment_runner.py` | **la boucle AutoResearch** (`describe`, `run`, `final`, `status`, `outputs`) |
| `literature_search.py` | recherche PubMed / Europe PMC (bioRxiv) / arXiv, vérification des DOI (Crossref) |
| `results.csv` | toutes les mesures (validation et test final), y compris les résultats négatifs |
| `research_memory.md` | mémoire durable : synthèse, écarts au protocole, journal automatique, prochaines étapes |
| `scientific_hypotheses.md` | hypothèses testées / à tester, avec statut et preuve |
| `literature_review.md` | références vérifiées, fiches de lecture, comparaison prudente |
| `scientific_report.md` | rapport de la mission |
| `program.md` | protocole pour un agent IA qui poursuit le travail |
| `lessons/` | 4 leçons : explication, figure, code, activité, exercice, correction, bilan |
| `runs/` | traces complètes : état, détails par expérience, prédictions, test final |
| `figures/` | figures générées |
| `data/PROVENANCE.md` | origine, licence, unités, contrôle qualité des données |

## Principes du laboratoire

1. **Pré-enregistrement** : hypothèses et règle de décision sont committées avant l'exécution.
2. **Une modification à la fois**, comparée au meilleur modèle courant sur les mêmes découpages.
3. **Le test est verrouillé** pendant la boucle ; il est évalué une seule fois, et c'est tracé.
4. **Résultats négatifs conservés.**
5. **Références vérifiées ou signalées** : aucun DOI inventé.
6. **Résultat ≠ hypothèse ≠ spéculation** ; une prédiction n'est jamais une découverte biologique.
7. **Budget explicite** ; aucun calcul payant sans accord.

## Parcours pédagogique

1. [Molécules, SMILES et RDKit](lessons/01_molecules_smiles_rdkit.md)
2. [Références, régression linéaire et métriques](lessons/02_references_et_metriques.md)
3. [Forêts aléatoires, représentations et découpages](lessons/03_random_forest_et_representations.md)
4. [Robustesse, test final, erreurs et limites](lessons/04_robustesse_erreurs_limites.md)
