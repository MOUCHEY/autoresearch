"""
Tests du laboratoire : ils protègent contre les erreurs qui rendent un backtest faux
sans faire planter le code (fuite du futur, exécution au mauvais prix, chevauchement
train/validation, évaluateur modifié...).  Lancer :  python -m pytest -q
"""
import lzma
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import backtest as bt  # noqa: E402
import evaluation as ev  # noqa: E402
from data_loader import decode_bi5_candles, make_demo_data, read_price_file, resample_ohlc  # noqa: E402
from features import build_features, donchian  # noqa: E402
from strategy import Breakout, VolFilteredBreakout  # noqa: E402

FEAT_CFG = {"atr_window": 14, "vol_fast_bars": 50, "vol_slow_bars": 400}


@pytest.fixture(scope="module")
def bars():
    m1 = make_demo_data("2024-01-01", "2024-01-20", seed=7)
    return resample_ohlc(m1, 5)


def tiny_bars(opens, start="2024-01-02 10:00", freq="5min", gap_after=None):
    idx = pd.date_range(start, periods=len(opens), freq=freq, tz="UTC")
    if gap_after is not None:  # trou de 2 h après la barre `gap_after`
        idx = idx + pd.to_timedelta(np.where(np.arange(len(opens)) > gap_after, 2, 0), unit="h")
    o = np.asarray(opens, dtype=float)
    return pd.DataFrame({"open": o, "high": o + 1, "low": o - 1, "close": o + 0.5,
                         "volume": 1.0, "spread": 0.2}, index=idx)


# ----------------------------------------------------------------------------- causalité
def test_features_are_causal(bars):
    """Recalculer les variables sur des données TRONQUÉES doit donner les mêmes valeurs :
    si une variable change quand on retire le futur, elle utilisait le futur."""
    full = build_features(bars, FEAT_CFG)
    k = len(bars) - 300
    cut = build_features(bars.iloc[:k], FEAT_CFG)
    num = ["ret1", "atr", "rv_fast", "rv_slow", "vol_regime"]
    pd.testing.assert_frame_equal(full[num].iloc[:k], cut[num], check_exact=False, rtol=1e-12)
    hi_f, lo_f = donchian(bars, 20)
    hi_c, lo_c = donchian(bars.iloc[:k], 20)
    pd.testing.assert_series_equal(hi_f.iloc[:k], hi_c)
    pd.testing.assert_series_equal(lo_f.iloc[:k], lo_c)


def test_signals_are_causal(bars):
    feats = build_features(bars, FEAT_CFG)
    k = len(bars) - 300
    s_full = Breakout(lookback=20, hold=12).signals(bars, feats)
    s_cut = Breakout(lookback=20, hold=12).signals(bars.iloc[:k], feats.iloc[:k])
    pd.testing.assert_series_equal(s_full.iloc[:k], s_cut)


def test_vol_threshold_learned_on_train_only(bars):
    """Modifier les données HORS train ne doit pas changer le seuil appris."""
    feats = build_features(bars, FEAT_CFG)
    mask = np.zeros(len(bars), dtype=bool)
    mask[: len(bars) // 2] = True
    a = VolFilteredBreakout(lookback=20, hold=12, regime="high", quantile=0.67).fit(bars, feats, mask)
    feats2 = feats.copy()
    feats2.loc[~mask, "vol_regime"] = 999.0
    b = VolFilteredBreakout(lookback=20, hold=12, regime="high", quantile=0.67).fit(bars, feats2, mask)
    assert a.fitted_["threshold"] == b.fitted_["threshold"]


# ----------------------------------------------------------------------------- exécution
def test_trade_executes_at_next_open_with_costs():
    b = tiny_bars(np.arange(100.0, 130.0))
    sig = pd.Series(0, index=b.index)
    sig.iloc[2] = 1
    cost = bt.CostModel(commission_roundturn=0.07, slippage_per_side=0.05, min_spread=0.0)
    t = bt.simulate(b, sig, hold=3, cost=cost, window=(0, len(b)))
    assert len(t) == 1
    tr = t.iloc[0]
    assert tr["entry_px"] == b["open"].iloc[3]        # décision en clôture de 2 -> ouverture de 3
    assert tr["exit_px"] == b["open"].iloc[6]         # 3 + hold
    assert tr["gross_pnl"] == pytest.approx(3.0)
    assert tr["cost"] == pytest.approx(0.2 + 0.10 + 0.07)   # spread + 2*slippage + commission
    assert tr["net_pnl"] == pytest.approx(3.0 - 0.37)


def test_short_trade_sign():
    b = tiny_bars(np.arange(130.0, 100.0, -1.0))
    sig = pd.Series(0, index=b.index)
    sig.iloc[0] = -1
    t = bt.simulate(b, sig, hold=2, cost=bt.CostModel(min_spread=0.0), window=(0, len(b)))
    assert t.iloc[0]["gross_pnl"] == pytest.approx(2.0)


def test_no_trade_across_gap():
    b = tiny_bars(np.arange(100.0, 130.0), gap_after=5)
    sig = pd.Series(0, index=b.index)
    sig.iloc[3] = 1           # détention 3 -> 7 : traverse le trou de 2 h -> refusé
    sig.iloc[10] = 1          # après le trou : accepté
    t = bt.simulate(b, sig, hold=4, cost=bt.CostModel(), window=(0, len(b)))
    assert list(t["bar"]) == [10]


def test_one_position_at_a_time():
    b = tiny_bars(np.arange(100.0, 140.0))
    sig = pd.Series(1, index=b.index)
    t = bt.simulate(b, sig, hold=5, cost=bt.CostModel(), window=(0, len(b)))
    assert (np.diff(t["bar"]) >= 5).all()
    assert (t["entry_time"].iloc[1:].to_numpy() >= t["exit_time"].iloc[:-1].to_numpy()).all()


def test_window_contains_whole_trade():
    b = tiny_bars(np.arange(100.0, 140.0))
    sig = pd.Series(1, index=b.index)
    t = bt.simulate(b, sig, hold=5, cost=bt.CostModel(), window=(10, 25))
    assert t["bar"].min() >= 10
    assert (t["bar"] + 1 + 5).max() < 25


# ----------------------------------------------------------------------------- protocole
def test_splits_chronological_with_embargo():
    s = ev.make_splits(100_000, 0.25, 4, 36)
    assert s.test[0] == s.dev[1] + 36
    prev_val_end = None
    for f in s.folds:
        assert f.train[0] == 0 and f.train[1] + 36 == f.val[0]
        assert f.val[0] < f.val[1] <= s.dev[1]
        if prev_val_end is not None:
            assert f.val[0] == prev_val_end
        prev_val_end = f.val[1]


def test_evaluator_lock_intact():
    ok, msg = ev.verify_lock(ROOT)
    assert ok, msg


def test_holm_and_dsr():
    np.testing.assert_allclose(ev.holm_adjust([0.01, 0.04, 0.03]), [0.03, 0.06, 0.06])
    rng = np.random.default_rng(0)
    r = rng.normal(0.05, 1, 2000)
    one = ev.deflated_sharpe(r, 1, 0.0)["dsr"]
    many = ev.deflated_sharpe(r, 100, 0.002)["dsr"]
    assert many < one          # plus on teste, plus la barre est haute


def test_bootstrap_ci_covers_mean():
    rng = np.random.default_rng(1)
    x = rng.normal(0, 1, 500)
    b = ev.stationary_bootstrap_means(x, 1000, 5, 0)
    assert np.quantile(b, 0.025) < x.mean() < np.quantile(b, 0.975)


# ----------------------------------------------------------------------------- données
@pytest.mark.parametrize("order", ["OHLC", "OCLH"])
def test_dukascopy_decoder_detects_field_order(order):
    o, h, l, c = 2045123, 2046000, 2044000, 2045500
    p = (o, h, l, c) if order == "OHLC" else (o, c, l, h)
    rec = np.array([(60, *p, 12.5), (120, *p, 3.0)], dtype=[("t", ">u4"), ("p1", ">u4"), ("p2", ">u4"),
                                                             ("p3", ">u4"), ("p4", ">u4"), ("v", ">f4")])
    blob = lzma.compress(rec.tobytes(), format=lzma.FORMAT_ALONE)
    df = decode_bi5_candles(blob, pd.Timestamp("2024-01-03"), 1000.0)
    assert df["high"].iloc[0] == pytest.approx(2046.0)
    assert df["close"].iloc[0] == pytest.approx(2045.5)
    assert str(df.index[0]) == "2024-01-03 00:01:00+00:00"


def test_mt5_reader_converts_to_utc_and_points(tmp_path):
    f = tmp_path / "x.csv"
    f.write_text("<DATE>\t<TIME>\t<OPEN>\t<HIGH>\t<LOW>\t<CLOSE>\t<TICKVOL>\t<VOL>\t<SPREAD>\n"
                 "2024.01.02\t03:00:00\t2063.10\t2064.00\t2062.50\t2063.80\t120\t0\t25\n")
    df = read_price_file(f, "auto", utc_offset_hours=2, point_size=0.01)
    assert str(df.index[0]) == "2024-01-02 01:00:00+00:00"
    assert df["spread"].iloc[0] == pytest.approx(0.25)
