import numpy as np

from .componenten import Buffer


def overbrugging(cfg, df, met_condensor=True, max_uur=400):
    """Worst case: alle WP's uit, buffer start vol. Aantal uren dat HT + LT volledig geleverd worden, per startuur."""
    buf = Buffer({**cfg["buffer"], "soc_start": 1.0})
    t_lev = buf.t_levering()
    q_ht, q_lt = df["q_ht"].values, df["q_lt"].values
    q_cond = df["q_cond"].values if met_condensor else np.zeros(len(df))
    t_ht, t_lt, t_b = df["t_aanvoer_ht"].values, df["t_aanvoer_lt"].values, df["t_buiten"].values
    n = len(df)
    uren = np.zeros(n, dtype=int)
    for s in range(n):
        buf.e = buf.e_max
        h = 0
        while h < max_uur:
            i = (s + h) % n
            if (q_ht[i] > 1e-9 and t_lev < t_ht[i] - 1e-9) or (q_lt[i] > q_cond[i] + 1e-9 and t_lev < t_lt[i] - 1e-9):
                break
            vraag = q_ht[i] + max(0.0, q_lt[i] - q_cond[i])
            if vraag > min(buf.e, buf.c["p_max_kw"]) + 1e-9:
                break
            buf.e = max(0.0, buf.e - vraag - buf.verlies(t_b[i]))
            h += 1
        uren[s] = h
    return uren


def samenvatting(uren):
    return {f">= {x} h": round(float((uren >= x).mean() * 100), 1) for x in (12, 24, 48, 96)} | {
        "kortst_h": int(uren.min()), "mediaan_h": float(np.median(uren))}
