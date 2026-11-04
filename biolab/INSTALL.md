# Installation — iMac Intel 2017 (macOS), sans GPU

Durée : environ 15 minutes. Il n'y a rien à payer et aucun compte à créer.

## Ce qui a été vérifié pour votre machine

| Composant | Version choisie | Pourquoi |
|---|---|---|
| Python | 3.12 | bien supporté par toutes les bibliothèques ci-dessous |
| RDKit | **2025.9.3** | **dernière version publiée avec des paquets précompilés pour Mac Intel** (les versions 2025.9.4 et suivantes n'existent que pour Mac Apple Silicon) |
| NumPy / pandas / scikit-learn / matplotlib | 2.3.5 / 2.3.3 / 1.7.2 / 3.10.7 | paquets Mac Intel disponibles |

La liste complète et figée est dans `requirements.txt`. Nous avons vérifié
que l'installation se résout **uniquement avec des paquets précompilés** pour
`x86_64-apple-darwin` + Python 3.12. Il n'y a donc rien à compiler sur votre Mac :

```bash
uv pip compile requirements.in --python-version 3.12 \
   --python-platform x86_64-apple-darwin --only-binary :all:
```

⚠️ **À savoir pour la suite (deep learning)** : PyTorch ne publie plus de
version pour Mac Intel depuis la 2.2.2. DeepChem et les réseaux de neurones
sur graphes seront donc limités en local. Pour ces étapes, le laboratoire
proposera Google Colab (gratuit) ou un autre service cloud, **toujours avec
votre accord préalable** s'il y a un coût.

## Étapes

### 1. Ouvrir le Terminal
Applications → Utilitaires → Terminal.

### 2. Installer `uv` (gestionnaire Python moderne, un seul outil)
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```
Fermez puis rouvrez le Terminal.

### 3. Récupérer le projet
```bash
git clone https://github.com/mouchey/autoresearch.git
cd autoresearch
git checkout autoresearch-biology-v1
cd biolab
```

### 4. Créer l'environnement et installer les bibliothèques
```bash
uv venv --python 3.12          # télécharge Python 3.12 si nécessaire
source .venv/bin/activate      # à refaire à chaque nouveau Terminal
uv pip sync requirements.txt   # installe EXACTEMENT les versions testées
```

Variante sans `uv` (Python 3.12 déjà installé depuis python.org) :
```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 5. Vérifier que tout fonctionne
```bash
python -m pytest -q                  # 17 tests doivent passer
python molecule_features.py          # affiche quelques descripteurs
```

### 6. Reproduire la mission M1
```bash
python experiment_runner.py describe   # télécharge ESOL, contrôle qualité
python experiment_runner.py status     # état du laboratoire (résultats déjà enregistrés)
```
Pour **refaire** toutes les expériences depuis zéro :
```bash
mv runs runs_reference                  # garde les résultats de référence de côté
python experiment_runner.py run         # ~5 à 10 min sur un iMac 2017
python experiment_runner.py final       # évaluation unique du test
```
Comparez ensuite `results.csv` avec la version enregistrée dans Git
(`git diff results.csv`). Hors colonnes de date, de durée et de commit, les
chiffres doivent être **identiques**, car les graines aléatoires sont fixées.

## Problèmes fréquents

| Symptôme | Solution |
|---|---|
| `No matching distribution found for rdkit==2025.9.3` | vérifiez `python --version` (3.10 à 3.14 sont supportés pour RDKit ; ce projet est testé en 3.12) |
| `xcrun: error: invalid active developer path` | `xcode-select --install` (outils Apple pour `git`) |
| Erreur SHA-256 au téléchargement | le fichier distant a changé : ne pas continuer, voir `data/PROVENANCE.md` |
| Calcul trop lent | réduire `n_jobs` ou les graines dans `research_config.yaml` **crée une nouvelle mission** : notez-le dans `research_memory.md` |
