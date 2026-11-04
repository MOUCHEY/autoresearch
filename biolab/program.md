# program.md — Protocole de l'agent de recherche (AutoResearch Biology)

Ce fichier est destiné à un **agent IA** (Claude ou autre) qui reprend le
laboratoire. C'est l'équivalent biologie du `program.md` du dépôt parent.
L'humain modifie ce fichier ; l'agent le suit.

## Rôles simulés

| Rôle | Responsabilité dans la boucle |
|---|---|
| Research Orchestrator | lit `research_memory.md`, choisit la prochaine hypothèse, respecte le budget |
| Computational Chemist | représentations moléculaires (RDKit), cohérence chimique des erreurs |
| Computational Biologist | pertinence biologique, limites d'interprétation |
| ML Scientist | modèles, protocole d'évaluation, robustesse statistique |
| Bioinformatics Engineer | code, tests, reproductibilité, environnement |
| Scientific Reviewer | vérifie références, biais, sur-interprétations **avant** toute conclusion |

## Démarrage d'une session

1. Lire `README.md`, `research_memory.md`, `scientific_hypotheses.md`, `research_config.yaml`.
2. `python experiment_runner.py status`, puis `python -m pytest -q`.
3. Ne **jamais** réutiliser le test d'une mission déjà évaluée (`final`) pour
   choisir un modèle. Une nouvelle idée, testée après `final`, doit être
   évaluée en **validation** ; son test n'est consulté qu'une fois, à la fin
   d'une **nouvelle** mission, et cette mission doit être signalée comme telle.

## Boucle (une itération = une hypothèse)

1. **Hypothèse** : une phrase testable, avec sa prédiction a priori.
2. **Justification** : un résultat antérieur (ID d'expérience) ou une référence
   **vérifiée** de `literature_review.md`. N'inventez jamais un DOI.
3. **Modification** : UNE seule, ajoutée à la fin de `experiments:` dans
   `research_config.yaml` (`base: champion` + `change:`).
4. **Commit** de la configuration AVANT l'exécution (pré-enregistrement).
5. `python experiment_runner.py run --only EXX`.
6. Lire la décision automatique (règle pré-enregistrée, comparaison appariée sur 10 découpages).
7. Analyser : le gain est-il robuste sur les deux types de split ? Est-il chimiquement plausible ?
8. Mettre à jour la partie rédigée de `research_memory.md` (les blocs `AUTO` se mettent à jour seuls).
9. Commit des résultats (y compris les résultats **négatifs**).

## Interdits

- Modifier la section `protocol` de `research_config.yaml` pour améliorer un score.
- Regarder le test pour choisir des hyperparamètres, des variables ou un modèle.
- Supprimer une expérience rejetée de l'historique.
- Présenter une prédiction comme une découverte biologique ou un effet thérapeutique.
- Lancer un calcul payant (cloud) sans accord explicite de l'humain.
- Dépasser le budget (`budget:`) sans le signaler et le justifier.
- Protocoles de laboratoire humide, culture ou manipulation d'agents biologiques :
  hors périmètre (laboratoire purement computationnel, données publiques).

## Vocabulaire obligatoire dans les rapports

- **Résultat** : mesuré par ce laboratoire, avec ID d'expérience, code et données.
- **Hypothèse** : proposition testable, pas encore testée ou non concluante.
- **Spéculation** : idée plausible sans test prévu. À étiqueter comme telle.
