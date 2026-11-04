"""
data_loader.py — chargement, contrôle qualité et mode démonstration.

Ce que fait ce module
---------------------
1. Lit un fichier de prix historiques (CSV standard, export MetaTrader 5, HistData)
   ou télécharge les bougies M1 gratuites de Dukascopy (à lancer sur TA machine).
2. Convertit tout en UTC, agrège M1 -> M5, supprime les barres vides.
3. Produit un rapport qualité (trous, doublons, OHLC incohérents, valeurs aberrantes,
   spread) : on ne fait pas de recherche sur des données qu'on n'a pas contrôlées.
4. Si aucune donnée réelle n'est disponible, génère un jeu SYNTHÉTIQUE clairement
   étiqueté DEMO. Ce jeu est un "monde nul" : il ne contient aucun avantage
   exploitable. Il sert de CONTRÔLE NÉGATIF : si le labo y "découvre" une stratégie
   gagnante, c'est que le protocole est défaillant.

Convention temporelle (importante pour éviter les fuites d'information)
-----------------------------------------------------------------------
L'horodatage d'une barre = son heure d'OUVERTURE (convention MT5 et Dukascopy).
La barre 10:00 couvre [10:00, 10:05[ et sa clôture n'est connue qu'à 10:05.

Usage en ligne de commande
--------------------------
    python data_loader.py check                      # contrôle les données de la config
    python data_loader.py fetch --start 2023-01-01 --end 2026-10-31
                                                     # télécharge Dukascopy (sur ta machine)
"""
from __future__ import annotations

import argparse
import hashlib
import io
import lzma
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent
OHLC = ["open", "high", "low", "close"]


@dataclass
class MarketData:
    bars: pd.DataFrame            # index DatetimeIndex UTC ; open high low close volume spread
    symbol: str
    timeframe: str
    is_demo: bool
    source: str
    data_hash: str
    quality: dict = field(default_factory=dict)

    @property
    def label(self) -> str:
        return "DEMO" if self.is_demo else "REAL"


# =============================================================================
# 1. Lecture de fichiers
# =============================================================================
def detect_format(path: Path) -> str:
    with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
        first = f.readline().strip()
    if first.upper().startswith("<DATE>"):
        return "mt5"
    if ";" in first and first.split(";")[0].replace(" ", "").isdigit():
        return "histdata"
    return "standard"


def read_price_file(path: Path, fmt: str = "auto", utc_offset_hours: float = 0.0,
                    point_size: float = 0.01) -> pd.DataFrame:
    """Retourne un DataFrame indexé en UTC avec open, high, low, close, volume, spread.

    spread est exprimé en unités de prix (USD/oz pour XAUUSD) ; NaN s'il est inconnu.
    """
    path = Path(path)
    if fmt == "auto":
        fmt = detect_format(path)

    if fmt == "mt5":
        # Export MT5 "Barres" : <DATE> <TIME> <OPEN> <HIGH> <LOW> <CLOSE> <TICKVOL> <VOL> <SPREAD>
        raw = pd.read_csv(path, sep="\t")
        raw.columns = [c.strip("<>").lower() for c in raw.columns]
        ts = pd.to_datetime(raw["date"].astype(str) + " " + raw["time"].astype(str),
                            format="%Y.%m.%d %H:%M:%S", errors="coerce")
        if ts.isna().mean() > 0.5:   # certains exports n'ont pas les secondes
            ts = pd.to_datetime(raw["date"].astype(str) + " " + raw["time"].astype(str),
                                format="%Y.%m.%d %H:%M", errors="coerce")
        df = pd.DataFrame({
            "open": raw["open"], "high": raw["high"], "low": raw["low"], "close": raw["close"],
            "volume": raw.get("tickvol", raw.get("vol", 0)),
            "spread": raw["spread"] * point_size if "spread" in raw else np.nan,
        })
        df.index = ts
    elif fmt == "histdata":
        # HistData ASCII M1 : 20240102 180000;open;high;low;close;volume  (heure EST fixe, UTC-5)
        raw = pd.read_csv(path, sep=";", header=None,
                          names=["ts", "open", "high", "low", "close", "volume"])
        df = raw[OHLC + ["volume"]].copy()
        df["spread"] = np.nan
        df.index = pd.to_datetime(raw["ts"], format="%Y%m%d %H%M%S", errors="coerce")
    elif fmt == "standard":
        raw = pd.read_csv(path)
        raw.columns = [c.strip().lower() for c in raw.columns]
        tcol = next((c for c in ("time", "datetime", "timestamp", "date") if c in raw.columns), None)
        if tcol is None:
            raise ValueError(f"{path}: aucune colonne temps (time/datetime/timestamp/date)")
        missing = [c for c in OHLC if c not in raw.columns]
        if missing:
            raise ValueError(f"{path}: colonnes manquantes {missing}")
        df = raw[OHLC].copy()
        df["volume"] = raw["volume"] if "volume" in raw.columns else 0
        df["spread"] = raw["spread"] if "spread" in raw.columns else np.nan
        df.index = pd.to_datetime(raw[tcol], utc=True, errors="coerce").dt.tz_localize(None)
    else:
        raise ValueError(f"format inconnu : {fmt}")

    df = df[~df.index.isna()]
    # Heure source -> UTC. (Les heures serveur MT5 avec changement d'heure été/hiver
    # ne sont qu'approximées par un décalage fixe : limite documentée dans le README.)
    df.index = (df.index - pd.Timedelta(hours=utc_offset_hours)).tz_localize("UTC")
    df.index.name = "time"
    return df.astype({"open": float, "high": float, "low": float, "close": float,
                      "volume": float, "spread": float})


def infer_minutes(df: pd.DataFrame) -> int:
    d = pd.Series(df.index).diff().dropna().dt.total_seconds() / 60
    return int(round(d.mode().iloc[0])) if len(d) else 0


def resample_ohlc(df: pd.DataFrame, minutes: int) -> pd.DataFrame:
    """Agrège des barres fines en barres de `minutes` minutes (label = heure d'ouverture).

    spread : on garde le spread de la PREMIÈRE minute (spread à l'ouverture, c'est celui
    qu'on paie en entrant à l'ouverture de la barre) et la moyenne pour information.
    """
    rule = f"{minutes}min"
    g = df.resample(rule, label="left", closed="left")
    out = pd.DataFrame({
        "open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(),
        "close": g["close"].last(), "volume": g["volume"].sum(),
        "spread": g["spread"].first(), "spread_mean": g["spread"].mean(),
    })
    return out.dropna(subset=OHLC)


def clean_bars(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Nettoyage minimal et TRACÉ (chaque suppression est comptée)."""
    log = {"rows_in": int(len(df))}
    df = df.sort_index()
    dup = df.index.duplicated(keep="last")
    log["duplicates_removed"] = int(dup.sum())
    df = df[~dup]
    bad_px = (df[OHLC] <= 0).any(axis=1) | df[OHLC].isna().any(axis=1)
    log["nonpositive_or_nan_removed"] = int(bad_px.sum())
    df = df[~bad_px]
    # Barres "plates" sans aucune activité (Dukascopy remplit les heures fermées)
    flat = (df["high"] == df["low"]) & (df["volume"].fillna(0) <= 0)
    log["flat_zero_volume_removed"] = int(flat.sum())
    df = df[~flat]
    log["rows_out"] = int(len(df))
    return df, log


def quality_report(df: pd.DataFrame, bar_minutes: int) -> dict:
    """Contrôles qualité. Retourne un dict avec métriques + liste d'avertissements."""
    q: dict = {"n_bars": int(len(df)),
               "start": str(df.index[0]) if len(df) else None,
               "end": str(df.index[-1]) if len(df) else None}
    hi_bad = df["high"] < df[["open", "close"]].max(axis=1) - 1e-9
    lo_bad = df["low"] > df[["open", "close"]].min(axis=1) + 1e-9
    q["ohlc_inconsistent"] = int((hi_bad | lo_bad).sum())

    dt = pd.Series(df.index).diff().dt.total_seconds().div(60).iloc[1:]
    gaps = dt[dt > bar_minutes]
    q["gaps_total"] = int(len(gaps))
    q["gaps_over_1h"] = int((gaps > 60).sum())
    # > 2 h en semaine = anormal (la pause quotidienne de l'or dure ~1 h ; le week-end ~48 h)
    q["gaps_over_2h_weekday"] = int(((gaps > 120) & (gaps < 36 * 60)).sum())
    q["max_gap_hours"] = float(gaps.max() / 60) if len(gaps) else 0.0

    r = np.log(df["close"]).diff()
    mad = (r - r.median()).abs().rolling(2000, min_periods=200).median()
    q["extreme_returns_gt_15mad"] = int((r.abs() > 15 * 1.4826 * mad).sum())

    sp = df["spread"]
    q["spread_available"] = bool(sp.notna().mean() > 0.5)
    if q["spread_available"]:
        q["spread_median"] = float(sp.median())
        q["spread_p95"] = float(sp.quantile(0.95))
        q["spread_zero_frac"] = float((sp <= 0).mean())
    days = df.index.normalize().nunique()
    q["trading_days"] = int(days)
    q["bars_per_day"] = float(len(df) / max(days, 1))

    warn = []
    if q["ohlc_inconsistent"] > 0.001 * len(df):
        warn.append(f"{q['ohlc_inconsistent']} barres OHLC incohérentes (> 0.1 %)")
    if q["gaps_over_2h_weekday"] > 0.02 * days:
        warn.append(f"{q['gaps_over_2h_weekday']} trous > 2 h en semaine : données incomplètes ?")
    if q["extreme_returns_gt_15mad"] > 0:
        warn.append(f"{q['extreme_returns_gt_15mad']} rendements extrêmes (> 15 MAD) : vérifier "
                    "(news réelles ou erreurs de données)")
    if not q["spread_available"]:
        warn.append("pas de spread dans les données : spread fixe de la config utilisé")
    elif q.get("spread_zero_frac", 0) > 0.05:
        warn.append("> 5 % de spreads nuls : spread minimum de la config appliqué")
    q["warnings"] = warn
    return q


def frame_hash(df: pd.DataFrame) -> str:
    """Empreinte des données : deux runs sur les mêmes données ont le même hash."""
    h = hashlib.sha256()
    h.update(np.asarray(df.index.as_unit("ns").asi8).tobytes())
    h.update(np.ascontiguousarray(df[OHLC].to_numpy(dtype=np.float64)).tobytes())
    return h.hexdigest()[:16]


# =============================================================================
# 2. Jeu de démonstration SYNTHÉTIQUE (étiqueté DEMO)
# =============================================================================
# Profil de volatilité intrajournalière (heures UTC), inspiré de la saisonnalité
# documentée par Andersen & Bollerslev (1997) : Asie calme, pics à l'ouverture de
# Londres et à l'ouverture de New York / publications macro US.
_HOURLY_VOL = np.array([0.55, 0.55, 0.6, 0.6, 0.6, 0.65, 0.75, 1.2, 1.1, 1.0, 1.0, 0.95,
                        1.1, 1.6, 1.6, 1.3, 1.0, 0.9, 0.85, 0.8, 0.7, 0.5, 0.45, 0.5])


def make_demo_data(start: str, end: str, start_price: float = 2000.0,
                   annual_vol: float = 0.16, planted_edge: float = 0.0,
                   seed: int = 42) -> pd.DataFrame:
    """Génère des barres M1 SYNTHÉTIQUES ressemblant statistiquement à de l'or au comptant.

    Propriétés reproduites (faits stylisés, Cont 2001) : queues épaisses (Student-t),
    volatilité en grappes (volatilité stochastique à 2 échelles), saisonnalité
    intrajournalière, pause quotidienne, week-ends, spread variable.
    Propriété VOLONTAIREMENT absente : aucune prévisibilité des rendements (dérive nulle,
    pas d'autocorrélation) si planted_edge == 0.

    planted_edge > 0 crée un CONTRÔLE POSITIF : momentum artificiel en régime de forte
    volatilité. Sert uniquement à vérifier que le labo sait détecter un effet réel.
    """
    from scipy.signal import lfilter

    rng = np.random.default_rng(seed)
    idx = pd.date_range(start, end, freq="1min", tz="UTC")
    wd, hr = idx.day_of_week, idx.hour
    # Ouvert : dim >= 23h, lun-jeu sauf 21h-22h (pause), ven < 21h
    is_open = (((wd >= 0) & (wd <= 3) & (hr != 21)) | ((wd == 4) & (hr < 21)) | ((wd == 6) & (hr >= 23)))
    idx = idx[is_open]
    n = len(idx)

    mins_per_year = 252 * 23 * 60
    base = annual_vol / np.sqrt(mins_per_year)
    # Volatilité stochastique : log-vol = composante rapide (demi-vie ~1 jour) + lente (~20 jours)
    phi_f, phi_s = 0.5 ** (1 / 1380), 0.5 ** (1 / (20 * 1380))
    f = lfilter([1.0], [1.0, -phi_f], rng.normal(0, 0.35 * np.sqrt(1 - phi_f ** 2), n))
    s = lfilter([1.0], [1.0, -phi_s], rng.normal(0, 0.30 * np.sqrt(1 - phi_s ** 2), n))
    logv = f + s
    season = _HOURLY_VOL[idx.hour]
    season = season / season.mean()
    sigma = base * season * np.exp(logv - 0.5 * logv.var())

    df_t = 4.0
    eps = rng.standard_t(df_t, n) / np.sqrt(df_t / (df_t - 2))    # variance 1, queues épaisses
    r = sigma * eps
    if planted_edge > 0:
        # z_{t-1} = moyenne exponentielle (span 60 min) des chocs PASSÉS -> momentum causal
        a = 2 / 61
        z = lfilter([a], [1.0, -(1 - a)], eps)
        z = np.concatenate([[0.0], z[:-1]])
        high_regime = s > np.median(s)
        r = r + planted_edge * sigma * z * high_regime
    # Saut d'ouverture après pause / week-end
    gap = np.concatenate([[False], np.diff(idx.as_unit("ns").asi8) > 30 * 60 * 10**9])
    r[gap] += rng.normal(0, 8 * base, gap.sum())

    close = start_price * np.exp(np.cumsum(r))
    open_ = np.concatenate([[start_price], close[:-1]])
    wick = sigma * close
    high = np.maximum(open_, close) + np.abs(rng.normal(0, 0.6, n)) * wick
    low = np.minimum(open_, close) - np.abs(rng.normal(0, 0.6, n)) * wick
    spread = 0.18 * season ** -0.5 * (sigma / sigma.mean()) ** 0.3
    spread = np.where(np.isin(idx.hour, [22, 23]) & (idx.minute < 30), spread * 3, spread)
    spread = np.round(np.clip(spread, 0.08, 2.0), 2)
    volume = rng.poisson(40 * season * sigma / sigma.mean()) + 1

    df = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close,
                       "volume": volume.astype(float), "spread": spread}, index=idx)
    df.index.name = "time"
    return df.round({"open": 3, "high": 3, "low": 3, "close": 3})


# =============================================================================
# 3. Point d'entrée principal
# =============================================================================
def load_config(path: Path | str = ROOT / "research_config.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_market_data(cfg: dict, root: Path = ROOT, force_mode: str | None = None) -> MarketData:
    dcfg = cfg["data"]
    target_min = int(dcfg["timeframe"].lstrip("M"))
    mode = force_mode or dcfg.get("mode", "auto")
    path = (root / dcfg["path"]) if dcfg.get("path") else None
    have_real = path is not None and path.exists()

    if mode == "real" and not have_real:
        raise FileNotFoundError(f"mode=real mais {path} est introuvable. Voir README (section Données).")

    if mode in ("real", "auto") and have_real:
        raw = read_price_file(path, dcfg.get("format", "auto"),
                              float(dcfg.get("source_utc_offset_hours", 0)),
                              float(dcfg.get("point_size", 0.01)))
        is_demo, source = False, f"file:{path.name}"
    else:
        dm = dcfg["demo"]
        raw = make_demo_data(dm["start"], dm["end"], float(dm["start_price"]),
                             float(dm["annual_vol"]), float(dm.get("planted_edge", 0.0)),
                             int(cfg["project"]["seed"]))
        is_demo = True
        source = f"SYNTHETIC_DEMO(seed={cfg['project']['seed']},planted_edge={dm.get('planted_edge', 0.0)})"

    raw, clean_log = clean_bars(raw)
    src_min = infer_minutes(raw)
    if src_min > target_min:
        raise ValueError(f"données en {src_min} min, impossible de construire du M{target_min}")
    bars = resample_ohlc(raw, target_min) if src_min < target_min else raw.assign(spread_mean=raw["spread"])
    bars, _ = clean_bars(bars)

    q = quality_report(bars, target_min)
    q["source_minutes"] = src_min
    q["cleaning"] = clean_log
    if len(bars) < int(dcfg.get("min_bars", 0)):
        raise ValueError(f"seulement {len(bars)} barres : échantillon insuffisant (min_bars)")
    return MarketData(bars=bars, symbol=dcfg["symbol"], timeframe=dcfg["timeframe"],
                      is_demo=is_demo, source=source, data_hash=frame_hash(bars), quality=q)


# =============================================================================
# 4. Téléchargement Dukascopy (données gratuites) — à exécuter sur TA machine
# =============================================================================
# Bougies M1 journalières : .../datafeed/{SYM}/{AAAA}/{MM-1}/{JJ}/{BID|ASK}_candles_min_1.bi5
# Fichier compressé LZMA ; enregistrements big-endian de 24 octets : 5 entiers + 1 float
# (secondes depuis minuit UTC, 4 prix entiers, volume). ATTENTION : les mois sont indexés
# à partir de 0 (janvier = 00). L'ordre des 4 prix diffère selon les sources
# communautaires (OHLC ou OCLH) : on le DÉTECTE en vérifiant la cohérence high/low.
PRICE_DIVISOR = {"XAUUSD": 1000.0, "XAGUSD": 1000.0, "GBPUSD": 100000.0, "EURUSD": 100000.0,
                 "USDJPY": 1000.0}
_BI5 = np.dtype([("t", ">u4"), ("p1", ">u4"), ("p2", ">u4"), ("p3", ">u4"), ("p4", ">u4"), ("v", ">f4")])


def decode_bi5_candles(blob: bytes, day: pd.Timestamp, divisor: float) -> pd.DataFrame:
    raw = lzma.decompress(blob)
    n = len(raw) // _BI5.itemsize
    if n == 0:
        return pd.DataFrame(columns=OHLC + ["volume"])
    a = np.frombuffer(raw[: n * _BI5.itemsize], dtype=_BI5)
    o = a["p1"] / divisor
    p2, p3, p4 = a["p2"] / divisor, a["p3"] / divisor, a["p4"] / divisor
    active = a["v"] > 0
    # Hypothèse A : O, H, L, C   |   Hypothèse B : O, C, L, H
    ok_a = np.all((p2 >= np.maximum(o, p4) - 1e-9) & (p3 <= np.minimum(o, p4) + 1e-9) | ~active)
    ok_b = np.all((p4 >= np.maximum(o, p2) - 1e-9) & (p3 <= np.minimum(o, p2) + 1e-9) | ~active)
    if ok_a and not ok_b:
        h, l, c = p2, p3, p4
    elif ok_b and not ok_a:
        h, l, c = p4, p3, p2
    elif ok_a and ok_b:          # indécidable (barres toutes plates) : peu importe
        h, l, c = p2, p3, p4
    else:
        raise ValueError(f"{day.date()}: ordre des champs bi5 non reconnu (données corrompues ?)")
    idx = pd.DatetimeIndex(day.tz_localize("UTC") + pd.to_timedelta(a["t"], unit="s"), name="time")
    return pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": a["v"].astype(float)}, index=idx)


def _http_get(url: str, retries: int = 4) -> bytes | None:
    for k in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "quantlab-research/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            pass
        time.sleep(2 ** (k + 1))
    raise ConnectionError(f"échec du téléchargement : {url}")


def fetch_dukascopy(symbol: str, start: str, end: str, out_path: Path, pause_s: float = 0.2) -> Path:
    """Télécharge les bougies M1 BID et ASK, en déduit prix médian et spread, écrit un CSV.

    Reprise possible : un cache mensuel est conservé dans data/dukascopy/{symbol}/.
    Respecte le serveur (requêtes séquentielles + pause). Données gratuites ; vérifie
    les conditions d'utilisation de Dukascopy avant tout usage autre que personnel.
    """
    divisor = PRICE_DIVISOR.get(symbol)
    if divisor is None:
        raise ValueError(f"diviseur de prix inconnu pour {symbol} : ajoute-le à PRICE_DIVISOR")
    cache = out_path.parent / "dukascopy" / symbol
    cache.mkdir(parents=True, exist_ok=True)
    months = pd.period_range(start, end, freq="M")
    for m in months:
        mfile = cache / f"{m}.csv"
        if mfile.exists():
            continue
        parts = []
        for day in pd.date_range(max(m.start_time, pd.Timestamp(start)),
                                 min(m.end_time, pd.Timestamp(end)), freq="D"):
            if day.day_of_week == 5:          # samedi : marché fermé
                continue
            sides = {}
            for side in ("BID", "ASK"):
                url = (f"https://datafeed.dukascopy.com/datafeed/{symbol}/{day.year}/"
                       f"{day.month - 1:02d}/{day.day:02d}/{side}_candles_min_1.bi5")
                blob = _http_get(url)
                time.sleep(pause_s)
                if blob:
                    sides[side] = decode_bi5_candles(blob, day.normalize(), divisor)
            if len(sides) == 2 and len(sides["BID"]):
                b, a = sides["BID"], sides["ASK"].reindex(sides["BID"].index)
                mid = pd.DataFrame({c: (b[c] + a[c]) / 2 for c in OHLC})
                mid["high"] = np.maximum(mid["high"], mid[["open", "close"]].max(axis=1))
                mid["low"] = np.minimum(mid["low"], mid[["open", "close"]].min(axis=1))
                mid["volume"] = b["volume"]
                mid["spread"] = (a["open"] - b["open"]).round(5)   # spread à l'ouverture de la minute
                parts.append(mid[b["volume"] > 0])
        dfm = pd.concat(parts) if parts else pd.DataFrame(columns=OHLC + ["volume", "spread"])
        dfm.to_csv(mfile, index_label="time")
        print(f"  {symbol} {m}: {len(dfm)} barres M1", flush=True)
    allm = [pd.read_csv(cache / f"{m}.csv") for m in months if (cache / f"{m}.csv").exists()]
    full = pd.concat(allm, ignore_index=True).drop_duplicates("time").sort_values("time")
    full.to_csv(out_path, index=False)
    print(f"écrit : {out_path} ({len(full)} barres M1)")
    return out_path


def _main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check", help="charge les données de la config et affiche le rapport qualité")
    f = sub.add_parser("fetch", help="télécharge les bougies M1 Dukascopy (gratuites)")
    f.add_argument("--symbol", default=None)
    f.add_argument("--start", required=True)
    f.add_argument("--end", required=True)
    args = ap.parse_args(argv)
    cfg = load_config()
    if args.cmd == "fetch":
        sym = args.symbol or cfg["data"]["symbol"]
        out = ROOT / cfg["data"]["path"] if sym == cfg["data"]["symbol"] else ROOT / f"data/{sym}_M1.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        fetch_dukascopy(sym, args.start, args.end, out)
        return 0
    md = load_market_data(cfg)
    print(f"[{md.label}] {md.symbol} {md.timeframe} source={md.source} hash={md.data_hash}")
    for k, v in md.quality.items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
