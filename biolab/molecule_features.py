"""
molecule_features.py — Transformer une molécule en nombres (représentations).

Un modèle de machine learning ne lit pas une formule chimique : il lit un
vecteur de nombres. Ce module propose plusieurs "blocs" de représentation :

  logp          : 1 descripteur, le logP de Crippen (lipophilie calculée)
  esol4         : les 4 descripteurs de l'équation ESOL de Delaney (2004)
                  logP, masse molaire, liaisons rotatives, proportion aromatique
  physchem      : 19 descripteurs physico-chimiques interprétables
  rdkit_all     : tous les descripteurs 2D de RDKit (~217)
  morgan2_2048  : empreinte de Morgan (ECFP4), rayon 2, 2048 bits

Les descripteurs sont calculés molécule par molécule, SANS utiliser les
valeurs de solubilité : il n'y a donc aucune fuite d'information possible à
cette étape. (Les étapes qui "apprennent" quelque chose des données, comme la
normalisation, sont faites dans model.py, sur l'entraînement uniquement.)
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import rdkit
from rdkit import Chem, RDLogger
from rdkit.Chem import Crippen, Descriptors, Lipinski, rdFingerprintGenerator, rdMolDescriptors

RDLogger.DisableLog("rdApp.*")

CACHE_DIR = Path(__file__).resolve().parent / "data" / "cache"


# ---------------------------------------------------------------------------
# Descripteurs individuels
# ---------------------------------------------------------------------------
def aromatic_proportion(mol: Chem.Mol) -> float:
    """Proportion d'atomes lourds aromatiques (descripteur "AP" d'ESOL)."""
    heavy = mol.GetNumHeavyAtoms()
    arom = sum(1 for a in mol.GetAtoms() if a.GetIsAromatic())
    return arom / heavy if heavy else 0.0


def esol4(mol: Chem.Mol) -> dict[str, float]:
    """Les 4 descripteurs de l'équation ESOL (Delaney 2004), calculés avec RDKit.
    Attention : Delaney utilisait un autre logiciel pour clogP, les valeurs
    ne sont donc pas strictement identiques à celles de l'article."""
    return {
        "MolLogP": Crippen.MolLogP(mol),               # lipophilie (Wildman & Crippen 1999)
        "MolWt": Descriptors.MolWt(mol),               # masse molaire (g/mol)
        "NumRotatableBonds": Lipinski.NumRotatableBonds(mol),  # flexibilité
        "AromaticProportion": aromatic_proportion(mol),
    }


def physchem(mol: Chem.Mol) -> dict[str, float]:
    """19 descripteurs interprétables : les 4 d'ESOL + polarité, liaisons H, cycles..."""
    d = esol4(mol)
    halogens = sum(1 for a in mol.GetAtoms() if a.GetSymbol() in ("F", "Cl", "Br", "I"))
    d.update({
        "TPSA": rdMolDescriptors.CalcTPSA(mol),        # surface polaire (Å²)
        "NumHDonors": Lipinski.NumHDonors(mol),        # donneurs de liaison H
        "NumHAcceptors": Lipinski.NumHAcceptors(mol),  # accepteurs de liaison H
        "RingCount": rdMolDescriptors.CalcNumRings(mol),
        "NumAromaticRings": rdMolDescriptors.CalcNumAromaticRings(mol),
        "NumAliphaticRings": rdMolDescriptors.CalcNumAliphaticRings(mol),
        "FractionCSP3": rdMolDescriptors.CalcFractionCSP3(mol),  # "saturation"
        "HeavyAtomCount": mol.GetNumHeavyAtoms(),
        "NumHeteroatoms": rdMolDescriptors.CalcNumHeteroatoms(mol),
        "NumHalogens": halogens,
        "MolMR": Crippen.MolMR(mol),                   # réfractivité molaire
        "LabuteASA": rdMolDescriptors.CalcLabuteASA(mol),  # surface approchée
        "NHOHCount": Lipinski.NHOHCount(mol),
        "NOCount": Lipinski.NOCount(mol),
        "FormalChargeAbs": sum(abs(a.GetFormalCharge()) for a in mol.GetAtoms()),
    })
    return d


def rdkit_all(mol: Chem.Mol) -> dict[str, float]:
    """Tous les descripteurs 2D proposés par RDKit (la liste dépend de la version)."""
    return Descriptors.CalcMolDescriptors(mol)


_MORGAN = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048)


def morgan2_2048(mol: Chem.Mol) -> dict[str, float]:
    """Empreinte de Morgan : chaque bit = présence d'un motif atomique local
    (l'atome et ses voisins jusqu'à 2 liaisons). Équivalent "ECFP4"."""
    bits = _MORGAN.GetFingerprintAsNumPy(mol)
    return {f"morgan_{i}": float(b) for i, b in enumerate(bits)}


FEATURE_BLOCKS = {
    "logp": lambda m: {"MolLogP": Crippen.MolLogP(m)},
    "esol4": esol4,
    "physchem": physchem,
    "rdkit_all": rdkit_all,
    "morgan2_2048": morgan2_2048,
}


# ---------------------------------------------------------------------------
# Construction de la matrice X (avec cache disque)
# ---------------------------------------------------------------------------
def _block_matrix(smiles: list[str], block: str) -> tuple[np.ndarray, list[str]]:
    key = hashlib.sha256(("|".join(smiles) + block + rdkit.__version__).encode()).hexdigest()[:16]
    cache = CACHE_DIR / f"{block}_{key}.npz"
    if cache.exists():
        z = np.load(cache, allow_pickle=False)
        return z["X"], z["columns"].tolist()
    fn = FEATURE_BLOCKS[block]
    rows = [fn(Chem.MolFromSmiles(s)) for s in smiles]
    columns = list(rows[0].keys())
    X = np.array([[r[c] for c in columns] for r in rows], dtype=np.float64)
    # Certains descripteurs peuvent valoir +/- infini : on les marque comme
    # manquants (NaN) ; ils seront imputés dans le modèle (sur l'entraînement).
    X[~np.isfinite(X)] = np.nan
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(cache, X=X, columns=np.array(columns))
    return X, columns


def build_features(smiles: list[str], blocks: list[str]) -> tuple[np.ndarray, list[str]]:
    """Concatène les blocs demandés. Les colonnes en double (ex. MolLogP présent
    dans esol4 et physchem) ne sont gardées qu'une fois."""
    if not blocks:  # modèle "moyenne" : aucune variable
        return np.zeros((len(smiles), 0)), []
    mats, cols = [], []
    for b in blocks:
        X, c = _block_matrix(smiles, b)
        keep = [i for i, name in enumerate(c) if name not in cols]
        mats.append(X[:, keep])
        cols += [c[i] for i in keep]
    return np.hstack(mats), cols


if __name__ == "__main__":
    # Démonstration : quelques descripteurs pour l'éthanol, le benzène et la caféine.
    for name, smi in [("éthanol", "CCO"), ("benzène", "c1ccccc1"),
                      ("caféine", "Cn1cnc2c1c(=O)n(C)c(=O)n2C")]:
        d = physchem(Chem.MolFromSmiles(smi))
        print(f"{name:8s} logP={d['MolLogP']:.2f}  MW={d['MolWt']:.1f}  "
              f"TPSA={d['TPSA']:.1f}  donneurs H={d['NumHDonors']}  AP={d['AromaticProportion']:.2f}")
