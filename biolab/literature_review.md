# Revue de littérature — Mission M1 : prédiction de la solubilité aqueuse

> **Méthode de vérification (4 novembre 2026).** Le conteneur cloud dans lequel ce
> laboratoire a été construit n'avait pas accès à PubMed, Crossref ni Europe PMC
> (réseau restreint). Les métadonnées ci-dessous (titre, auteurs, année, revue,
> volume, pages, DOI) ont été **vérifiées par recherche web** en recoupant
> plusieurs notices indépendantes (PubMed, DBLP, sites des éditeurs, dépôts
> institutionnels). Les « résultats principaux » sont tirés **des résumés**,
> pas d'une lecture complète des articles. Sur votre ordinateur, relancez la
> vérification automatique des DOI :
> `python literature_search.py verify-file literature_review.md`
>
> Légende : ✅ vérifié · ⚠️ partiellement vérifié · ❓ non vérifié

---

## 1. Article fondateur du jeu de données

### [L1] ESOL : Estimating Aqueous Solubility Directly from Molecular Structure
- **Auteur** : John S. Delaney (Syngenta, Jealott's Hill, Royaume-Uni)
- **Année / revue** : 2004, *J. Chem. Inf. Comput. Sci.* 44(3):1000–1005
- **DOI** : [10.1021/ci034243x](https://doi.org/10.1021/ci034243x) ✅
- **Question** : peut-on estimer la solubilité aqueuse directement à partir de la structure, sans mesure expérimentale (en particulier sans le point de fusion) ?
- **Méthode** : régression linéaire sur 9 propriétés moléculaires calculées ; équation finale à 4 descripteurs (clogP, masse molaire, liaisons rotatives, proportion d'atomes aromatiques).
- **Données** : 2874 solubilités mesurées pour l'ajustement (d'après le résumé). Le fichier MoleculeNet « delaney-processed.csv » (1128 lignes) contient les mesures et les prédictions ESOL.
- **Résultats principaux (résumé)** : le logP calculé est le prédicteur le plus fort ; prédictions à un facteur 5 à 8 près sur trois jeux de validation ; méthode présentée comme compétitive avec l'équation générale de solubilité (GSE).
- **Coefficients publiés** : `log S = 0.16 − 0.63·clogP − 0.0062·MW + 0.066·RB − 0.74·AP`. ⚠️ Cette équation est citée par une source **secondaire** (documentation DiaDEM, et billet de P. Walters). À vérifier dans l'article.
- **Limites / biais** : modèle linéaire ; clogP vient d'un logiciel commercial (différent du logP de Crippen de RDKit) ; on ne sait pas exactement quelles molécules du fichier MoleculeNet ont servi à ajuster l'équation. Les prédictions ESOL du fichier ne sont donc **pas** forcément des prédictions « hors échantillon ».
- **Reproductibilité** : bonne pour la forme du modèle (4 descripteurs simples). Le clogP d'origine n'est pas reproductible avec des outils libres.
- **Hypothèse dérivée** : H2/H3. Un modèle linéaire simple à base de logP capture déjà l'essentiel du signal, ce que testent E02 et E03.

## 2. Benchmarks et protocoles d'évaluation

### [L2] MoleculeNet: a benchmark for molecular machine learning
- **Auteurs** : Zhenqin Wu, Bharath Ramsundar, Evan N. Feinberg, Joseph Gomes, Caleb Geniesse, Aneesh S. Pappu, Karl Leswing, Vijay Pande
- **Année / revue** : 2018, *Chemical Science* (vol. 9, p. 513–530 ⚠️ volume et pages non revérifiés) ; prépublication [arXiv:1703.00564](https://arxiv.org/abs/1703.00564)
- **DOI** : [10.1039/C7SC02664A](https://doi.org/10.1039/C7SC02664A) ✅
- **Question** : comparer équitablement les méthodes d'apprentissage moléculaire sur des jeux de données standardisés.
- **Méthode** : jeux de données publics, découpages définis (aléatoire, échafaudage...) et métriques fixées. Implémentation dans DeepChem.
- **Données** : ESOL (1128 composés) en fait partie, avec FreeSolv et Lipophilicity.
- **Résultats (⚠️ rapportés par une recherche web, non lus dans le PDF)** : la table S5 de l'annexe donnerait, sur ESOL, un RMSE de test d'environ 1.07 pour la forêt aléatoire et 0.99 pour XGBoost. Les modèles de graphes (MPNN) feraient nettement mieux (~0.58).
- **Limites** : découpages différents des nôtres ; la forêt aléatoire utilisait probablement des empreintes ECFP (⚠️ à vérifier). La comparaison directe de nos chiffres avec les leurs est donc **impossible**.
- **Hypothèse dérivée** : H6. Une forêt sur empreintes seules fait moins bien qu'avec des descripteurs, ce que teste E06.

### [L3] Analyzing Learned Molecular Representations for Property Prediction
- **Auteurs** : Kevin Yang, Kyle Swanson, Wengong Jin, Connor Coley, et al. (dont T. Jaakkola, K. Jensen, R. Barzilay)
- **Année / revue** : 2019, *J. Chem. Inf. Model.* 59(8):3370–3388 ; correctif [10.1021/acs.jcim.9b01076](https://doi.org/10.1021/acs.jcim.9b01076)
- **DOI** : [10.1021/acs.jcim.9b00237](https://doi.org/10.1021/acs.jcim.9b00237) ✅ (PMC6727618)
- **Question** : les représentations apprises (réseaux de graphes, « Chemprop ») font-elles mieux que les descripteurs classiques, et comment les évaluer honnêtement ?
- **Méthode** : réseau de passage de messages dirigé (D-MPNN), comparé aux empreintes et descripteurs sur de nombreux jeux de données, avec des découpages aléatoires, par échafaudage et chronologiques.
- **Résultat clé (résumé et texte)** : le découpage par échafaudage approche mieux un découpage chronologique (réaliste en industrie) que le découpage aléatoire, qui est trop optimiste.
- **Limites** : un correctif publié modifie les chiffres de la forêt aléatoire de référence. Il faut citer les tables corrigées.
- **Reproductibilité** : code public (Chemprop).
- **Hypothèse dérivée** : comparer systématiquement le split aléatoire et le split scaffold (protocole). Notre implémentation du split scaffold « équilibré » s'en inspire.

### [L4] Time-Split Cross-Validation as a Method for Estimating the Goodness of Prospective Prediction
- **Auteur** : Robert P. Sheridan (Merck)
- **Année / revue** : 2013, *J. Chem. Inf. Model.* 53(4):783–790
- **DOI** : [10.1021/ci400084k](https://doi.org/10.1021/ci400084k) ✅
- **Résultat clé (résumé)** : le découpage aléatoire surestime la performance prospective. Le découpage « leave-class-out » la sous-estime. Le découpage chronologique est plus réaliste.
- **Limite pour nous** : ESOL n'a pas de dates de mesure, donc pas de split chronologique possible.
- **Hypothèse dérivée** : l'écart entre split aléatoire et split scaffold mesure l'optimisme de l'évaluation aléatoire.

### [L5] The Properties of Known Drugs. 1. Molecular Frameworks
- **Auteurs** : Guy W. Bemis, Mark A. Murcko
- **Année / revue** : 1996, *J. Med. Chem.* 39(15):2887–2893
- **DOI** : [10.1021/jm9602928](https://doi.org/10.1021/jm9602928) ✅ (PMID 8709122)
- **Contenu (résumé)** : décomposition des molécules en cycles, chaînes de liaison (« framework ») et chaînes latérales. Sur 5120 médicaments, la moitié est décrite par 32 « frameworks ».
- **Usage ici** : définition de l'**échafaudage de Bemis-Murcko** utilisé par notre split scaffold.

## 3. Représentations et modèles

### [L6] Prediction of Physicochemical Parameters by Atomic Contributions
- **Auteurs** : Scott A. Wildman, Gordon M. Crippen
- **Année / revue** : 1999, *J. Chem. Inf. Comput. Sci.* 39(5):868–873
- **DOI** : [10.1021/ci990307l](https://doi.org/10.1021/ci990307l) ✅
- **Résultats (résumé)** : logP calculé par somme de 68 contributions atomiques, ajustées sur 9920 molécules (r² = 0.918, σ = 0.677).
- **Usage ici** : `MolLogP` de RDKit implémente cette méthode. Une erreur de ~0.7 unité sur logP se propage à la solubilité prédite.

### [L7] Extended-Connectivity Fingerprints
- **Auteurs** : David Rogers, Mathew Hahn
- **Année / revue** : 2010, *J. Chem. Inf. Model.* 50(5):742–754
- **DOI** : [10.1021/ci100050t](https://doi.org/10.1021/ci100050t) ✅ (PMID 20426451)
- **Contenu** : description des empreintes ECFP, conçues pour la modélisation structure-activité.
- **Usage ici** : `morgan2_2048` (rayon 2, équivalent ECFP4).

### [L8] Random Forests
- **Auteur** : Leo Breiman
- **Année / revue** : 2001, *Machine Learning* 45(1):5–32
- **DOI** : [10.1023/A:1010933404324](https://doi.org/10.1023/A:1010933404324) ✅
- **Usage ici** : modèle principal (E04–E09).

### [L9] Scikit-learn: Machine Learning in Python
- **Auteurs** : Fabian Pedregosa, Gaël Varoquaux, Alexandre Gramfort, et al.
- **Année / revue** : 2011, *Journal of Machine Learning Research* 12:2825–2830
- **URL** : https://jmlr.org/papers/v12/pedregosa11a.html ✅ (pas de DOI)

## 4. Physico-chimie de la solubilité et qualité des données

### [L10] Prediction of Drug Solubility by the General Solubility Equation (GSE)
- **Auteurs** : Yingqing Ran, Samuel H. Yalkowsky
- **Année / revue** : 2001, *J. Chem. Inf. Comput. Sci.* 41(2):354–357 ✅ (notice [DBLP](https://dblp.org/rec/journals/jcisd/RanY01.html))
- **DOI** : ❓ **non vérifié** (10.1021/ci000338c, de mémoire, introuvable dans nos recherches). À confirmer avec `literature_search.py verify`.
- **Résultats (résumé)** : la GSE n'utilise que le **point de fusion** et le **logP**, sans paramètre ajusté. Erreur absolue moyenne de 0.43 log sur 150 composés.
- **Pourquoi c'est central** : pour un solide, la solubilité dépend aussi de l'énergie du cristal, que le point de fusion résume. Une structure 2D ne contient pas directement cette information.
- **Hypothèse dérivée** : nos plus grosses erreurs devraient concerner des molécules **planes, symétriques, à haut point de fusion**. C'est vérifié qualitativement dans le rapport (anthraquinone, carbazole, simazine).

### [L11] Is Experimental Data Quality the Limiting Factor in Predicting the Aqueous Solubility of Druglike Molecules?
- **Auteurs** : David S. Palmer, John B. O. Mitchell
- **Année / revue** : 2014, *Molecular Pharmaceutics* 11(8):2962–2972 (accès libre, CC-BY)
- **DOI** : [10.1021/mp500103r](https://doi.org/10.1021/mp500103r) ✅
- **Résultats (résumé)** : des modèles entraînés sur des mesures très précises (méthode CheqSol) ne sont **pas** plus prédictifs que ceux entraînés sur des données de la littérature, plus bruitées. La limite viendrait donc surtout des méthodes et des descripteurs, plus que du bruit expérimental.
- **Hypothèse dérivée** : améliorer la représentation (cristal, conformation) compte plus que nettoyer davantage les données.

### [L12] AqSolDB, a curated reference set of aqueous solubility and 2D descriptors for a diverse set of compounds
- **Auteurs** : Murat Cihan Sorkun, Abhishek Khetan, Süleyman Er
- **Année / revue** : 2019, *Scientific Data* 6:143 (accès libre)
- **DOI** : [10.1038/s41597-019-0151-1](https://doi.org/10.1038/s41597-019-0151-1) ✅
- **Contenu (résumé)** : 9982 composés uniques issus de 9 jeux publics, avec des structures standardisées et des étiquettes de fiabilité.
- **Hypothèse dérivée** : **validation externe**. Notre modèle ESOL, testé sur les molécules d'AqSolDB absentes d'ESOL, garde-t-il ses performances ? (prochaine mission)

## 5. Sources non relues par les pairs (à utiliser avec prudence)

### [W1] « Predicting Aqueous Solubility — It's Harder Than It Looks » (billet de blog)
- **Auteur** : W. Patrick Walters, *Practical Cheminformatics*, septembre 2018
- **URL** : https://practicalcheminformatics.blogspot.com/2018/09/predicting-aqueous-solubility-its.html ✅ (existence vérifiée)
- **Contenu** : compare l'équation ESOL à des modèles d'apprentissage DeepChem. Le code est public. Un billet de 2023 (« Getting Real with Molecular Property Prediction ») donnerait une ré-estimation de l'équation ESOL avec des descripteurs RDKit (⚠️ attribution non confirmée).
- **Statut** : billet de blog, non relu par les pairs. Utile comme guide pratique, pas comme preuve.

### [S1] Logiciel RDKit
- https://www.rdkit.org (version utilisée : 2025.09.3). Logiciel libre (BSD). C'est un logiciel, pas une publication.

---

## 6. Comparaison avec nos résultats (avec précautions)

| Source | Modèle | Découpage | RMSE (log mol/L) | Comparable à nos chiffres ? |
|---|---|---|---|---|
| Delaney 2004 [L1], prédictions du fichier | ESOL linéaire (clogP commercial) | nos tests verrouillés | 0.87 (aléatoire) / 0.97 (scaffold) | Partiellement : peut-être pas hors échantillon |
| MoleculeNet [L2] ⚠️ | Forêt aléatoire (ECFP ?) | aléatoire (le leur) | ~1.07 | Non : découpage et représentation différents |
| MoleculeNet [L2] ⚠️ | MPNN (graphe) | aléatoire (le leur) | ~0.58 | Non : découpage différent |
| **Ce laboratoire, E06** | RF sur ECFP4 seul | nos validations | 1.21 / 1.60 | Ordre de grandeur cohérent avec ~1.07 |
| **Ce laboratoire, champion E05** | RF sur 19 descripteurs | nos tests verrouillés | **0.65 / 0.88** | — |

**Leçon** : un RMSE n'a de sens qu'accompagné du jeu de données, de la version, du
découpage, des graines et du traitement des doublons. Deux chiffres publiés
obtenus avec des protocoles différents ne se comparent pas directement.
