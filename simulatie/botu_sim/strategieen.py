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


def verlaging_fractie(c):
    """Gevraagde verlaging als fractie (0–1) uit strategie.congestie; oude configuraties met `alles_uit` blijven werken."""
    if "verlaging_pct" in c:
        return min(1.0, max(0.0, float(c["verlaging_pct"]) / 100))
    return 1.0   # oude configuraties (alles_uit / reductie_kwe): als volledig uit behandelen


class Congestie(Referentie):
    """Strategie 3. In het congestievenster draaien de WP's een percentage minder hard dan zonder verlaging
    (100 % = uit); het buffer levert de warmte die dan ontbreekt, voor HT en LT naar verhouding. Buiten het venster
    gedraagt de regelaar zich als de referentie en laadt het buffer weer vol.

    Adaptief (perfecte voorspelling van de vensterdag): past de gevraagde verlaging bij de start van het venster
    niet in de buffervulling, dan wordt het percentage voor die dag verlaagd tot het past. Zo wordt een kleinere,
    maar zekere verlaging over het hele venster gehaald in plaats van een volledige verlaging die halverwege stopt.
    """
    label = "3 · Netcongestie"
    beschrijving = "Verlaagt het WP-vermogen in het congestievenster met een percentage; buffer levert, laadt buiten het venster bij."
    naam = "congestie"

    def start(self, cfg, df, buffer):
        super().start(cfg, df, buffer)
        c = cfg["strategie"].get("congestie", {})
        self.f = verlaging_fractie(c)
        self.adaptief = c.get("adaptief", True)
        self.veilig = c.get("veiligheid", 0.95)
        self.q_ht = df["q_ht"].values
        self.q_lt = (df["q_lt"] - df[["q_cond", "q_lt"]].min(axis=1)).values   # LT-vraag na condensorwarmte
        self.vens = df["congestievenster"].values.astype(bool)
        self.f_dag = self.f

    def _vensterwarmte(self, i, f):
        tot, j = 0.0, i
        while j < len(self.vens) and self.vens[j]:
            tot += f * (self.q_ht[j] + self.q_lt[j])
            j += 1
        return tot

    def besluit(self, i, r, buf):
        if not self.vens[i]:
            return super().besluit(i, r, buf)
        if i == 0 or not self.vens[i - 1]:
            self.f_dag = self.f
            if self.adaptief:
                beschikbaar = self.veilig * buf.e
                nodig = self._vensterwarmte(i, 1.0)
                if self.f * nodig > beschikbaar:
                    self.f_dag = beschikbaar / nodig if nodig > 0 else self.f   # lineair in f: direct op te lossen
        return {"buf_ht": self.f_dag * self.q_ht[i], "buf_lt": self.f_dag * self.q_lt[i], "laad": 0.0}


STRATEGIEEN = {"referentie": Referentie, "congestie": Congestie}


def maak_regelaar(naam):
    return STRATEGIEEN[naam]()
