# Hypothèses scientifiques

Chaque hypothèse est **testable**, rattachée à une expérience (ID), et reçoit
un statut à partir de preuves enregistrées. « Soutenue » veut dire « soutenue
par cette expérience computationnelle, avec ce protocole » : ce n'est jamais
une preuve biologique.

Règle de décision (pré-enregistrée dans `research_config.yaml`) : une
modification est conservée si le RMSE de **validation** baisse en moyenne d'au
moins 0.02 log **et** baisse dans au moins 8 des 10 paires (5 graines × split
aléatoire / scaffold), en comparaison appariée avec le champion.

## Mission M1 — tableau de suivi (mis à jour automatiquement)

<!-- AUTO:HYPOTHESES:START -->
| ID | Hypothèse | Statut | Preuve (validation, 10 paires) |
|---|---|---|---|
| E01 | Sans aucune information structurale, l'erreur est égale à la dispersion des données (≈ écart-type). Toute méthode utile doit faire mieux. | Référence | RMSE alé. 2.12 / scaf. 2.21 |
| E02 | La lipophilie (logP de Crippen) explique à elle seule une grande partie de la solubilité : plus une molécule est lipophile, moins elle est soluble. | Soutenue (modification conservée) | Δ RMSE -0.863 vs E01, 100% des paires améliorées |
| E03 | Ajouter la masse molaire, les liaisons rotatives et la proportion aromatique (les 4 descripteurs d'ESOL) améliore la régression linéaire. | Soutenue (modification conservée) | Δ RMSE -0.214 vs E02, 100% des paires améliorées |
| E04 | Un modèle non linéaire (forêt aléatoire) capture des interactions entre descripteurs que la régression linéaire ne voit pas. | Soutenue (modification conservée) | Δ RMSE -0.256 vs E03, 100% des paires améliorées |
| E05 | Ajouter polarité (TPSA), liaisons hydrogène, cycles, halogènes, etc. fournit une information complémentaire au logP. | Soutenue (modification conservée) | Δ RMSE -0.052 vs E04, 90% des paires améliorées |
| E06 | La présence/absence de sous-structures suffit à prédire la solubilité. (Prédiction a priori : moins bon, car la solubilité est une propriété globale et additive mal décrite par des bits binaires.) | Non soutenue (rejetée) | Δ RMSE +0.620 vs E05, 0% des paires améliorées |
| E07 | Les empreintes apportent une information locale (groupes fonctionnels) complémentaire aux descripteurs globaux. | Non soutenue (rejetée) | Δ RMSE -0.005 vs E05, 60% des paires améliorées |
| E08 | Un ensemble large de descripteurs contient des informations utiles absentes de notre sélection manuelle. | Non soutenue (rejetée) | Δ RMSE -0.001 vs E05, 60% des paires améliorées |
| E09 | Limiter la profondeur effective des arbres (min_samples_leaf) et le nombre de variables par division (max_features) réduit le surapprentissage. | Non soutenue (rejetée) | Δ RMSE -0.014 vs E05, 70% des paires améliorées |
| E10 | Le boosting, qui corrige séquentiellement les erreurs, est plus précis que la forêt aléatoire sur des données tabulaires de cette taille. | Non soutenue (rejetée) | Δ RMSE +0.013 vs E05, 30% des paires améliorées |
<!-- AUTO:HYPOTHESES:END -->

## Hypothèses issues de l'analyse, pas encore testées (prochaines missions)

| ID | Hypothèse | Test proposé | Type |
|---|---|---|---|
| H-M2-1 | Les erreurs de surestimation se concentrent sur les molécules à haut point de fusion (cristal stable). | Récupérer des points de fusion **vérifiés** (ex. PubChem) pour les molécules du jeu, puis tester si le résidu de validation est corrélé au point de fusion. | Hypothèse (fondée sur GSE [L10]) |
| H-M2-2 | Des empreintes de **comptage** de Morgan font mieux que les empreintes binaires. | Nouveau bloc `morgan_counts`, une seule modification vs E05. | Hypothèse |
| H-M2-3 | Le modèle E05 garde ses performances sur des molécules externes. | Validation externe sur AqSolDB [L12], après retrait des molécules d'ESOL (par InChIKey). | Hypothèse (nouvelle mission) |
| H-M2-4 | La similarité de Tanimoto à l'entraînement est un meilleur indicateur de fiabilité que l'écart-type entre arbres hors domaine. | Comparer les deux indicateurs (corrélation de Spearman, courbes erreur-vs-rejet) en validation scaffold. | Hypothèse |
| H-M2-5 | Retirer le logP dégrade fortement le modèle, et les autres descripteurs de taille ne compensent qu'en partie. | Ablation `physchem_sans_logp` (activité de la leçon 4). | Hypothèse pédagogique |
| H-M2-6 | Les conclusions (descripteurs > empreintes, forêt > linéaire) se transfèrent à la lipophilie. | Même protocole sur le jeu Lipophilicity (MoleculeNet). | Hypothèse (Phase A) |

## Spéculations (aucun test prévu pour l'instant)

- Un modèle de graphe (type Chemprop, [L3]) pourrait réduire l'erreur scaffold.
  Il demande cependant plus de calcul (GPU conseillé) ; voir les notes cloud de `scientific_report.md`.
- Une partie de l'erreur irréductible viendrait des conditions de mesure non
  renseignées (pH, température, forme solide). Par exemple, une entrée du
  fichier est notée « Chlorimuron-ethyl (ph 7) ».
