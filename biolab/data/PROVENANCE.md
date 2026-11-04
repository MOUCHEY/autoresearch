# Provenance des données — ESOL

| Champ | Valeur |
|---|---|
| Nom | ESOL (Delaney), fichier `delaney-processed.csv` |
| Publication d'origine | J. S. Delaney, *J. Chem. Inf. Comput. Sci.* 2004, 44(3):1000–1005, [10.1021/ci034243x](https://doi.org/10.1021/ci034243x) |
| Distribution utilisée | MoleculeNet / DeepChem (Wu et al. 2018, [10.1039/C7SC02664A](https://doi.org/10.1039/C7SC02664A)) |
| URL de téléchargement | https://deepchemdata.s3-us-west-1.amazonaws.com/datasets/delaney-processed.csv |
| Date de téléchargement | 2026-11-04 |
| `Last-Modified` (serveur) | Fri, 10 Jul 2020 06:38:36 GMT |
| Taille | 96 699 octets, 1128 lignes de données + 1 en-tête |
| **SHA-256** | `8c06a76f0c6487d29ab0f903e6a7a7139f189ab3c1178f159c8be8964602f189` |

Le fichier n'est **pas** copié dans le dépôt Git. `data_loader.py` le télécharge
au premier lancement puis vérifie son empreinte SHA-256. Si l'empreinte change,
le programme s'arrête : les résultats ne seraient plus comparables.

## Conditions d'utilisation

- Aucune licence explicite n'est jointe au fichier CSV.
- La fiche Hugging Face communautaire du jeu `delaney` indique une licence MIT,
  attribuée à la diffusion MoleculeNet/DeepChem (DeepChem est sous licence MIT).
  ⚠️ C'est une source **secondaire**, non confirmée sur moleculenet.org.
- Ce jeu de données est utilisé très largement en recherche académique et en
  enseignement comme référence publique.
- **Notre usage** : recherche personnelle et pédagogique, sans redistribution du
  fichier. Avant tout usage commercial ou toute redistribution, vérifiez la
  licence auprès de DeepChem et de l'éditeur de l'article d'origine (ACS).

## Colonnes

| Colonne | Rôle dans le laboratoire |
|---|---|
| `Compound ID` | nom du composé (texte libre, contient des fautes : « Metranidazole ») |
| `smiles` | structure → **seule entrée des modèles** |
| `measured log solubility in mols per litre` | **cible** : log10 de la solubilité en mol/L |
| `ESOL predicted log solubility in mols per litre` | prédiction publiée par Delaney → comparaison « littérature » uniquement |
| `Minimum Degree`, `Molecular Weight`, `Number of H-Bond Donors`, `Number of Rings`, `Number of Rotatable Bonds`, `Polar Surface Area` | descripteurs précalculés : **non utilisés** (nous recalculons tout avec RDKit, de façon traçable) |

## Unités et conditions expérimentales

- Unité : log10(mol/L), d'après le nom de la colonne. Plage observée : de −11.60
  (un PCB décachloré) à +1.58 (acétamide). Aucune valeur hors de la plage plausible.
- Température : la solubilité de référence est en général mesurée vers 25 °C,
  mais le fichier ne contient **ni la température, ni le pH, ni la méthode de
  mesure**. Ces conditions ne sont pas contrôlées : c'est une source de bruit
  inconnue.
- Forme solide (polymorphe, sel, hydrate) : non renseignée.

## Contrôle qualité réalisé automatiquement (voir `runs/data_quality.json`)

| Contrôle | Résultat |
|---|---|
| Valeurs manquantes | 0 dans toutes les colonnes |
| SMILES illisibles par RDKit | 0 |
| Valeurs hors plage plausible [−15, 3] | 0 |
| Groupes de doublons structuraux (même connectivité) | 13 groupes, 26 lignes |
| → fusionnés (moyenne des valeurs) | 12 groupes (écart ≤ 0.5 log) |
| → exclus (ambigus) | 1 : **mannitol / sorbitol** (0.06 vs 1.09). Ce sont deux diastéréoisomères différents, que le SMILES sans stéréochimie confond. |
| Molécules finales | **1114** |
| Échafaudages de Bemis-Murcko distincts | 269 (+ 313 molécules acycliques) |

Exemples de doublons fusionnés : métronidazole écrit « Metranidazole » (−1.26
et −1.22), amobarbital (−2.468 et −2.658), eucalyptol et 1,8-cinéole (−1.64 et
−1.74), cis- et trans-2-pentène (même valeur −2.54 : une seule mesure a
probablement été recopiée pour les deux). Sur les 12 groupes fusionnés, 7 ont
des valeurs **strictement identiques** : c'est vraisemblablement la même mesure
recopiée sous deux noms, pas une mesure répétée. Les vraies répétitions
(métronidazole 0.04, probarbital 0.06, eucalyptol 0.10, amobarbital 0.19 log)
donnent un aperçu, très partiel (4 cas seulement), du bruit expérimental.
Androstérone et épiandrostérone (écart 0.24) sont deux stéréoisomères, pas un
même composé.

Les nitro-groupes sont écrits `N(=O)=O` dans le fichier. RDKit les convertit
automatiquement en forme chargée `[N+](=O)[O-]`, d'où 59 molécules « chargées »
qui sont en réalité neutres.
