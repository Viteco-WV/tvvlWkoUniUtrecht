"""Flexibiliteitsenvelop: hoeveel kWe kunnen de WP's hoe lang minder trekken in het congestievenster?

Doorlopende berekening over het jaar, per gevraagde verlaging R (kWe):
- basislijn = elektrisch vermogen van de WP's bij directe levering (uit een referentierun);
- in het congestievenster: WP-vermogen naar max(0, basis − R). De niet-geproduceerde warmte komt uit het buffer,
  eerst via terugregelen van de HT-WP's (minder buffer-kWh per kWe), daarna LT: warmte = ΔP · COP van dat uur.
  Is het buffer (of het ontlaadvermogen) ontoereikend, dan wordt alleen het haalbare deel verlaagd;
- buiten het venster laden de HT-WP's het buffer terug tot vol, met hun restcapaciteit (laden op 69 °C);
- de buffervulling loopt door van dag tot dag (wat niet bijgeladen wordt, ontbreekt de volgende dag).
"""
import numpy as np
import pandas as pd

from .componenten import Buffer, cop


def envelop(res, cfg, reducties=(25, 50, 75, 100, 125, 150, 200), soc_start=1.0):
    ht = cfg["warmtepompen"]["ht"]
    ht_max = ht["aantal"] * ht["p_max_kw"]
    t_laad_wp = cfg["buffer"]["t_laad_c"] + cfg["buffer"]["dt_wisselaar_k"]
    cop_laad = cop(t_laad_wp, ht["p_max_kw"], ht, cfg["cop"])
    buf = Buffer({**cfg["buffer"], "soc_start": soc_start})
    p_ont = buf.c["p_max_kw"]

    el_ht, el_lt = res["el_ht"].values, res["el_lt"].values
    cop_ht = np.where(res["q_htwp"] > 0, res["q_htwp"] / np.maximum(el_ht, 1e-9), 0)
    cop_lt = np.where(res["ltwp"] > 0, res["ltwp"] / np.maximum(el_lt, 1e-9), 0)
    # basislijn zonder de laadbijdrage van de referentie: alleen directe levering
    el_ht_dir = np.where(res["q_htwp"] > 0, res["htwp_dir"] / np.maximum(cop_ht, 1e-9), 0)
    q_htdir = res["htwp_dir"].values
    t_b = res["t_buiten"].values
    vens = res["congestievenster"].astype(bool).values
    lokaal = pd.to_datetime(res["t_lokaal"])
    maand, datum = lokaal.dt.month.values, lokaal.dt.date.values

    samenvatting, uur_uit = [], {}
    for R in list(reducties) + ["alles"]:
        buf.e = soc_start * buf.e_max
        gerealiseerd = np.zeros(len(res))
        gevraagd = np.zeros(len(res))
        extra_laad_el = 0.0
        for i in range(len(res)):
            if vens[i]:
                basis = el_ht_dir[i] + el_lt[i]
                doel = basis if R == "alles" else min(R, basis)
                gevraagd[i] = doel
                ruimte = min(buf.e, p_ont)
                d_ht = min(doel, el_ht_dir[i])
                q_ht = d_ht * cop_ht[i]
                if q_ht > ruimte:                       # buffer schiet tekort: deel van de HT-verlaging
                    d_ht, q_ht = ruimte / max(cop_ht[i], 1e-9), ruimte
                d_lt = min(doel - d_ht, el_lt[i]) if d_ht >= min(doel, el_ht_dir[i]) - 1e-9 else 0.0
                q_lt = min(d_lt * cop_lt[i], ruimte - q_ht)
                d_lt = q_lt / cop_lt[i] if cop_lt[i] > 0 else 0.0
                gerealiseerd[i] = d_ht + d_lt
                buf.e -= q_ht + q_lt
            else:
                vrij = max(0.0, ht_max - q_htdir[i])
                laad = min(vrij, buf.e_max - buf.e, p_ont)
                buf.e += laad
                extra_laad_el += laad / cop_laad
            buf.e = max(0.0, buf.e - buf.verlies(t_b[i]))

        v = vens
        vol = np.isclose(gerealiseerd[v], gevraagd[v], atol=1e-6)
        dagtabel = pd.DataFrame({"datum": datum[v], "maand": maand[v], "vol": vol, "real": gerealiseerd[v], "gevr": gevraagd[v]})
        per_dag = dagtabel.groupby("datum").agg(vol=("vol", "all"), uren_vol=("vol", "sum"), uren=("vol", "size"), maand=("maand", "first"))
        # langste aaneengesloten reeks uren met volledige verlaging per dag
        duur = dagtabel.groupby("datum")["vol"].apply(lambda s: int(np.max(np.diff(np.flatnonzero(np.r_[True, ~s.values, True])) - 1)))
        basis_v = el_ht_dir[v] + el_lt[v]
        maxpiek_voor = pd.Series(basis_v).groupby(maand[v]).max()
        maxpiek_na = pd.Series(basis_v - gerealiseerd[v]).groupby(maand[v]).max()
        samenvatting.append({
            "reductie_kwe": R,
            "uren_volledig_pct": round(100 * float(vol.mean()), 1),
            "dagen_heel_venster_pct": round(100 * float(per_dag["vol"].mean()), 1),
            "gem_duur_volledig_h": round(float(duur.mean()), 1),
            "min_duur_volledig_h": int(duur.min()),
            "gem_verlaging_kwe": round(float(gerealiseerd[v].mean()), 1),
            "max_wp_kwe_venster_voor": {int(m): round(float(x), 1) for m, x in maxpiek_voor.items()},
            "max_wp_kwe_venster_na": {int(m): round(float(x), 1) for m, x in maxpiek_na.items()},
            "maandpiekverlaging_som_kwe": round(float((maxpiek_voor - maxpiek_na).sum()), 1),
            "vermeden_in_venster_mwhe": round(float(gerealiseerd[v].sum()) / 1000, 1),
            "laden_buiten_venster_mwhe": round(extra_laad_el / 1000, 1),
        })
        uur_uit[str(R)] = gerealiseerd
    return pd.DataFrame(samenvatting), pd.DataFrame(uur_uit)
