"""FastAPI-backend van de simulatie-webapp.

Start (vanuit simulatie/):  .venv/bin/uvicorn webapp.main:app --port 8000
"""
import json
import re
import shutil
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path

import yaml
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from botu_sim.config import laad_config
from . import rekenen, schema

HIER = Path(__file__).parent
SIM = HIER.parent
SCENARIOS = SIM / "scenarios"
RUNS = SIM / "runs"
SCENARIOS.mkdir(exist_ok=True)
RUNS.mkdir(exist_ok=True)
BASIS = laad_config(SIM / "config/basis.yaml")

app = FastAPI(title="BoTu UU · simulatie")
app.mount("/static", StaticFiles(directory=HIER / "static"), name="static")


def _slug(t):
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")[:40] or "scenario"


def _nu():
    return datetime.now().isoformat(timespec="seconds")


# ------------------------------------------------------------------ pagina
@app.get("/", response_class=HTMLResponse)
def index():
    """index.html met versienummer (wijzigingsdatum) achter css/js, zodat de browser nooit een oude versie gebruikt."""
    v = int(max((HIER / "static" / f).stat().st_mtime for f in ("app.js", "app.css")))
    return (HIER / "static/index.html").read_text().replace("{{v}}", str(v))


# ------------------------------------------------------------------ invoer
@app.get("/api/schema")
def get_schema():
    return {"groepen": schema.GROEPEN, "maanden": schema.MAANDEN, "basis": schema.waarden_uit_config(BASIS)}


class Scenario(BaseModel):
    naam: str
    omschrijving: str = ""
    waarden: dict


@app.get("/api/scenarios")
def lijst_scenarios():
    uit = [yaml.safe_load(p.read_text()) for p in sorted(SCENARIOS.glob("*.yaml"))]
    return sorted(uit, key=lambda s: s.get("gewijzigd", ""), reverse=True)


@app.get("/api/scenarios/{sid}")
def get_scenario(sid: str):
    p = SCENARIOS / f"{sid}.yaml"
    if not p.exists():
        raise HTTPException(404, "scenario niet gevonden")
    return yaml.safe_load(p.read_text())


@app.put("/api/scenarios/{sid}")
def bewaar_scenario(sid: str, s: Scenario):
    p = SCENARIOS / f"{sid}.yaml"
    oud = yaml.safe_load(p.read_text()) if p.exists() else {}
    doc = {"id": sid, "naam": s.naam, "omschrijving": s.omschrijving, "aangemaakt": oud.get("aangemaakt", _nu()),
           "gewijzigd": _nu(), "waarden": s.waarden}
    schema.config_uit_waarden(BASIS, s.waarden)  # controle dat de waarden toepasbaar zijn
    p.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False))
    return doc


@app.post("/api/scenarios")
def nieuw_scenario(s: Scenario):
    sid = _slug(s.naam)
    i = 2
    while (SCENARIOS / f"{sid}.yaml").exists():
        sid = f"{_slug(s.naam)}-{i}"
        i += 1
    return bewaar_scenario(sid, s)


@app.delete("/api/scenarios/{sid}")
def verwijder_scenario(sid: str):
    (SCENARIOS / f"{sid}.yaml").unlink(missing_ok=True)
    return {"ok": True}


# ------------------------------------------------------------------ runs
class RunVerzoek(BaseModel):
    scenario_id: str


def _meta(rid):
    p = RUNS / rid / "meta.json"
    return json.loads(p.read_text()) if p.exists() else None


def _schrijf_meta(rid, m):
    (RUNS / rid / "meta.json").write_text(json.dumps(m, ensure_ascii=False, indent=1))


def _uitvoeren(rid, cfg):
    m = _meta(rid)
    t0 = time.time()
    try:
        rekenen.draai(cfg, RUNS / rid)
        m.update(status="klaar", duur_s=round(time.time() - t0, 1))
    except Exception as e:  # fout zichtbaar maken in de frontend
        m.update(status="fout", fout=f"{e}\n{traceback.format_exc(limit=3)}")
    _schrijf_meta(rid, m)


@app.post("/api/runs")
def start_run(v: RunVerzoek):
    sc = get_scenario(v.scenario_id)
    cfg = schema.config_uit_waarden(BASIS, sc["waarden"])
    rid = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + sc["id"][:30]
    (RUNS / rid).mkdir(parents=True)
    _schrijf_meta(rid, {"id": rid, "scenario_id": sc["id"], "scenario_naam": sc["naam"], "omschrijving": sc.get("omschrijving", ""),
                        "waarden": sc["waarden"], "gestart": _nu(), "status": "bezig"})
    threading.Thread(target=_uitvoeren, args=(rid, cfg), daemon=True).start()
    return _meta(rid)


@app.get("/api/runs")
def lijst_runs():
    uit = [m for p in RUNS.iterdir() if p.is_dir() and (m := _meta(p.name))]
    return sorted(uit, key=lambda m: m["gestart"], reverse=True)


@app.get("/api/runs/{rid}")
def get_run(rid: str):
    m = _meta(rid)
    if not m:
        raise HTTPException(404, "run niet gevonden")
    if m["status"] == "klaar":
        d = RUNS / rid
        m["kpi"] = json.loads((d / "kpi.json").read_text())
        m["typedagen"] = json.loads((d / "typedagen.json").read_text())
        m["flex"] = json.loads((d / "flex.json").read_text())
        m["worstcase"] = json.loads((d / "worstcase.json").read_text())
    return m


@app.get("/api/runs/{rid}/jaar")
def run_jaar(rid: str):
    return rekenen.jaaroverzicht(RUNS / rid)


@app.get("/api/runs/{rid}/dag")
def run_dag(rid: str, datum: str, dagen: int = 1):
    return rekenen.dagdata(RUNS / rid, datum, dagen)


@app.delete("/api/runs/{rid}")
def verwijder_run(rid: str):
    shutil.rmtree(RUNS / rid, ignore_errors=True)
    return {"ok": True}
