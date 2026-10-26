"""Tests voor de webapp-laag: dagwaarden (back-up, vensterdagen, nachtelijk laden), runbeheer en het PDF-rapport.

Draait twee jaarsimulaties (referentie en netcongestie 200 m³, WP's uit) in een tijdelijke map.
"""
import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from botu_sim.kpi import max_vermogen
from webapp import main, rekenen, schema
from webapp.rapport import maak_rapport

KOUD = ["2001-01-15", "2001-01-16", "2001-01-17", "2001-01-18"]


def _draai(map_, naam, wijziging):
    w = schema.waarden_uit_config(main.BASIS) | wijziging
    cfg = schema.config_uit_waarden(main.BASIS, w)
    rekenen.draai(cfg, map_)
    (map_ / "meta.json").write_text(json.dumps({"id": map_.name, "scenario_id": map_.name, "scenario_naam": naam,
                                                "omschrijving": "", "waarden": w, "gestart": "2026-01-01T00:00:00", "status": "klaar"}))
    u = pd.read_csv(map_ / "uurdata.csv", parse_dates=["t_lokaal"])
    return {"map": map_, "cfg": cfg, "u": u, "kpi": json.loads((map_ / "kpi.json").read_text())}


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    d = tmp_path_factory.mktemp("runs")
    return {
        "ref": _draai(d / "ref", "Referentie", {"strategie.naam": "referentie"}),
        "cong": _draai(d / "cong", "Netcongestie 200 m³", {"strategie.naam": "congestie", "strategie.congestie.verlaging_pct": 100,
                                                           "buffer.volume_m3": 200}),
    }


def _idx(u, datum):
    return u.index[u["t_lokaal"].dt.strftime("%Y-%m-%d") == datum]


def test_congestie_haalt_wps_uit_het_venster(runs):
    ref, cong = runs["ref"]["kpi"]["elektra"], runs["cong"]["kpi"]["elektra"]
    assert cong["gem_kwe_congestievenster"] < 0.05 * ref["gem_kwe_congestievenster"]
    assert runs["cong"]["kpi"]["warmte"]["tekort_mwh"] == 0                  # 200 m³ redt de koudste nachten nog


def test_vensterdagen(runs):
    vd = rekenen.vensterdagen(runs["cong"]["u"])
    assert len(vd) == 108                                                      # werkdagen nov–mrt in 2001
    assert (vd["uit"] == vd["uren"]).mean() > 0.95
    assert (rekenen.vensterdagen(runs["ref"]["u"])["uit"] == 0).all()        # referentie: WP's nooit uit in het venster


def test_backup_per_dag(runs):
    r = runs["cong"]
    idx = [i for d in KOUD for i in _idx(r["u"], d)]
    b = rekenen.dag_backup(r["map"], r["u"], idx)
    assert [x["datum"] for x in b] == KOUD and all(x["start"] == "08:00" for x in b)
    assert all(x["vol_h"] >= x["nu_h"] for x in b)                            # werkelijke vulling ≤ vol
    assert b[0]["soc_pct"] > b[-1]["soc_pct"]                                  # buffer loopt leeg in de koude reeks
    assert b[-1]["nu_h"] < 9                                                   # laatste dag: reserve korter dan het venster


def test_nachtelijk_laden_is_beperkt_op_koude_nachten(runs):
    r = runs["cong"]
    cap = r["cfg"]["warmtepompen"]["ht"]["aantal"] * r["cfg"]["warmtepompen"]["ht"]["p_max_kw"]
    koud = rekenen.nacht(r["u"], "2001-01-16", cap)
    gemiddeld = rekenen.nacht(r["u"], "2001-11-08", cap)
    assert 0 <= koud["laden_mwh"] < 0.5 < gemiddeld["laden_mwh"]
    assert koud["ht_wp_kw"] <= cap and koud["vol_uren"] >= 12                 # HT-WP's (bijna) de hele nacht op vol vermogen


def test_max_vermogen():
    mx = max_vermogen(main.BASIS)
    assert mx["ht"]["t_c"] == 69 and mx["totaal_kwe"] == pytest.approx(169.5, abs=1)


def test_rapport_pdf(runs):
    pdf = maak_rapport([runs["ref"]["map"], runs["cong"]["map"]])
    assert pdf[:5] == b"%PDF-" and pdf.count(b"/Type /Page\n") + pdf.count(b"/Type /Page ") >= 3


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "RUNS", tmp_path / "runs")
    monkeypatch.setattr(main, "SCENARIOS", tmp_path / "scenarios")
    (tmp_path / "runs").mkdir()
    (tmp_path / "scenarios").mkdir()
    return TestClient(main.app)


def test_scenario_verwijderen_ruimt_resultaten_op(client):
    w = schema.waarden_uit_config(main.BASIS)
    sid = client.post("/api/scenarios", json={"naam": "Test", "waarden": w}).json()["id"]
    for _ in range(2):
        rid, cfg = main.maak_run(sid)
        main._uitvoeren(rid, cfg)
    lijst = client.get("/api/runs").json()
    assert len(lijst) == 2 and all(m["scenario_bestaat"] for m in lijst)
    assert [m["nieuwste"] for m in lijst] == [True, False]                     # nieuwste eerst

    assert client.delete(f"/api/scenarios/{sid}").json() == {"ok": True, "runs_verwijderd": 2}
    assert client.get("/api/runs").json() == [] and not any(main.RUNS.iterdir())


def test_rapport_vraagt_twee_tot_vier_runs(client):
    assert client.get("/api/rapport?runs=een").status_code == 400
    assert client.get("/api/rapport?runs=a,b").status_code == 404


def test_verlaging_in_procenten(tmp_path):
    """50 % verlaging met een ruim buffer: het WP-vermogen in het venster halveert ongeveer."""
    ref = _draai(tmp_path / "ref", "Referentie", {"strategie.naam": "referentie"})
    half = _draai(tmp_path / "half", "50 %", {"strategie.naam": "congestie", "strategie.congestie.verlaging_pct": 50,
                                               "buffer.volume_m3": 300})
    g_ref, g_half = (r["kpi"]["elektra"]["gem_kwe_congestievenster"] for r in (ref, half))
    assert 0.4 < g_half / g_ref < 0.6
    assert half["kpi"]["warmte"]["tekort_mwh"] == 0
