"""
data_loader.py — Chargement, contrôle qualité et découpage du jeu de données.

Ce module fait trois choses :
  1. TÉLÉCHARGER le fichier ESOL et vérifier son empreinte SHA-256 (on est sûr
     de travailler exactement sur le même fichier que dans les résultats publiés
     par ce laboratoire) ;
  2. NETTOYER les données : lecture des SMILES par RDKit, détection des
     doublons structuraux, vérification des unités et des valeurs manquantes ;
  3. DÉCOUPER en entraînement / validation / test, de deux façons :
       - "random"   : tirage aléatoire des molécules ;
       - "scaffold" : regroupement par échafaudage moléculaire (Bemis-Murcko),
                      pour tester la généralisation à des familles chimiques
                      jamais vues pendant l'entraînement.

Usage rapide (dans un terminal, depuis le dossier biolab/) :
    python data_loader.py          # télécharge, vérifie et affiche un rapport
"""

from __future__ import annotations

import hashlib
import shutil
import tempfile
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from rdkit import Chem, RDLogger
from rdkit.Chem.Scaffolds import MurckoScaffold

# RDKit affiche beaucoup d'avertissements ; on les coupe pour garder une sortie lisible.
RDLogger.DisableLog("rdApp.*")

LAB_DIR = Path(__file__).resolve().parent


# ---------------------------------------------------------------------------
# 0. Configuration
# ---------------------------------------------------------------------------
def load_config(path: str | Path = LAB_DIR / "research_config.yaml") -> dict:
    """Lit le fichier YAML de configuration et le renvoie sous forme de dictionnaire."""
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# 1. Téléchargement + vérification d'intégrité
# ---------------------------------------------------------------------------
def sha256_of(path: Path) -> str:
    """Empreinte SHA-256 d'un fichier : si un seul octet change, l'empreinte change."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 16), b""):
            h.update(block)
    return h.hexdigest()


def download_dataset(cfg: dict) -> Path:
    """Télécharge le CSV si absent, puis vérifie son empreinte SHA-256."""
    data_cfg = cfg["data"]
    target = LAB_DIR / data_cfg["local_path"]
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        print(f"Téléchargement de {data_cfg['url']} ...")
        # On télécharge d'abord dans un fichier temporaire : un téléchargement
        # interrompu ne laisse jamais de fichier corrompu à la place du vrai.
        with tempfile.NamedTemporaryFile(delete=False, dir=target.parent) as tmp:
            with urllib.request.urlopen(data_cfg["url"], timeout=60) as resp:
                shutil.copyfileobj(resp, tmp)
        Path(tmp.name).replace(target)

    digest = sha256_of(target)
    if digest != data_cfg["sha256"]:
        raise ValueError(
            "L'empreinte SHA-256 du fichier ne correspond pas à celle enregistrée.\n"
            f"  attendu : {data_cfg['sha256']}\n  obtenu  : {digest}\n"
            "Le fichier source a peut-être changé : NE PAS comparer les résultats "
            "avec ceux du laboratoire sans investiguer (voir data/PROVENANCE.md)."
        )
    return target


# ---------------------------------------------------------------------------
# 2. Nettoyage et contrôle qualité
# ---------------------------------------------------------------------------
def murcko_scaffold(smiles: str) -> str:
    """Échafaudage de Bemis-Murcko : on garde les cycles et les chaînes qui les
    relient, on enlève les chaînes latérales. Une molécule sans cycle a un
    échafaudage vide ("")."""
    mol = Chem.MolFromSmiles(smiles)
    return MurckoScaffold.MurckoScaffoldSmiles(mol=mol, includeChirality=False)


def clean_dataset(raw: pd.DataFrame, cfg: dict) -> tuple[pd.DataFrame, dict]:
    """Transforme le CSV brut en table propre, une ligne par structure unique.

    Renvoie (table_propre, rapport_qualite). Le rapport documente chaque
    décision (lignes rejetées, doublons fusionnés...) pour la traçabilité.
    """
    d = cfg["data"]
    report: dict = {"n_raw_rows": int(len(raw))}

    # -- Valeurs manquantes --------------------------------------------------
    report["missing_values_per_column"] = {k: int(v) for k, v in raw.isna().sum().items()}
    df = raw.dropna(subset=[d["smiles_column"], d["target_column"]]).copy()

    # -- Lecture des SMILES par RDKit ----------------------------------------
    df["mol"] = [Chem.MolFromSmiles(s.strip()) for s in df[d["smiles_column"]]]
    bad = df["mol"].isna()
    report["n_unparsable_smiles"] = int(bad.sum())
    df = df[~bad].copy()

    # SMILES canonique : une écriture unique par molécule (le même composé peut
    # s'écrire de plusieurs façons en SMILES, ex. "OCC" et "CCO" = éthanol).
    df["canonical_smiles"] = [Chem.MolToSmiles(m) for m in df["mol"]]
    df["inchikey"] = [Chem.MolToInchiKey(m) for m in df["mol"]]
    # Les 14 premiers caractères de l'InChIKey codent la connectivité (sans la
    # stéréochimie) : c'est exactement ce que "voient" nos descripteurs 2D.
    df["inchikey14"] = df["inchikey"].str[:14]

    # -- Unités / plage plausible --------------------------------------------
    lo, hi = d["plausible_target_range"]
    y = df[d["target_column"]]
    out_of_range = (y < lo) | (y > hi)
    report["n_out_of_plausible_range"] = int(out_of_range.sum())
    df = df[~out_of_range].copy()
    report["target_unit"] = d["target_unit"]
    report["target_min"] = float(y.min())
    report["target_max"] = float(y.max())

    # -- Doublons structuraux -------------------------------------------------
    dup_cfg = d["deduplication"]
    groups = df.groupby("inchikey14", sort=False)
    rows, merged, excluded = [], [], []
    for key, g in groups:
        values = g[d["target_column"]].to_numpy()
        spread = float(values.max() - values.min())
        names = " | ".join(map(str, g[d["id_column"]]))
        if len(g) > 1:
            info = {"inchikey14": key, "names": names, "values": values.round(3).tolist(),
                    "spread": round(spread, 3)}
            if spread > dup_cfg["max_spread_log_units"]:
                excluded.append(info)
                continue  # groupe ambigu : on l'exclut
            merged.append(info)
        first = g.iloc[0]
        rows.append({
            "name": names,
            "smiles": first["canonical_smiles"],
            "inchikey14": key,
            "y": float(values.mean()),  # moyenne des mesures répétées
            "n_measurements": int(len(g)),
            "y_spread": spread,
            "esol_literature_pred": float(g[d["literature_prediction_column"]].mean()),
        })
    clean = pd.DataFrame(rows)
    clean["scaffold"] = [murcko_scaffold(s) for s in clean["smiles"]]
    clean = clean.reset_index(drop=True)

    report["duplicate_groups_merged"] = merged
    report["duplicate_groups_excluded"] = excluded
    report["n_clean_molecules"] = int(len(clean))
    report["n_unique_scaffolds"] = int(clean["scaffold"].nunique())
    report["n_acyclic_molecules"] = int((clean["scaffold"] == "").sum())
    # Les écarts entre mesures répétées d'un même composé donnent une idée
    # (grossière, peu d'exemples) du bruit expérimental.
    rep = [m["spread"] for m in merged]
    report["replicate_spread_median"] = float(np.median(rep)) if rep else None
    return clean, report


def load_dataset(cfg: dict | None = None) -> tuple[pd.DataFrame, dict]:
    """Point d'entrée principal : télécharge + vérifie + nettoie."""
    cfg = cfg or load_config()
    path = download_dataset(cfg)
    raw = pd.read_csv(path)
    clean, report = clean_dataset(raw, cfg)
    report["source_sha256"] = cfg["data"]["sha256"]
    return clean, report


# ---------------------------------------------------------------------------
# 3. Découpages entraînement / validation / test
# ---------------------------------------------------------------------------
def _sizes(n: int, fractions: dict) -> tuple[int, int, int]:
    n_train = int(round(fractions["train"] * n))
    n_valid = int(round(fractions["valid"] * n))
    return n_train, n_valid, n - n_train - n_valid


def random_split(n: int, seed: int, fractions: dict) -> dict[str, np.ndarray]:
    """Mélange les indices avec une graine fixée, puis coupe en 3 morceaux."""
    rng = np.random.default_rng(seed)
    idx = rng.permutation(n)
    n_train, n_valid, _ = _sizes(n, fractions)
    return {"train": np.sort(idx[:n_train]),
            "valid": np.sort(idx[n_train:n_train + n_valid]),
            "test": np.sort(idx[n_train + n_valid:])}


def scaffold_split(scaffolds: list[str], seed: int, fractions: dict) -> dict[str, np.ndarray]:
    """Découpage "équilibré" par échafaudage (inspiré de Chemprop, Yang et al. 2019).

    Toutes les molécules d'un même échafaudage vont dans le MÊME ensemble.
    Les grandes familles (plus de la moitié de la taille du test) vont d'abord
    en entraînement ; les autres sont réparties aléatoirement (graine fixée).
    Conséquence importante : les molécules acycliques (échafaudage vide) et les
    dérivés du benzène, très nombreux, restent toujours en entraînement.
    """
    n = len(scaffolds)
    n_train, n_valid, n_test = _sizes(n, fractions)
    groups: dict[str, list[int]] = {}
    for i, s in enumerate(scaffolds):
        groups.setdefault(s, []).append(i)
    sets = list(groups.values())
    big = [g for g in sets if len(g) > n_valid / 2 or len(g) > n_test / 2]
    small = [g for g in sets if not (len(g) > n_valid / 2 or len(g) > n_test / 2)]
    rng = np.random.default_rng(seed)
    big = [big[i] for i in rng.permutation(len(big))]
    small = [small[i] for i in rng.permutation(len(small))]
    train, valid, test = [], [], []
    for g in big + small:
        if len(train) + len(g) <= n_train:
            train += g
        elif len(valid) + len(g) <= n_valid:
            valid += g
        else:
            test += g
    return {"train": np.sort(train), "valid": np.sort(valid), "test": np.sort(test)}


def make_split(df: pd.DataFrame, split_type: str, seed: int, fractions: dict) -> dict[str, np.ndarray]:
    if split_type == "random":
        split = random_split(len(df), seed, fractions)
    elif split_type == "scaffold":
        split = scaffold_split(df["scaffold"].tolist(), seed, fractions)
    else:
        raise ValueError(f"Type de split inconnu : {split_type}")
    check_no_leakage(df, split, split_type)
    return split


def check_no_leakage(df: pd.DataFrame, split: dict[str, np.ndarray], split_type: str) -> None:
    """Vérifie qu'aucune molécule (ni, pour le split scaffold, aucun échafaudage)
    n'apparaît dans deux ensembles. Lève une erreur sinon : on ne continue
    JAMAIS une expérience avec une fuite de données."""
    names = list(split)
    all_idx = np.concatenate([split[k] for k in names])
    if len(all_idx) != len(set(all_idx.tolist())) or len(all_idx) != len(df):
        raise AssertionError("Les ensembles se chevauchent ou ne couvrent pas toutes les molécules.")
    keys = {k: set(df.loc[split[k], "inchikey14"]) for k in names}
    scaf = {k: set(df.loc[split[k], "scaffold"]) for k in names}
    for a in range(len(names)):
        for b in range(a + 1, len(names)):
            ka, kb = names[a], names[b]
            if keys[ka] & keys[kb]:
                raise AssertionError(f"Molécule dupliquée entre {ka} et {kb}.")
            if split_type == "scaffold" and scaf[ka] & scaf[kb]:
                raise AssertionError(f"Échafaudage partagé entre {ka} et {kb}.")


if __name__ == "__main__":
    cfg = load_config()
    clean, rep = load_dataset(cfg)
    print(f"Lignes brutes            : {rep['n_raw_rows']}")
    print(f"SMILES illisibles        : {rep['n_unparsable_smiles']}")
    print(f"Hors plage plausible     : {rep['n_out_of_plausible_range']}")
    print(f"Groupes de doublons fusionnés : {len(rep['duplicate_groups_merged'])}")
    print(f"Groupes ambigus exclus   : {len(rep['duplicate_groups_excluded'])}")
    for g in rep["duplicate_groups_excluded"]:
        print(f"   - {g['names']} : valeurs {g['values']}")
    print(f"Molécules propres        : {rep['n_clean_molecules']}")
    print(f"Échafaudages uniques     : {rep['n_unique_scaffolds']} "
          f"(dont {rep['n_acyclic_molecules']} molécules acycliques)")
    for st in cfg["protocol"]["split_types"]:
        s = make_split(clean, st, 0, cfg["protocol"]["fractions"])
        print(f"Split {st:8s} (graine 0) : " + ", ".join(f"{k}={len(v)}" for k, v in s.items()))
