"""Een simulatierun uitvoeren en de resultaten voor de webapp klaarzetten."""
import json

import numpy as np
import pandas as pd
import yaml

from botu_sim import worstcase
from botu_sim.data import laad_invoer
from botu_sim.flexibiliteit import envelop
from botu_sim.kpi import bereken
from botu_sim.simulatie import simuleer
from botu_sim.strategieen import maak_regelaar

UUR_KOLOMMEN = ["t_lokaal", "el", "el_ht", "el_lt", "q_ht", "q_lt", "htwp_dir", "q_htwp", "ltwp", "laad", "buf_ht", "buf_lt",
                "cond_lt", "soc", "e_buffer", "verlies", "t_buiten", "t_aanvoer_ht", "t_aanvoer_lt", "congestievenster",
                "cop_ht_dir", "cop_lt", "duty_ht", "duty_lt", "tekort_ht", "tekort_lt"]


def typedagen(df):
    """Standaard deep-dive-dagen uit het NEN-jaar (lokale tijd)."""
    d = df.assign(datum=df["t_lokaal"].dt.date, maand=df["t_lokaal"].dt.month, wd=df["t_lokaal"].dt.weekday)
    dag = d.groupby("datum").agg(T=("t_buiten", "mean"), maand=("maand", "first"), wd=("wd", "first"))
    werk = dag[dag["wd"] < 5]
    uit = []
    for m, naam in ((1, "Koude werkdag januari"), (2, "Koude werkdag februari"), (12, "Koude werkdag december")):
        x = werk[werk["maand"] == m]
        dt = x["T"].idxmin()
        uit.append({"id": f"koud_{m}", "label": naam, "datum": str(dt), "toelichting": f"koudste werkdag, gem. {x.loc[dt, 'T']:.1f} °C"})
    v = d[d["congestievenster"]].assign(q=lambda x: x["q_ht"] + x["q_lt"]).groupby("datum")["q"].sum()
    if len(v):
        dt = v.idxmax()
        uit.append({"id": "kritiek", "label": "Kritieke congestiedag", "datum": str(dt), "toelichting": f"meeste warmte in het venster ({v.max() / 1000:.1f} MWh)"})
    for m, naam, sleutel in ((4, "Gemiddelde voorjaarsdag", "voorjaar"), (7, "Zomerdag", "zomer")):
        x = werk[werk["maand"] == m]
        dt = (x["T"] - x["T"].mean()).abs().idxmin()
        uit.append({"id": sleutel, "label": naam, "datum": str(dt), "toelichting": f"werkdag rond maandgemiddelde, {x.loc[dt, 'T']:.1f} °C"})
    return uit


def draai(cfg, map_):
    df = laad_invoer(cfg)
    res = simuleer(cfg, df, maak_regelaar(cfg["strategie"]["naam"]))
    k = bereken(res, cfg)
    wc_met = worstcase.overbrugging(cfg, df, True)
    k["worstcase_met_condensor"] = worstcase.samenvatting(wc_met)
    k["worstcase_zonder_condensor"] = worstcase.samenvatting(worstcase.overbrugging(cfg, df, False))

    # flexibiliteitsenvelop altijd op een referentie-basislijn met dezelfde systeeminstellingen
    if cfg["strategie"]["naam"] == "referentie":
        basis = res
    else:
        c2 = {**cfg, "strategie": {**cfg["strategie"], "naam": "referentie"}}
        basis = simuleer(c2, df, maak_regelaar("referentie"))
    env, _ = envelop(basis, cfg, reducties=tuple(range(10, 201, 10)))

    uur = res[UUR_KOLOMMEN].copy()
    uur["t_lokaal"] = uur["t_lokaal"].dt.strftime("%Y-%m-%dT%H:%M")
    map_.mkdir(parents=True, exist_ok=True)
    uur.to_csv(map_ / "uurdata.csv", index=False)
    (map_ / "kpi.json").write_text(json.dumps(k, ensure_ascii=False))
    (map_ / "flex.json").write_text(env.to_json(orient="records"))
    (map_ / "worstcase.json").write_text(json.dumps(wc_met.tolist()))
    (map_ / "typedagen.json").write_text(json.dumps(typedagen(res), ensure_ascii=False))
    (map_ / "config.yaml").write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False))
    return k


def _schoon(a):
    """NaN/inf → None (JSON), recursief voor lijsten."""
    if isinstance(a, list):
        return [_schoon(x) for x in a]
    if isinstance(a, float) and not np.isfinite(a):
        return None
    return a


def jaaroverzicht(map_):
    u = pd.read_csv(map_ / "uurdata.csv", parse_dates=["t_lokaal"])
    u["dag"] = u["t_lokaal"].dt.dayofyear
    u["uur"] = u["t_lokaal"].dt.hour
    heat = u.pivot_table(index="uur", columns="dag", values="el", aggfunc="mean")
    vens = u["congestievenster"].astype(bool)
    maand = u["t_lokaal"].dt.month
    mnd = pd.DataFrame({"piek": u["el"].groupby(maand).max(), "piek_venster": u["el"].where(vens).groupby(maand).max(),
                        "mwhe": u["el"].groupby(maand).sum() / 1000}).fillna(0)
    return {
        "heatmap": {"dagen": [int(x) for x in heat.columns], "uren": [int(x) for x in heat.index],
                    "z": _schoon(np.round(heat.values, 1).tolist())},
        "duur": np.round(np.sort(u["el"].values)[::-1], 1).tolist(),
        "duur_venster": np.round(np.sort(u.loc[vens, "el"].values)[::-1], 1).tolist(),
        "maand": {"maand": [int(m) for m in mnd.index], **{c: np.round(mnd[c].values, 1).tolist() for c in mnd}},
    }


def dagdata(map_, datum, dagen=1):
    u = pd.read_csv(map_ / "uurdata.csv", parse_dates=["t_lokaal"])
    a = pd.Timestamp(datum)
    s = u[(u["t_lokaal"] >= a) & (u["t_lokaal"] < a + pd.Timedelta(days=dagen))].copy()
    s["t_lokaal"] = s["t_lokaal"].dt.strftime("%Y-%m-%dT%H:%M")
    return {c: (_schoon(s[c].round(3).tolist()) if s[c].dtype.kind in "fi" else s[c].tolist()) for c in s.columns}
