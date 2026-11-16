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
    """Gevraagde reductie als fractie (0–1) uit strategie.congestie; oude configuraties met `alles_uit` blijven werken."""
    if "verlaging_pct" in c:
        return min(1.0, max(0.0, float(c["verlaging_pct"]) / 100))
    return 1.0   # oude configuraties (alles_uit / reductie_kwe): als volledig uit behandelen


class Congestie(Referentie):
    """Strategie 3. In het congestievenster geldt een plafond voor het elektrisch vermogen van de WP's samen:
    (100 % − reductie) × hun maximale vermogen (100 % = uit). Vragen de kassen meer dan de WP's onder het plafond
    kunnen leveren, dan levert het buffer de rest (HT en LT naar verhouding); daaronder draaien de WP's gewoon.
    Buiten het venster gedraagt de regelaar zich als de referentie en laadt het buffer weer vol.

    Adaptief (perfecte voorspelling van de vensterdag): past de buffervraag van de hele dag bij de start van het venster
    niet in de buffervulling, dan wordt het plafond voor die dag verhoogd tot het past. Zo wordt een kleinere,
    maar zekere reductie over het hele venster gehaald in plaats van een volledige reductie die halverwege stopt.
    """
    label = "3 · Netcongestie"
    beschrijving = "Begrenst het WP-vermogen in het congestievenster tot een plafond; buffer levert de rest, laadt buiten het venster bij."
    naam = "congestie"

    def start(self, cfg, df, buffer):
        super().start(cfg, df, buffer)
        from .componenten import elektra
        from .kpi import max_vermogen
        c = cfg["strategie"].get("congestie", {})
        self.f = verlaging_fractie(c)
        self.adaptief = c.get("adaptief", True)
        self.veilig = c.get("veiligheid", 0.95)
        self.p_max = max_vermogen(cfg)["totaal_kwe"]
        self.q_ht = df["q_ht"].values
        self.q_lt = (df["q_lt"] - df[["q_cond", "q_lt"]].min(axis=1)).values   # LT-vraag na condensorwarmte
        self.vens = df["congestievenster"].values.astype(bool)
        ht, lt, cc = cfg["warmtepompen"]["ht"], cfg["warmtepompen"]["lt"], cfg["cop"]
        t_ht, t_lt = df["t_aanvoer_ht"].values, df["t_aanvoer_lt"].values
        # elektrisch vermogen van de WP's als een deel g van de warmtevraag uit het buffer komt (direct leveren, niet laden)
        self._el = lambda i, g: (elektra((1 - g) * self.q_ht[i], t_ht[i], ht, cc)[0]
                                 + elektra((1 - g) * self.q_lt[i], t_lt[i], lt, cc)[0])
        self.plafond = (1 - self.f) * self.p_max
        self.uren = []

    def _buffer_deel(self, i, plafond):
        """Deel (0–1) van de warmtevraag in uur i dat uit het buffer moet komen om onder het plafond te blijven."""
        if plafond <= 0:
            return 1.0
        if self._el(i, 0.0) <= plafond:
            return 0.0
        lo, hi = 0.0, 1.0
        for _ in range(25):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if self._el(i, mid) > plafond else (lo, mid)
        return hi

    def _vensterwarmte(self, plafond):
        return sum(self._buffer_deel(j, plafond) * (self.q_ht[j] + self.q_lt[j]) for j in self.uren)

    def besluit(self, i, r, buf):
        if not self.vens[i]:
            return super().besluit(i, r, buf)
        if i == 0 or not self.vens[i - 1]:   # start van een venster: uren en plafond voor deze dag bepalen
            j, self.uren = i, []
            while j < len(self.vens) and self.vens[j]:
                self.uren.append(j)
                j += 1
            self.plafond = (1 - self.f) * self.p_max
            if self.adaptief:
                beschikbaar = self.veilig * buf.e
                if self._vensterwarmte(self.plafond) > beschikbaar:
                    lo, hi = self.plafond, self.p_max   # hoger plafond = minder uit het buffer
                    for _ in range(20):
                        mid = (lo + hi) / 2
                        lo, hi = (mid, hi) if self._vensterwarmte(mid) > beschikbaar else (lo, mid)
                    self.plafond = hi
        g = self._buffer_deel(i, self.plafond)
        return {"buf_ht": g * self.q_ht[i], "buf_lt": g * self.q_lt[i], "laad": 0.0}


STRATEGIEEN = {"referentie": Referentie, "congestie": Congestie}


def maak_regelaar(naam):
    return STRATEGIEEN[naam]()
