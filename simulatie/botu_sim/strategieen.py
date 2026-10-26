"""Regelaars. Elke regelaar geeft per uur wensen; de simulatie dwingt de fysica af.

Wensen (kWh in het uur): buf_ht, buf_lt = levering uit buffer; laad = laden door HT-WP's.
"""


class Regelaar:
    naam = "basis"

    def start(self, cfg, df, buffer):
        self.cfg, self.df = cfg, df

    def besluit(self, i, r, buffer):
        return {}

    def na_uur(self, i, r, buffer):
        pass


class Referentie(Regelaar):
    """Strategie 1. WP's volgen de vraag; het buffer wordt met HT-restcapaciteit vol gehouden (pieken en back-up).
    Onder de minimumlast pendelt een WP; dat blijft zichtbaar als KPI."""
    label = "1 · Referentie"
    beschrijving = "WP's volgen de vraag; buffer vol houden voor pieken en back-up."
    naam = "referentie"

    def start(self, cfg, df, buffer):
        super().start(cfg, df, buffer)
        self.doel = cfg["strategie"].get("referentie", {}).get("soc_doel", 1.0)

    def besluit(self, i, r, buf):
        return {"laad": max(0.0, self.doel * buf.e_max - buf.e)}


class Congestie(Referentie):
    """Strategie 3. In het congestievenster verlagen de WP's hun elektrisch vermogen met R kWe (of gaan uit);
    het buffer levert de warmte die dan ontbreekt (eerst HT terugregelen, daarna LT). Buiten het venster
    gedraagt de regelaar zich als de referentie en laadt het buffer weer vol.

    Adaptief (perfecte voorspelling van de vensterdag): past de gevraagde verlaging bij de start van het venster
    niet in de buffervulling, dan wordt R voor die dag verlaagd tot het past. Zo wordt een kleinere, maar
    zekere verlaging over het hele venster gehaald in plaats van een volledige verlaging die halverwege stopt.
    """
    label = "3 · Netcongestie"
    beschrijving = "Verlaagt het WP-vermogen in het congestievenster met R kWe; buffer levert, laadt buiten het venster bij."
    naam = "congestie"

    def start(self, cfg, df, buffer):
        super().start(cfg, df, buffer)
        from .componenten import cop, wp_bedrijf
        c = cfg["strategie"].get("congestie", {})
        self.R = float("inf") if c.get("alles_uit", False) else float(c.get("reductie_kwe", 100))
        self.adaptief = c.get("adaptief", True)
        self.veilig = c.get("veiligheid", 0.95)
        ht, lt, cc = cfg["warmtepompen"]["ht"], cfg["warmtepompen"]["lt"], cfg["cop"]

        def cop_uur(q, t, wp):
            n, p, _ = wp_bedrijf(q, wp)
            return cop(t, p, wp, cc) if n else 1.0

        self.q_ht = df["q_ht"].values
        self.q_lt = (df["q_lt"] - df[["q_cond", "q_lt"]].min(axis=1)).values
        self.cop_ht = [cop_uur(q, t, ht) for q, t in zip(self.q_ht, df["t_aanvoer_ht"].values)]
        self.cop_lt = [cop_uur(q, t, lt) for q, t in zip(self.q_lt, df["t_aanvoer_lt"].values)]
        self.vens = df["congestievenster"].values.astype(bool)
        self.R_dag = self.R

    def _verlaging(self, i, R):
        el_ht = self.q_ht[i] / self.cop_ht[i]
        el_lt = self.q_lt[i] / self.cop_lt[i]
        d_ht = min(R, el_ht)
        d_lt = min(R - d_ht, el_lt)
        w_ht = self.q_ht[i] * (d_ht / el_ht if el_ht > 0 else 0.0)
        w_lt = self.q_lt[i] * (d_lt / el_lt if el_lt > 0 else 0.0)
        return w_ht, w_lt

    def _vensterwarmte(self, i, R):
        tot, j = 0.0, i
        while j < len(self.vens) and self.vens[j]:
            w_ht, w_lt = self._verlaging(j, R)
            tot += w_ht + w_lt
            j += 1
        return tot

    def besluit(self, i, r, buf):
        if not self.vens[i]:
            return super().besluit(i, r, buf)
        if (i == 0 or not self.vens[i - 1]):
            self.R_dag = self.R
            if self.adaptief:
                beschikbaar = self.veilig * buf.e
                if self._vensterwarmte(i, self.R) > beschikbaar:
                    lo, hi = 0.0, min(self.R, 2000.0)
                    for _ in range(30):
                        mid = (lo + hi) / 2
                        lo, hi = (mid, hi) if self._vensterwarmte(i, mid) <= beschikbaar else (lo, mid)
                    self.R_dag = lo
        w_ht, w_lt = self._verlaging(i, self.R_dag)
        return {"buf_ht": w_ht, "buf_lt": w_lt, "laad": 0.0}


STRATEGIEEN = {"referentie": Referentie, "congestie": Congestie}


def maak_regelaar(naam):
    return STRATEGIEEN[naam]()
