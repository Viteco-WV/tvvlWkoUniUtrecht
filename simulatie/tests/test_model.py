from pathlib import Path

import numpy as np
import pytest

from botu_sim.componenten import Buffer, cop, wp_bedrijf
from botu_sim.config import laad_config
from botu_sim.data import laad_invoer
from botu_sim.kpi import bereken
from botu_sim.simulatie import simuleer
from botu_sim.strategieen import maak_regelaar

CFG = Path(__file__).parents[1] / "config/basis.yaml"


@pytest.fixture(scope="module")
def cfg():
    return laad_config(CFG)


@pytest.fixture(scope="module")
def invoer(cfg):
    return laad_invoer(cfg)


def test_cop_steunpunten(cfg):
    ht = cfg["warmtepompen"]["ht"]
    p_nom = ht["p_max_kw"] / cfg["cop"]["p_max_tov_nominaal"]
    assert cop(45, p_nom, ht, cfg["cop"]) == pytest.approx(4.49, abs=0.01)   # aanname 4,5 bij 45 °C
    assert cop(70, p_nom, ht, cfg["cop"]) == pytest.approx(2.95, abs=0.05)   # Dutek 70/60: 2,91–2,93


def test_minimumlast_pendelt(cfg):
    ht = cfg["warmtepompen"]["ht"]
    assert wp_bedrijf(50, ht) == (1, 103, pytest.approx(50 / 103))
    assert wp_bedrijf(300, ht) == (2, 150, 1.0)


def test_buffercapaciteit(cfg):
    assert Buffer(cfg["buffer"]).e_max == pytest.approx(200 * 1.163 * 32)


def test_invoer_komt_overeen_met_bod(invoer):
    assert invoer["q_ht"].sum() / 1000 == pytest.approx(1383, abs=2)
    assert invoer["q_lt"].sum() / 1000 == pytest.approx(494, abs=2)
    assert len(invoer) == 8760


def test_referentie_sluit_en_levert_alles(cfg, invoer):
    res = simuleer(cfg, invoer, maak_regelaar("referentie"))   # BalansFout bij een fout
    k = bereken(res, cfg)
    assert k["warmte"]["tekort_mwh"] == 0
    geleverd = res["htwp_dir"] + res["buf_ht"] + res["ltwp"] + res["buf_lt"] + res["cond_lt"]
    assert np.allclose(geleverd, res["q_ht"] + res["q_lt"])
