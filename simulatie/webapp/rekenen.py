"""Een simulatierun uitvoeren en de resultaten voor de webapp klaarzetten."""
import json

import numpy as np
import pandas as pd
import yaml

from botu_sim import worstcase
from botu_sim.data import laad_invoer
from botu_sim.flexibiliteit import envelop
from botu_sim.kpi import aansluiting, bereken
from botu_sim.simulatie import simuleer
from botu_sim.strategieen import maak_regelaar

UUR_KOLOMMEN = ["t_lokaal", "el", "el_ht", "el_lt", "q_ht", "q_lt", "htwp_dir", "q_htwp", "ltwp", "laad", "buf_ht", "buf_lt",
                "cond_lt", "soc", "e_buffer", "verlies", "t_buiten", "t_aanvoer_ht", "t_aanvoer_lt", "congestievenster",
                "cop_ht_dir", "cop_lt", "duty_ht", "duty_lt", "tekort_ht", "tekort_lt"]


def typedagen(df):
    """Standaard deep-dive-dagen uit het NEN-jaar (lokale tijd)."""
    d = df.assign(datum=df["t_lokaal"].dt.date, maand=df["t_lokaal"].dt.month, wd=df["t_lokaal"].dt.weekday, q=df["q_ht"] + df["q_lt"])
    dag = d.groupby("datum").agg(T=("t_buiten", "mean"), q=("q", "sum"), maand=("maand", "first"), wd=("wd", "first"))
    werk = dag[dag["wd"] < 5]
    uit = []

    # koudste reeks van 4 aaneengesloten werkdagen (ma–do of di–vr): opladen tussen de vensters is hier het knelpunt
    T4 = dag["T"].rolling(4).mean().shift(-3)
    start = [x for x in werk.index if all(dag["wd"].get(x + pd.Timedelta(days=i), 9) < 5 for i in range(4))]
    st = T4[start].idxmin()
    uit.append({"id": "koude_periode", "label": "Koude periode", "datum": str(st), "dagen": 4,
                "toelichting": f"4 werkdagen, gem. {T4[st]:.1f} °C"})

    # gemiddelde dagen: werkdag met de warmtevraag die het dichtst bij het seizoensgemiddelde ligt
    for maanden, naam, sleutel in (((12, 1, 2), "Gemiddelde winterdag", "winter"), ((11,), "Gemiddelde herfstdag", "herfst")):
        x = werk[werk["maand"].isin(maanden)]
        dt = (x["q"] - x["q"].mean()).abs().idxmin()
        uit.append({"id": sleutel, "label": naam, "datum": str(dt),
                    "toelichting": f"{x.loc[dt, 'q'] / 1000:.1f} MWh warmte, gem. {x.loc[dt, 'T']:.1f} °C"})

    for m, naam in ((2, "Koude werkdag februari"), (12, "Koude werkdag december")):
        x = werk[werk["maand"] == m]
        dt = x["T"].idxmin()
        uit.append({"id": f"koud_{m}", "label": naam, "datum": str(dt), "toelichting": f"koudste werkdag, gem. {x.loc[dt, 'T']:.1f} °C"})
    v = d[d["congestievenster"]].groupby("datum")["q"].sum()
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
                        "mwhe": u["el"].groupby(maand).sum() / 1000})   # piek_venster leeg (None) in maanden zonder venster
    return {
        "heatmap": {"dagen": [int(x) for x in heat.columns], "uren": [int(x) for x in heat.index],
                    "z": _schoon(np.round(heat.values, 1).tolist())},
        "duur": np.round(np.sort(u["el"].values)[::-1], 1).tolist(),
        "duur_venster": np.round(np.sort(u.loc[vens, "el"].values)[::-1], 1).tolist(),
        "maand": {"maand": [int(m) for m in mnd.index], **{c: _schoon(np.round(mnd[c].values, 1).tolist()) for c in mnd}},
    }


def dagdata(map_, datum, dagen=1):
    u = pd.read_csv(map_ / "uurdata.csv", parse_dates=["t_lokaal"])
    a = pd.Timestamp(datum)
    s = u[(u["t_lokaal"] >= a) & (u["t_lokaal"] < a + pd.Timedelta(days=dagen))].copy()
    backup = dag_backup(map_, u, s.index)
    s["t_lokaal"] = s["t_lokaal"].dt.strftime("%Y-%m-%dT%H:%M")
    uit = {c: (_schoon(s[c].round(3).tolist()) if s[c].dtype.kind in "fi" else s[c].tolist()) for c in s.columns}
    return uit | {"backup": backup}


def dag_backup(map_, u, idx, max_uur=400):
    """Back-up per dag, gestart aan het begin van het ontlaadvenster: alle WP's uit, hoeveel uur dekt het buffer
    (met condensorwarmte) de volledige vraag? Eén keer vanaf vol buffer, één keer vanaf de werkelijke vulling."""
    cfg = yaml.safe_load((map_ / "config.yaml").read_text())
    uur0 = cfg["congestie"]["uren_lokaal"][0]
    starts = [i for i in idx if u.at[i, "t_lokaal"].hour == uur0]
    if not starts:
        return []
    df = laad_invoer(cfg)
    e_max = float(u["e_buffer"].max() / u["soc"].max()) if u["soc"].max() > 0 else 0.0
    e_nu = [float(u.at[i - 1, "e_buffer"]) if i > 0 else cfg["buffer"]["soc_start"] * e_max for i in starts]  # vulling bij begin van het uur
    vol = worstcase.overbrugging(cfg, df, True, max_uur, starts)
    nu = worstcase.overbrugging(cfg, df, True, max_uur, starts, e_nu)
    return [{"datum": u.at[i, "t_lokaal"].strftime("%Y-%m-%d"), "start": f"{uur0:02d}:00", "vol_h": int(v), "nu_h": int(n),
             "soc_pct": round(e / e_max * 100) if e_max else None, "max_h": max_uur} for i, v, n, e in zip(starts, vol, nu, e_nu)]


def vensterdagen(u):
    """Per vensterdag: uren dat de WP's uit staan (< 0,5 kWe) en het hoogste vermogen."""
    vens = u["congestievenster"].astype(str).eq("True")
    v = u[vens].assign(datum=lambda x: x["t_lokaal"].dt.date, maand=lambda x: x["t_lokaal"].dt.month)
    return v.groupby("datum").agg(maand=("maand", "first"), uren=("el", "size"),
                                  uit=("el", lambda e: int((e < 0.5).sum())), piek=("el", "max"))


def nacht(u, datum, cap):
    """Bijladen in de nacht na een vensterdag (17:00–08:00): hoeveel HT-vermogen gaat naar de kassen en hoeveel naar het buffer."""
    a = pd.Timestamp(datum) + pd.Timedelta(hours=17)
    s = u[(u["t_lokaal"] >= a) & (u["t_lokaal"] < a + pd.Timedelta(hours=15))]
    return {"datum": datum, "t_buiten": round(float(s["t_buiten"].mean()), 1), "ht_vraag_kw": round(float(s["q_ht"].mean())),
            "ht_wp_kw": round(float(s["q_htwp"].mean())), "laden_mwh": round(float(s["laad"].sum()) / 1000, 2),
            "vrij_kw": round(float((cap - s["q_htwp"]).mean())), "vol_uren": int((s["q_htwp"] >= cap - 1).sum()),
            "soc_start": round(float(u.loc[s.index[0] - 1, "soc"]) * 100), "soc_eind": round(float(s["soc"].iloc[-1]) * 100)}


def kpi_met_aansluiting(map_, kpi, cfg, standaard=None):
    """Voegt de aansluiting-KPI toe aan runs van vóór die KPI (berekend uit de opgeslagen uurdata)."""
    if "aansluiting" not in kpi:
        el = pd.read_csv(map_ / "uurdata.csv", usecols=["el"])["el"]
        kpi["aansluiting"] = aansluiting(el, cfg.get("aansluiting", standaard))
    return kpi

