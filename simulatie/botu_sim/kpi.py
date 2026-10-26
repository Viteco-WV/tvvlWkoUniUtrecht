import numpy as np

from .componenten import cop


def _mwh(x):
    return round(float(x.sum()) / 1000, 1)


AANSLUITING_STANDAARD = {"kva": 200, "cos_phi": 0.95, "overig_kwe": 0}


def aansluiting(el, c=None):
    """Elektrische aansluiting: grens voor de WP's (kVA · cos φ − overige gebruikers) en hoe vaak en hoeveel het
    WP-vermogen die overschrijdt (uurwaarden). Alleen gerapporteerd; het model begrenst de WP's niet."""
    c = {**AANSLUITING_STANDAARD, **(c or {})}
    grens = c["kva"] * c["cos_phi"] - c["overig_kwe"]
    boven = np.clip(np.asarray(el, dtype=float) - grens, 0, None)
    return {"kva": c["kva"], "grens_kwe": round(grens, 1), "uren_boven": int((boven > 0.05).sum()),
            "max_overschrijding_kwe": round(float(boven.max()), 1), "kwh_boven": round(float(boven.sum()))}


def bereken(res, cfg):
    t = cfg["tarieven"]
    tl = res["t_lokaal"]
    winter = tl.dt.month.isin(t.get("winter_maanden", [10, 11, 12, 1, 2, 3]))
    piek_u = t.get("piekuren_lokaal", [7, 23])
    piek = (tl.dt.weekday < 5) & (tl.dt.hour >= piek_u[0]) & (tl.dt.hour < piek_u[1])
    prijs = (winter * t["inkoop_winter_eur_kwh"] + ~winter * t["inkoop_zomer_eur_kwh"]
             + piek * t["opslag_piek_eur_kwh"] + ~piek * t["opslag_dal_eur_kwh"] + t["energiebelasting_eur_kwh"])
    warmte_wp = res["q_htwp"].sum() + res["ltwp"].sum()
    geleverd = res["q_ht"].sum() + res["q_lt"].sum() - res["tekort_ht"].sum() - res["tekort_lt"].sum()
    el = res["el"]
    maand = res["t_lokaal"].dt.month
    vens = res["congestievenster"].astype(bool)
    piek_maand = el.groupby(maand).max()
    piek_venster = el.where(vens).groupby(maand).max().fillna(0)
    starts = lambda n: int(((n.values[1:] > 0) & (n.values[:-1] == 0)).sum())
    pendel = lambda d: int(((d > 0) & (d < 1)).sum())

    return {
        "aansluiting": aansluiting(el, cfg.get("aansluiting")),
        "warmte": {
            "vraag_ht_mwh": _mwh(res["q_ht"]), "vraag_lt_mwh": _mwh(res["q_lt"]),
            "ht_wp_mwh": _mwh(res["q_htwp"]), "ht_wp_direct_mwh": _mwh(res["htwp_dir"]), "lt_wp_mwh": _mwh(res["ltwp"]),
            "condensor_naar_lt_mwh": _mwh(res["cond_lt"]), "condensor_naar_bron_mwh": _mwh(res["cond_bron"]),
            "tekort_mwh": _mwh(res["tekort_ht"] + res["tekort_lt"]),
            "tekort_uren": int(((res["tekort_ht"] + res["tekort_lt"]) > 1e-6).sum()),
        },
        "buffer": {
            "geladen_mwh": _mwh(res["laad"]), "naar_ht_mwh": _mwh(res["buf_ht"]), "naar_lt_mwh": _mwh(res["buf_lt"]),
            "verlies_mwh": _mwh(res["verlies"]), "gem_soc": round(float(res["soc"].mean()), 3),
            "min_soc": round(float(res["soc"].min()), 3),
        },
        "elektra": {
            "totaal_mwhe": _mwh(el), "ht_mwhe": _mwh(res["el_ht"]), "lt_mwhe": _mwh(res["el_lt"]),
            "spf_wp": round(float(warmte_wp / el.sum()), 2),
            "spf_systeem": round(float((geleverd - res["cond_lt"].sum()) / el.sum()), 2),
            "piek_kwe": round(float(el.max()), 1),
            "gem_kwe_congestievenster": round(float(el[vens].mean()), 1),
            "max_kwe_congestievenster": round(float(el[vens].max()), 1),
            "som_maandpieken_venster_kwe": round(float(piek_venster.sum()), 1),
            "maandpieken_kwe": {int(k): round(float(v), 1) for k, v in piek_maand.items()},
        },
        "bedrijf": {
            "ht_starts": starts(res["n_ht"]), "lt_starts": starts(res["n_lt"]),
            "ht_pendeluren": pendel(res["duty_ht"]), "lt_pendeluren": pendel(res["duty_lt"]),
            "ht_draaiuren": int((res["n_ht"] > 0).sum()), "lt_draaiuren": int((res["n_lt"] > 0).sum()),
        },
        "bron": {"verdamper_mwh": round(float(warmte_wp - el.sum()) / 1000, 1)},
        "kosten": {
            "inkoop_vast_eur": round(float((el * prijs).sum())),           # vast contract: seizoenstarief + opslag piek/dal + EB
            "gem_prijs_eur_kwh": round(float((el * prijs).sum() / el.sum()), 4),
            "kwmax_wp_maandpieken_eur": round(float(piek_maand.sum() * t["kwmax_eur_kw_maand"])),
            "inkoop_dayahead_2024_eur": round(float((el * res["prijs_2024"]).sum())),
            "inkoop_dayahead_2025_eur": round(float((el * res["prijs_2025"]).sum())),
            "indicatie_kwmax_venster_eur": round(float(piek_venster.sum() * t["kwmax_eur_kw_maand"])),
        },
    }


def bod_vergelijking(k):
    """Naast de BOD-energiebalans (IF, DO 27-8-2026)."""
    return [
        ("HT-WP totaal", 1403, k["warmte"]["ht_wp_mwh"]),
        ("HT-WP direct", 1283, k["warmte"]["ht_wp_direct_mwh"]),
        ("Buffer geladen", 239, k["buffer"]["geladen_mwh"]),
        ("Buffer → HT", 100, k["buffer"]["naar_ht_mwh"]),
        ("Buffer → LT", 138, k["buffer"]["naar_lt_mwh"]),
        ("LT-WP", 205, k["warmte"]["lt_wp_mwh"]),
        ("Condensor ZLT → LT", 151, k["warmte"]["condensor_naar_lt_mwh"]),
        ("Bufferverlies", 1, k["buffer"]["verlies_mwh"]),
        ("Bron → verdampers", 1086, k["bron"]["verdamper_mwh"]),
    ]


def max_vermogen(cfg):
    """Maximaal elektrisch vermogen dat de WP's samen kunnen vragen: alle WP's op p_max bij de slechtste COP
    (HT: hoogste van buffer laden en top stooklijn; LT: top stooklijn). Per groep en totaal, in kWe."""
    uit = {}
    for net in ("ht", "lt"):
        wp = cfg["warmtepompen"][net]
        t = max(p[1] for p in cfg["temperatuur"]["stooklijn"][net])
        if net == "ht":
            t = max(t, cfg["buffer"]["t_laad_c"] + cfg["buffer"]["dt_wisselaar_k"])
        c = cop(t, wp["p_max_kw"], wp, cfg["cop"])
        uit[net] = {"kwe": round(wp["aantal"] * wp["p_max_kw"] / c, 1), "t_c": t, "cop": round(float(c), 2)}
    uit["totaal_kwe"] = round(uit["ht"]["kwe"] + uit["lt"]["kwe"], 1)
    return uit

