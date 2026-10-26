import math
import numpy as np

RHO_C = 1.163  # kWh/(m³·K), water


def cop(t_c, p_per_wp, wp, cfg_cop):
    """COP = η · T_c / (T_c − T_v) · f(deellast); temperaturen in °C, omgerekend naar K."""
    tc = t_c + 273.15
    tv = cfg_cop["t_verdamper_c"] + 273.15
    p_nom = wp["p_max_kw"] / cfg_cop["p_max_tov_nominaal"]
    tabel = np.array(cfg_cop["deellast"])
    f = np.interp(p_per_wp / p_nom, tabel[:, 0], tabel[:, 1])
    return cfg_cop["eta_carnot"] * tc / (tc - tv) * f


def wp_bedrijf(q, wp):
    """Hoe een WP-groep een uurvraag q (kWh) levert.

    Geeft (aantal draaiend, vermogen per WP tijdens bedrijf, looptijdfractie).
    Onder de minimumlast pendelt één WP: hij draait op minimumlast gedurende een fractie van het uur.
    """
    if q <= 1e-9:
        return 0, 0.0, 0.0
    n = min(wp["aantal"], math.ceil(q / wp["p_max_kw"] - 1e-9))
    p = q / n
    if p >= wp["p_min_kw"]:
        return n, p, 1.0
    return 1, wp["p_min_kw"], q / wp["p_min_kw"]


def elektra(q, t_c, wp, cfg_cop):
    """Elektrisch verbruik (kWh) en bedrijfsgegevens voor levering q bij condensortemperatuur t_c."""
    n, p, duty = wp_bedrijf(q, wp)
    if n == 0:
        return 0.0, dict(n=0, duty=0.0, cop=np.nan)
    c = cop(t_c, p, wp, cfg_cop)
    return q / c, dict(n=n, duty=duty, cop=c)


class Buffer:
    """Volledig gelaagd buffer: bovenin T_laad, onderin T_retour. Energie E in kWh boven T_retour."""

    def __init__(self, cfg_buf):
        self.c = cfg_buf
        self.e_max = cfg_buf["volume_m3"] * RHO_C * (cfg_buf["t_laad_c"] - cfg_buf["t_retour_c"])
        self.e = cfg_buf["soc_start"] * self.e_max

    @property
    def soc(self):
        return self.e / self.e_max

    def t_levering(self):
        return self.c["t_laad_c"] - self.c["dt_wisselaar_k"]

    def kan_leveren_aan(self, t_eis):
        return self.t_levering() >= t_eis - 1e-9

    def verlies(self, t_buiten):
        t_gem = self.c["t_retour_c"] + self.soc * (self.c["t_laad_c"] - self.c["t_retour_c"])
        return max(0.0, self.ua * (t_gem - t_buiten))

    @property
    def ua(self):
        """UA schaalt met het oppervlak (∝ V^(2/3)) t.o.v. het referentievolume waarvoor ua_kw_per_k geldt."""
        v_ref = self.c.get("ua_referentie_m3", self.c["volume_m3"])
        return self.c["ua_kw_per_k"] * (self.c["volume_m3"] / v_ref) ** (2 / 3) if v_ref else self.c["ua_kw_per_k"]
