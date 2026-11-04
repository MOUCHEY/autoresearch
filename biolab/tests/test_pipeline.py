"""
Tests automatiques du laboratoire (lancer avec : python -m pytest -q).

Ils vérifient les garde-fous scientifiques : pas de fuite de données entre
ensembles, découpages reproductibles, métriques correctes, règle de décision.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import data_loader  # noqa: E402
import evaluate  # noqa: E402
import molecule_features as mf  # noqa: E402
from model import build_model  # noqa: E402

CFG = data_loader.load_config()


@pytest.fixture(scope="module")
def dataset():
    df, report = data_loader.load_dataset(CFG)
    return df, report


def test_data_quality(dataset):
    df, rep = dataset
    assert rep["n_raw_rows"] == 1128
    assert rep["n_unparsable_smiles"] == 0
    assert df["inchikey14"].is_unique          # une ligne par structure
    assert df["y"].between(-15, 3).all()       # unités plausibles (log mol/L)
    assert not df["y"].isna().any()


@pytest.mark.parametrize("split_type", ["random", "scaffold"])
@pytest.mark.parametrize("seed", [0, 1, 2, 3, 4])
def test_no_leakage(dataset, split_type, seed):
    df, _ = dataset
    s = data_loader.make_split(df, split_type, seed, CFG["protocol"]["fractions"])
    assert sum(len(v) for v in s.values()) == len(df)
    for a in s:
        for b in s:
            if a < b:
                assert not set(df.loc[s[a], "inchikey14"]) & set(df.loc[s[b], "inchikey14"])
                if split_type == "scaffold":
                    assert not set(df.loc[s[a], "scaffold"]) & set(df.loc[s[b], "scaffold"])


def test_split_is_reproducible(dataset):
    df, _ = dataset
    f = CFG["protocol"]["fractions"]
    for st in ("random", "scaffold"):
        a, b = data_loader.make_split(df, st, 3, f), data_loader.make_split(df, st, 3, f)
        assert all(np.array_equal(a[k], b[k]) for k in a)


def test_leakage_is_detected():
    df = pd.DataFrame({"inchikey14": ["A", "B", "C"], "scaffold": ["x", "y", "z"]})
    bad = {"train": np.array([0, 1]), "valid": np.array([1]), "test": np.array([2])}
    with pytest.raises(AssertionError):
        data_loader.check_no_leakage(df, bad, "random")


def test_metrics():
    m = evaluate.regression_metrics([0, 0, 0, 0], [1, -1, 1, -1])
    assert m["mae"] == pytest.approx(1.0) and m["rmse"] == pytest.approx(1.0)
    assert evaluate.regression_metrics([1, 2, 3], [1, 2, 3])["r2"] == pytest.approx(1.0)


def test_decision_rule():
    rule = {"min_delta_rmse": 0.02, "min_win_fraction": 0.8}
    ref = {("random", i): 1.0 for i in range(5)} | {("scaffold", i): 1.0 for i in range(5)}
    better = {k: 0.9 for k in ref}
    assert evaluate.paired_decision(better, ref, rule)["decision"] == "keep"
    tiny = {k: 0.995 for k in ref}                        # effet trop petit
    assert evaluate.paired_decision(tiny, ref, rule)["decision"] == "reject"
    mixed = {k: (0.8 if k[1] < 3 else 1.1) for k in ref}  # gain non robuste
    assert evaluate.paired_decision(mixed, ref, rule)["decision"] == "reject"


def test_features_shapes():
    X, cols = mf.build_features(["CCO", "c1ccccc1"], ["physchem", "morgan2_2048"])
    assert X.shape == (2, 19 + 2048) and len(cols) == X.shape[1]
    X1, c1 = mf.build_features(["CCO"], ["esol4", "physchem"])  # colonnes dédoublonnées
    assert len(c1) == len(set(c1)) == 19


def test_mean_baseline_predicts_train_mean():
    m = build_model("mean", {}, seed=0)
    m.fit(np.zeros((4, 0)), np.array([1.0, 2.0, 3.0, 4.0]))
    assert np.allclose(m.predict(np.zeros((2, 0))), 2.5)
