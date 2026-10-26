import numpy as np
import pandas as pd

from .config import pad


def laad_invoer(cfg):
    """Alle uurreeksen op de tijdas timestamp_2001 (8.760 uur, UT)."""
    d = cfg["data"]
    w = pd.read_csv(pad(d["warmte_netten"]))
    k = pd.read_csv(pad(d["klimaat"]))
    c = pd.read_csv(pad(d["condensor"]))
    p = pd.read_csv(pad(d["prijzen"]))
    for df in (k, c, p):
        assert (df["timestamp_2001"].values == w["timestamp_2001"].values).all(), "tijdassen lopen niet gelijk"

    df = pd.DataFrame({
        "t": pd.to_datetime(w["timestamp_2001"]),
        "q_ht": w["ht_kwh"].values,
        "q_lt": w["lt_kwh"].values,
        "tbuis_ht": w["ht_tbuis_max_c"].values,
        "tbuis_lt": w["lt_tbuis_max_c"].values,
        "t_buiten": k["buitentemperatuur_c"].values,
        "zon": (k["zonnestraling_wh_m2"] if "zonnestraling_wh_m2" in k else k["globale_straling_w_m2"]).values,  # NEN of KNMI
        "q_cond": c["condensor_zlt_kwh"].values if cfg.get("condensor_zlt", True) else 0.0,
        "prijs_2024": p["prijs_2024_eur_mwh"].values / 1000,
        "prijs_2025": p["prijs_2025_eur_mwh"].values / 1000,
    })
    cg = cfg["congestie"]
    lokaal = df["t"] + pd.Timedelta(hours=cg["utc_offset_h"])
    df["t_lokaal"] = lokaal
    venster = lokaal.dt.month.isin(cg["maanden"]) & (lokaal.dt.hour >= cg["uren_lokaal"][0]) & (lokaal.dt.hour < cg["uren_lokaal"][1])
    if cg["alleen_werkdagen"]:
        venster &= lokaal.dt.weekday < 5
    df["congestievenster"] = venster.values
    df["t_aanvoer_ht"] = aanvoertemperatuur(cfg, df, "ht")
    df["t_aanvoer_lt"] = aanvoertemperatuur(cfg, df, "lt")
    return df


def aanvoertemperatuur(cfg, df, net):
    tc = cfg["temperatuur"]
    punten = np.array(tc["stooklijn"][net], dtype=float)
    stook = np.interp(df["t_buiten"].values, punten[:, 0], punten[:, 1])  # np.interp begrenst buiten het bereik
    if tc["modus"] == "stooklijn":
        return stook
    if tc["modus"] == "vraaggestuurd":
        eis = df[f"tbuis_{net}"].values + tc["voorregeling_k"]
        return np.minimum(eis, punten[:, 1].max())
    raise ValueError(f"onbekende temperatuurmodus {tc['modus']}")
