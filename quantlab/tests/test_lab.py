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


def test_http_get_stops_immediately_on_429(monkeypatch):
    """Un refus explicite du fournisseur (429) doit arrêter le téléchargement, pas déclencher
    une rafale de nouvelles tentatives."""
    import io
    import urllib.error
    import data_loader as dl
    calls = []

    def fake_urlopen(req, timeout=30):
        calls.append(req.full_url)
        raise urllib.error.HTTPError(req.full_url, 429, "Too Many Requests", {}, io.BytesIO(b'{"error": "x"}'))
    monkeypatch.setattr(dl.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(dl.time, "sleep", lambda s: pytest.fail("ne doit pas attendre puis réessayer"))
    with pytest.raises(dl.DataSourceRefused):
        dl._http_get("https://example.invalid/x.bi5")
    assert len(calls) == 1


# ----------------------------------------------------------------------------- traçabilité par jeu
def _small_cfg(seed):
    """Petit monde DÉMO (3 mois) pour tester le runner en quelques secondes."""
    import copy
    from data_loader import load_config
    cfg = copy.deepcopy(load_config(ROOT / "research_config.yaml"))
    cfg["project"]["seed"] = seed
    cfg["data"]["min_bars"] = 1000
    cfg["data"]["demo"].update(start="2024-01-01", end="2024-03-31", planted_edge=0.0)
    cfg["features"] = dict(FEAT_CFG)
    cfg["evaluation"].update(n_bootstrap=200, n_null_sims=100)
    return cfg


def test_artifacts_and_test_access_are_separated_by_dataset(tmp_path):
    """Deux jeux de données n'écrivent jamais dans le même dossier : un run sur données réelles
    ne peut ni écraser les artefacts démo, ni relire la spécification démo d'un même identifiant
    (E04...), et le test final reste à usage unique PAR jeu."""
    import contextlib
    import io
    import json
    import experiment_runner as er
    runs, res = tmp_path / "runs", tmp_path / "results.csv"
    labs = []
    for seed in (1, 2):
        cfg = _small_cfg(seed)
        with contextlib.redirect_stdout(io.StringIO()):
            lab = er.Lab(cfg, force_mode="demo", results_path=res, write_docs=False, runs_root=runs)
            lab.run_experiment(dict(cfg["experiments"][0]))
        labs.append(lab)
    a, b = labs
    assert a.md.data_hash != b.md.data_hash
    for lab in labs:
        d = runs / lab.md.data_hash / "E01"
        assert json.loads((d / "summary.json").read_text())["data_hash"] == lab.md.data_hash
        assert (d / "trades.csv").exists()
    assert not (runs / "E01").exists()
    # une expérience proposée sur un jeu n'est retrouvée que sur ce jeu
    spec = {"id": "E09", "strategy": "breakout", "params": {"lookback": 20, "hold": 12, "mode": "fade"}}
    (a.run_dir / "E09").mkdir()
    (a.run_dir / "E09" / "summary.json").write_text(json.dumps({"experiment": spec}))
    assert a._find_spec("E09") == spec
    with pytest.raises(KeyError):
        b._find_spec("E09")
    # test final : trace dans le dossier du jeu, refus d'une 2e utilisation, l'autre jeu intact
    with contextlib.redirect_stdout(io.StringIO()):
        a.final_test("E01", force=True)
    acc = json.loads((a.run_dir / "test_access.json").read_text())
    assert acc["data_hash"] == a.md.data_hash and acc["test_start"] < acc["test_end"]
    assert not (b.run_dir / "test_access.json").exists()
    with pytest.raises(SystemExit):
        a.final_test("E01", force=True)


def test_final_test_refuses_real_period_already_seen(tmp_path):
    """Retélécharger les mêmes prix change le hash : la période de test d'un test final RÉEL
    déjà utilisé doit quand même être refusée. Les traces DÉMO (dates fictives) sont ignorées."""
    import json
    import experiment_runner as er

    def trace(h, **kw):
        (tmp_path / h).mkdir()
        (tmp_path / h / "test_access.json").write_text(json.dumps({"exp_id": "E02", "data_hash": h, **kw}))
    trace("aaaa", data_mode="REAL", symbol="XAUUSD",
          test_start="2025-12-01 00:00:00+00:00", test_end="2026-10-30 20:55:00+00:00")
    trace("bbbb", forced=False)                                   # ancien format, monde DÉMO
    trace("cccc", data_mode="DEMO", symbol="XAUUSD", test_start="2026-01-01", test_end="2026-06-01")
    clash = er.test_window_conflicts(tmp_path, "XAUUSD", "2026-01-05 00:00:00+00:00",
                                     "2026-11-27 20:55:00+00:00", "dddd")
    assert [c["data_hash"] for c in clash] == ["aaaa"]
    assert er.test_window_conflicts(tmp_path, "XAUUSD", "2023-01-01", "2024-01-01", "dddd") == []
    assert er.test_window_conflicts(tmp_path, "GBPUSD", "2026-01-05", "2026-11-27", "dddd") == []
    assert er.test_window_conflicts(tmp_path, "XAUUSD", "2026-01-05", "2026-11-27", "aaaa") == []
    trace("eeee", data_mode="REAL", symbol="XAUUSD")              # période inconnue -> prudence
    assert "eeee" in [c["data_hash"] for c in
                      er.test_window_conflicts(tmp_path, "XAUUSD", "2023-01-01", "2024-01-01", "dddd")]


def _rows(h, mode, net):
    return {"exp_id": "E01", "split": "DEV", "data_mode": mode, "data_hash": h, "name": "baseline_breakout",
            "n_trades": 500, "net_exp_bps": net, "ci_low_bps": net - 1, "ci_high_bps": net + 1, "decision": "REJECT"}


def test_figures_and_docs_keep_demo_and_real_apart(tmp_path):
    """Après un run réel, les chiffres réels ne doivent jamais apparaître sous une étiquette DÉMO
    (et inversement), et le tableau démo ne doit pas disparaître des documents."""
    import experiment_runner as er
    import figures
    df = pd.DataFrame([_rows("demohash", "DEMO", -1.8), _rows("realhash", "REAL", 0.4)])
    assert figures.data_label("DEMO_POSITIVE_CONTROL") == "DÉMO" and figures.data_label("REAL") == "RÉEL"
    out = figures.dataset_figures(df, tmp_path, mode="real")
    assert list(out) == ["realhash"] and (tmp_path / "realhash" / "fig_ci.png").exists()
    assert out["realhash"][0][1].startswith("RÉEL") and not (tmp_path / "demohash").exists()
    out = figures.dataset_figures(df, tmp_path, data_hash="demohash")
    assert list(out) == ["demohash"] and out["demohash"][0][1].startswith("DÉMO")
    # synthèse des contrôles : le « monde nul » ne lit que les lignes DÉMO
    pos = pd.DataFrame([_rows("poshash", "DEMO_POSITIVE_CONTROL", 1.5)])
    title = figures.demo_controls_figure(df, pos, tmp_path / "ctl.png")
    assert title.startswith("DÉMO")
    # documents : un tableau par jeu, chacun avec sa propre étiquette
    md = er.results_by_dataset(df)
    demo_part, real_part = md.split("`realhash`")
    assert "`demohash` — DÉMO" in demo_part and er.DEMO_WARNING in demo_part and "-1.800" in demo_part
    assert "— RÉEL" in real_part and er.REAL_NOTE in real_part and er.DEMO_WARNING not in real_part
    assert "0.400" in real_part and "-1.800" not in real_part


def test_fetch_resumes_day_by_day_without_refetching(tmp_path, monkeypatch):
    """Une panne en plein mois ne doit perdre que le fichier en cours : la relance reprend au jour
    suivant sans retélécharger, et un jour sans cotation (404) n'est demandé qu'une fois."""
    import data_loader as dl
    rec = np.array([(60, 2045123, 2046000, 2044000, 2045500, 2.0), (120, 2045500, 2046000, 2045000, 2045800, 1.0)],
                   dtype=[("t", ">u4"), ("p1", ">u4"), ("p2", ">u4"), ("p3", ">u4"), ("p4", ">u4"), ("v", ">f4")])
    blob = lzma.compress(rec.tobytes(), format=lzma.FORMAT_ALONE)
    calls, fail_at = [], {5}

    def fake_get(url, retries=6):
        calls.append(url)
        if len(calls) in fail_at:
            raise ConnectionError("panne simulée")
        return None if "/2024/00/01/" in url else blob          # 1er janvier : pas de cotation
    monkeypatch.setattr(dl, "_http_get", fake_get)
    out = tmp_path / "XAUUSD_M1.csv"
    with pytest.raises(ConnectionError):
        dl.fetch_dukascopy("XAUUSD", "2024-01-01", "2024-01-03", out, pause_s=0)
    assert len(calls) == 5                     # 01/01 BID+ASK (404), 02/01 BID+ASK, panne sur 03/01 BID
    fail_at.clear()
    dl.fetch_dukascopy("XAUUSD", "2024-01-01", "2024-01-03", out, pause_s=0)
    assert [u.split("/datafeed/XAUUSD/")[1] for u in calls[5:]] == [
        "2024/00/03/BID_candles_min_1.bi5", "2024/00/03/ASK_candles_min_1.bi5"]
    df = pd.read_csv(out)
    assert list(df["time"]) == ["2024-01-02 00:01:00+00:00", "2024-01-02 00:02:00+00:00",
                                "2024-01-03 00:01:00+00:00", "2024-01-03 00:02:00+00:00"]
    n = len(calls)
    dl.fetch_dukascopy("XAUUSD", "2024-01-01", "2024-01-03", out, pause_s=0)
    assert len(calls) == n                     # tout est en cache : aucune requête


def test_http_get_reports_cause_after_retries(monkeypatch):
    """Après des pannes réseau répétées, l'erreur finale doit dire POURQUOI (pas seulement « échec »)."""
    import urllib.error
    import data_loader as dl
    waits = []

    def fake_urlopen(req, timeout=30):
        raise urllib.error.URLError(TimeoutError("timed out"))
    monkeypatch.setattr(dl.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(dl.time, "sleep", waits.append)
    with pytest.raises(ConnectionError, match="URLError: timed out"):
        dl._http_get("https://example.invalid/x.bi5")
    assert waits == [30, 60, 120, 240, 480]
