# Mémoire de recherche — AutoResearch Biology

Ce fichier est la **mémoire durable** du laboratoire. Il contient deux parties :
- une partie **rédigée** (ci-dessous) : synthèse, décisions de méthode, écarts au protocole, leçons ;
- des blocs **automatiques** (`<!-- AUTO:... -->`) régénérés à chaque exécution depuis `runs/state.json`.
  Ne les modifiez pas à la main.

---

## Mission M1 — Solubilité aqueuse (ESOL) · statut : TERMINÉE (V1)

**Question** : peut-on prédire log S (log₁₀ mol/L) à partir de la seule structure 2D ?

**Réponse (résultat, pas découverte)** : oui, partiellement. Une forêt aléatoire
sur 19 descripteurs physico-chimiques RDKit (E05) obtient sur le **test
verrouillé** un RMSE de **0.65 ± 0.04** (R² 0.90) en split aléatoire et de
**0.88 ± 0.10** (R² 0.82) en split par échafaudage. Cela correspond à une
erreur typique d'un facteur ~4 à ~8 sur la solubilité. Sur ces mêmes ensembles
de test, les prédictions publiées de l'équation ESOL (Delaney 2004) font
0.87 et 0.97.

### Ce que la mission a établi (avec preuves)

| # | Constat | Preuve |
|---|---|---|
| 1 | Le logP explique à lui seul ~2/3 de la variance | E02 : R² validation 0.67 (aléatoire) |
| 2 | La relation est non linéaire : la forêt bat la régression | E04 vs E03 : Δ −0.256, 10/10 paires |
| 3 | Des descripteurs interprétables battent largement les empreintes ECFP seules | E06 : Δ +0.620, 0/10 paires |
| 4 | Ajouter plus de variables (empreintes, 217 descripteurs) n'aide pas de façon robuste | E07, E08 : gain en split aléatoire seulement |
| 5 | Le réglage d'hyperparamètres et le boosting n'apportent rien de robuste | E09 (Δ −0.014, 7/10), E10 (Δ +0.013, 3/10) |
| 6 | La généralisation à de nouveaux échafaudages coûte ~0.2 log de RMSE | écart scaffold − aléatoire, test final |
| 7 | Les extrêmes sont tirés vers la moyenne | pente résidu/mesure −0.11 (aléatoire), −0.19 (scaffold) |
| 8 | L'erreur augmente quand la similarité à l'entraînement baisse | split scaffold : RMSE 1.01 si Tanimoto max < 0.3, 0.58 si ≥ 0.7 |
| 9 | L'incertitude de la forêt est informative en split aléatoire, presque pas en split scaffold | Spearman 0.38 vs 0.07 |

### Hypothèses de travail (non démontrées ici)

- Plusieurs des plus grosses erreurs où la solubilité est **surestimée**
  (résidu positif : simazine +2.5, anthraquinone +2.4, carbazole +1.9 log, en
  validation) concernent des molécules **planes et rigides**, dont le point de
  fusion est réputé élevé. Ce serait l'énergie du
  cristal, absente des descripteurs 2D (cf. GSE, [L10]). *Hypothèse plausible,
  non testée : il faudrait des points de fusion vérifiés.*
- Plusieurs organophosphorés et pyridines très solubles sont prédits trop peu
  solubles (Dimecron, triéthylphosphate, acéphate, méthylpyridines). Ce serait
  une famille chimique sous-représentée ou mal décrite. *Hypothèse.*

### Écarts au protocole et transparence

1. **Exécution de mise au point.** Avant l'exécution officielle, le pipeline a
   été lancé une fois dans une copie de travail pour corriger d'éventuels bugs.
   La configuration et le protocole n'ont **pas** été modifiés ensuite (commit
   de pré-enregistrement `b5ccddf`). Les deux exécutions ont donné des
   résultats **identiques au chiffre près** (34 lignes de `results.csv`, hors
   colonnes de durée et de commit). Le test a donc été calculé deux fois, mais
   aucune décision n'a été prise après l'avoir vu.
2. **Mention `b5ccddf+modifs`** (E06 à E10 et test final) : pendant l'exécution,
   un nouveau fichier (`literature_search.py`, sans lien avec le calcul) a été
   ajouté au dossier. L'ancienne fonction d'horodatage le comptait comme une
   modification. C'est désormais corrigé : les fichiers non suivis par Git
   sont ignorés. Le code de calcul exécuté est bien celui de `b5ccddf`.
3. **Commande `final`** : lancée une seule fois dans le dossier officiel
   (`test_evaluations` = 1 dans `runs/state.json`).

### Leçons de méthode pour les prochaines missions

- Commencer **toujours** par une référence triviale et un modèle physique simple.
- Une amélioration visible seulement en split aléatoire est suspecte.
- 5 graines × 2 splits avec comparaison appariée suffisent à détecter des
  effets ≥ 0.05 log ; en dessous, la variabilité domine.
- Les résultats négatifs (E06–E10) ont autant de valeur que les positifs : ils
  évitent de dépenser du calcul et orientent vers la **représentation**
  (cristal, conditions de mesure), pas vers l'algorithme.

### Budget consommé

276 s de calcul (+ ~40 s pour l'évaluation finale) sur 4 cœurs CPU, pour un
budget de 3600 s. 10 expériences sur 10 autorisées. Aucun coût cloud.

---

## Journal automatique des expériences

<!-- AUTO:JOURNAL:START -->
### E01 — Référence naïve : prédire la moyenne — 🔵 RÉFÉRENCE
- Date : 2026-11-04 01:08 UTC · commit `b5ccddf` · durée 0.0 s · empreinte `e3a233f448`
- Hypothèse : Sans aucune information structurale, l'erreur est égale à la dispersion des données (≈ écart-type). Toute méthode utile doit faire mieux.
- Justification : Principe méthodologique : un modèle doit battre la référence triviale.
- Modification (vs —) : configuration de départ
- RMSE validation : aléatoire 2.123 ± 0.110 | scaffold 2.213 ± 0.165
- R² validation : aléatoire -0.014 ± 0.018 | scaffold -0.058 ± 0.092

### E02 — Régression linéaire sur logP seul — ✅ CONSERVÉE
- Date : 2026-11-04 01:08 UTC · commit `b5ccddf` · durée 0.0 s · empreinte `dc47149cef`
- Hypothèse : La lipophilie (logP de Crippen) explique à elle seule une grande partie de la solubilité : plus une molécule est lipophile, moins elle est soluble.
- Justification : Equation générale de solubilité (Ran & Yalkowsky 2001) : log S dépend de logP et du point de fusion ; Delaney 2004 : logP est le descripteur le plus important d'ESOL.
- Modification (vs E01) : features: [] → ['logp'] ; model: mean → linear
- RMSE validation : aléatoire 1.209 ± 0.148 | scaffold 1.402 ± 0.200
- R² validation : aléatoire 0.666 ± 0.084 | scaffold 0.571 ± 0.110
- Comparaison appariée : Δ RMSE = -0.863 ± 0.208, 100% des paires améliorées → **keep**

### E03 — Reproduction de la forme ESOL (4 descripteurs, linéaire) — ✅ CONSERVÉE
- Date : 2026-11-04 01:08 UTC · commit `b5ccddf` · durée 0.0 s · empreinte `adf6770f4d`
- Hypothèse : Ajouter la masse molaire, les liaisons rotatives et la proportion aromatique (les 4 descripteurs d'ESOL) améliore la régression linéaire.
- Justification : Delaney 2004 : équation ESOL à 4 descripteurs.
- Modification (vs E02) : features: ['logp'] → ['esol4']
- RMSE validation : aléatoire 1.010 ± 0.098 | scaffold 1.173 ± 0.123
- R² validation : aléatoire 0.768 ± 0.046 | scaffold 0.703 ± 0.040
- Comparaison appariée : Δ RMSE = -0.214 ± 0.085, 100% des paires améliorées → **keep**

### E04 — Premier Random Forest (mêmes 4 descripteurs) — ✅ CONSERVÉE
- Date : 2026-11-04 01:08 UTC · commit `b5ccddf` · durée 8.3 s · empreinte `63fc1cdfc5`
- Hypothèse : Un modèle non linéaire (forêt aléatoire) capture des interactions entre descripteurs que la régression linéaire ne voit pas.
- Justification : Breiman 2001 ; usage standard en QSPR (ex. Palmer & Mitchell 2014).
- Modification (vs E03) : model: linear → random_forest ; params: {} → {'n_estimators': 500, 'min_samples_leaf': 1, 'max_features': 1.0}
- RMSE validation : aléatoire 0.737 ± 0.097 | scaffold 0.934 ± 0.073
- R² validation : aléatoire 0.874 ± 0.038 | scaffold 0.809 ± 0.040
- Comparaison appariée : Δ RMSE = -0.256 ± 0.091, 100% des paires améliorées → **keep**

### E05 — Descripteurs physico-chimiques étendus (19 descripteurs) — ✅ CONSERVÉE
- Date : 2026-11-04 01:08 UTC · commit `b5ccddf` · durée 11.2 s · empreinte `5944cf91dd`
- Hypothèse : Ajouter polarité (TPSA), liaisons hydrogène, cycles, halogènes, etc. fournit une information complémentaire au logP.
- Justification : Delaney 2004 testait 9 propriétés ; la solubilité dépend aussi des interactions polaires.
- Modification (vs E04) : features: ['esol4'] → ['physchem']
- RMSE validation : aléatoire 0.694 ± 0.090 | scaffold 0.873 ± 0.070
- R² validation : aléatoire 0.889 ± 0.030 | scaffold 0.835 ± 0.023
- Comparaison appariée : Δ RMSE = -0.052 ± 0.045, 90% des paires améliorées → **keep**

### E06 — Empreintes de Morgan seules (ECFP4, 2048 bits) à la place des descripteurs — ❌ REJETÉE
- Date : 2026-11-04 01:10 UTC · commit `b5ccddf+modifs` · durée 66.8 s · empreinte `c657cb921b`
- Hypothèse : La présence/absence de sous-structures suffit à prédire la solubilité. (Prédiction a priori : moins bon, car la solubilité est une propriété globale et additive mal décrite par des bits binaires.)
- Justification : Rogers & Hahn 2010 (ECFP) ; MoleculeNet (Wu et al. 2018) l'utilise comme représentation de référence.
- Modification (vs E05) : features: ['physchem'] → ['morgan2_2048']
- RMSE validation : aléatoire 1.211 ± 0.063 | scaffold 1.595 ± 0.192
- R² validation : aléatoire 0.666 ± 0.055 | scaffold 0.452 ± 0.075
- Comparaison appariée : Δ RMSE = +0.620 ± 0.184, 0% des paires améliorées → **reject**

### E07 — Descripteurs + empreintes de Morgan combinés — ❌ REJETÉE
- Date : 2026-11-04 01:10 UTC · commit `b5ccddf+modifs` · durée 49.4 s · empreinte `afe53710ff`
- Hypothèse : Les empreintes apportent une information locale (groupes fonctionnels) complémentaire aux descripteurs globaux.
- Justification : Résultat attendu de E05/E06 ; combinaison fréquente en QSAR.
- Modification (vs E05) : features: ['physchem'] → ['physchem', 'morgan2_2048']
- RMSE validation : aléatoire 0.673 ± 0.075 | scaffold 0.884 ± 0.064
- R² validation : aléatoire 0.896 ± 0.026 | scaffold 0.830 ± 0.027
- Comparaison appariée : Δ RMSE = -0.005 ± 0.024, 60% des paires améliorées → **reject**

### E08 — Ensemble complet des descripteurs RDKit 2D (~217) — ❌ REJETÉE
- Date : 2026-11-04 01:12 UTC · commit `b5ccddf+modifs` · durée 63.5 s · empreinte `b55177d1d1`
- Hypothèse : Un ensemble large de descripteurs contient des informations utiles absentes de notre sélection manuelle.
- Justification : Pratique courante (ex. AqSolDB fournit des descripteurs 2D ; Yang et al. 2019 utilisent des descripteurs RDKit).
- Modification (vs E05) : features: ['physchem'] → ['rdkit_all']
- RMSE validation : aléatoire 0.667 ± 0.071 | scaffold 0.897 ± 0.063
- R² validation : aléatoire 0.898 ± 0.024 | scaffold 0.824 ± 0.031
- Comparaison appariée : Δ RMSE = -0.001 ± 0.038, 60% des paires améliorées → **reject**

### E09 — Réglage des hyperparamètres de la forêt (validation croisée interne) — ❌ REJETÉE
- Date : 2026-11-04 01:13 UTC · commit `b5ccddf+modifs` · durée 66.1 s · empreinte `94ef6b091a`
- Hypothèse : Limiter la profondeur effective des arbres (min_samples_leaf) et le nombre de variables par division (max_features) réduit le surapprentissage.
- Justification : Le réglage est fait UNIQUEMENT par validation croisée interne sur l'ensemble d'entraînement (groupée par échafaudage pour le split scaffold).
- Modification (vs E05) : model: random_forest → random_forest_tuned ; params: {'n_estimators': 500, 'min_samples_leaf': 1, 'max_features': 1.0} → {'n_estimators': 300, 'grid': {'min_samples_leaf': [1, 3], 'max_features': [0.33, 1.0]}, 'inner_folds': 3}
- RMSE validation : aléatoire 0.685 ± 0.072 | scaffold 0.854 ± 0.073
- R² validation : aléatoire 0.892 ± 0.026 | scaffold 0.842 ± 0.021
- Comparaison appariée : Δ RMSE = -0.014 ± 0.027, 70% des paires améliorées → **reject**
- Hyperparamètres choisis (CV interne) : {"random|0": {"max_features": 0.33, "min_samples_leaf": 1}, "random|1": {"max_features": 0.33, "min_samples_leaf": 1}, "random|2": {"max_features": 0.33, "min_samples_leaf": 3}, "random|3": {"max_features": 0.33, "min_samples_leaf": 1}, "random|4": {"max_features": 0.33, "min_samples_leaf": 1}, "scaffold|0": {"max_features": 0.33, "min_samples_leaf": 1}, "scaffold|1": {"max_features": 1.0, "min_samples_leaf": 3}, "scaffold|2": {"max_features": 0.33, "min_samples_leaf": 1}, "scaffold|3": {"max_features": 0.33, "min_samples_leaf": 1}, "scaffold|4": {"max_features": 1.0, "min_samples_leaf": 3}}

### E10 — Gradient boosting (HistGradientBoosting) à la place de la forêt — ❌ REJETÉE
- Date : 2026-11-04 01:13 UTC · commit `b5ccddf+modifs` · durée 10.7 s · empreinte `18e607747a`
- Hypothèse : Le boosting, qui corrige séquentiellement les erreurs, est plus précis que la forêt aléatoire sur des données tabulaires de cette taille.
- Justification : Algorithme alternatif courant ; XGBoost figure parmi les références de MoleculeNet.
- Modification (vs E05) : model: random_forest → hist_gradient_boosting ; params: {'n_estimators': 500, 'min_samples_leaf': 1, 'max_features': 1.0} → {'max_iter': 500, 'learning_rate': 0.05, 'min_samples_leaf': 10}
- RMSE validation : aléatoire 0.719 ± 0.089 | scaffold 0.873 ± 0.079
- R² validation : aléatoire 0.882 ± 0.030 | scaffold 0.834 ± 0.029
- Comparaison appariée : Δ RMSE = +0.013 ± 0.049, 30% des paires améliorées → **reject**

**Champion actuel : E05** · temps de calcul cumulé : 276 s / 3600 s · évaluations du test : 1
<!-- AUTO:JOURNAL:END -->

## Prochaines expériences proposées (générées par règles, à valider par un humain)

<!-- AUTO:NEXT:START -->
1. Écart scaffold − aléatoire = +0.18 log : le modèle généralise moins bien aux nouvelles familles chimiques. Piste : validation externe sur AqSolDB (Sorkun et al. 2019), après retrait des molécules déjà présentes dans ESOL (nouvelle mission, nouveau protocole).
2. Les empreintes de Morgan binaires n'ont pas aidé : tester des empreintes de COMPTAGE (nombre d'occurrences) ou un rayon 1, une seule modification à la fois.
3. Le réglage d'hyperparamètres n'apporte pas de gain robuste : ne plus investir de calcul ici tant que la représentation n'a pas changé.
4. Les résidus diminuent avec la solubilité mesurée (pente -0.11) : les molécules très peu solubles sont prédites trop solubles, et les très solubles pas assez (retour vers la moyenne). Hypothèse (équation générale de solubilité) : il manque l'information sur le cristal (point de fusion). Piste : descripteurs de symétrie/planéité, ou un jeu de données incluant le point de fusion.
5. L'incertitude de la forêt (écart-type entre arbres) est corrélée à l'erreur en split aléatoire (Spearman 0.38), mais presque plus en split scaffold (Spearman 0.07) : elle n'est PAS fiable hors du domaine connu. Piste : tester un indicateur fondé sur la similarité à l'entraînement, ou une prédiction conforme (conformal prediction), en validation.
6. Phase A suivante : lipophilie (jeu Lipophilicity de MoleculeNet, ~4200 molécules) avec exactement le même protocole, pour vérifier si les conclusions se transfèrent.
7. Comparer avec un modèle de graphe (ex. Chemprop) seulement si le gain attendu justifie le coût : à évaluer d'abord sur Google Colab (gratuit), aucune dépense sans accord.
<!-- AUTO:NEXT:END -->
