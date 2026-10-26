import pandas as pd

from .componenten import Buffer, wp_bedrijf, cop, elektra

TOL = 1e-6


class BalansFout(RuntimeError):
    pass


def simuleer(cfg, df, regelaar):
    """Uurlus. De regelaar geeft wensen (buf_ht, buf_lt, laad); de fysica en grenzen worden hier afgedwongen.

    Volgorde per uur: condensorwarmte ZLT → LT, buffer → LT, LT-WP, buffer → HT, HT-WP direct,
    daarna laden met de resterende HT-capaciteit. Tekorten na maximale inzet worden als `tekort` geboekt.
    """
    buf = Buffer(cfg["buffer"])
    ht, lt = cfg["warmtepompen"]["ht"], cfg["warmtepompen"]["lt"]
    ht_max, lt_max = ht["aantal"] * ht["p_max_kw"], lt["aantal"] * lt["p_max_kw"]
    c_cop = cfg["cop"]
    t_laad_wp = cfg["buffer"]["t_laad_c"] + cfg["buffer"]["dt_wisselaar_k"]
    regelaar.start(cfg, df, buf)
    uit = []

    for i, r in enumerate(df.itertuples(index=False)):
        w = regelaar.besluit(i, r, buf)
        e_start = buf.e
        ruimte_ontlaad = min(buf.e, buf.c["p_max_kw"])
        ok_lt, ok_ht = buf.kan_leveren_aan(r.t_aanvoer_lt), buf.kan_leveren_aan(r.t_aanvoer_ht)

        # LT-net
        cond_lt = min(r.q_cond, r.q_lt)
        rest_lt = r.q_lt - cond_lt
        buf_lt = min(w.get("buf_lt", 0.0), rest_lt, ruimte_ontlaad) if ok_lt else 0.0
        ltwp = rest_lt - buf_lt
        if ltwp > lt_max and ok_lt:
            extra = min(ltwp - lt_max, ruimte_ontlaad - buf_lt)
            buf_lt, ltwp = buf_lt + extra, ltwp - extra
        tekort_lt = max(0.0, ltwp - lt_max)
        ltwp -= tekort_lt

        # HT-net
        ruimte_ontlaad -= buf_lt
        buf_ht = min(w.get("buf_ht", 0.0), r.q_ht, ruimte_ontlaad) if ok_ht else 0.0
        htwp_dir = r.q_ht - buf_ht
        if htwp_dir > ht_max and ok_ht:
            extra = min(htwp_dir - ht_max, ruimte_ontlaad - buf_ht)
            buf_ht, htwp_dir = buf_ht + extra, htwp_dir - extra
        tekort_ht = max(0.0, htwp_dir - ht_max)
        htwp_dir -= tekort_ht

        # Laden (alleen HT-WP's)
        vrij_na = buf.e_max - (buf.e - buf_lt - buf_ht)
        laad = max(0.0, min(w.get("laad", 0.0), vrij_na, ht_max - htwp_dir, buf.c["p_max_kw"] - buf_lt - buf_ht))

        verlies = buf.verlies(r.t_buiten)
        e_eind = buf.e - buf_lt - buf_ht + laad - verlies
        if e_eind < 0:
            verlies += e_eind
            e_eind = 0.0
        buf.e = e_eind

        # Elektriciteit: directe levering op netaanvoertemperatuur, laden op T_laad + ΔT_wisselaar
        q_htwp = htwp_dir + laad
        n_ht, p_ht, duty_ht = wp_bedrijf(q_htwp, ht)
        if n_ht:
            cop_dir, cop_laad = cop(r.t_aanvoer_ht, p_ht, ht, c_cop), cop(t_laad_wp, p_ht, ht, c_cop)
            el_ht = htwp_dir / cop_dir + laad / cop_laad
        else:
            cop_dir = cop_laad = float("nan")
            el_ht = 0.0
        el_lt, info_lt = elektra(ltwp, r.t_aanvoer_lt, lt, c_cop)

        # Balanscontrole
        fouten = [
            abs(htwp_dir + buf_ht + tekort_ht - r.q_ht),
            abs(ltwp + buf_lt + cond_lt + tekort_lt - r.q_lt),
            abs(e_start - buf_lt - buf_ht + laad - verlies - buf.e),
        ]
        if max(fouten) > TOL or buf.e > buf.e_max + TOL or buf.e < -TOL:
            raise BalansFout(f"uur {i} ({r.t}): balansfout {fouten}, E={buf.e:.3f}")

        regelaar.na_uur(i, r, buf)
        uit.append(dict(
            q_ht=r.q_ht, q_lt=r.q_lt, htwp_dir=htwp_dir, laad=laad, q_htwp=q_htwp, ltwp=ltwp,
            buf_ht=buf_ht, buf_lt=buf_lt, cond_lt=cond_lt, cond_bron=r.q_cond - cond_lt,
            tekort_ht=tekort_ht, tekort_lt=tekort_lt, verlies=verlies, e_buffer=buf.e, soc=buf.soc,
            el_ht=el_ht, el_lt=el_lt, el=el_ht + el_lt,
            n_ht=n_ht, duty_ht=duty_ht, n_lt=info_lt["n"], duty_lt=info_lt["duty"],
            cop_ht_dir=cop_dir, cop_ht_laad=cop_laad, cop_lt=info_lt["cop"],
            t_aanvoer_ht=r.t_aanvoer_ht, t_aanvoer_lt=r.t_aanvoer_lt, t_buiten=r.t_buiten,
            congestievenster=r.congestievenster, prijs_2024=r.prijs_2024, prijs_2025=r.prijs_2025,
        ))

    res = pd.DataFrame(uit)
    res.insert(0, "t", df["t"].values)
    res.insert(1, "t_lokaal", df["t_lokaal"].values)
    return res
