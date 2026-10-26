"""Draai een simulatie vanaf de opdrachtregel. Scenario en resultaat komen in dezelfde mappen als die van de webapp
(`scenarios/`, `runs/`), dus een run van hier verschijnt ook in de app.

    python run.py --scenario netcongestie-200-m                     # bestaand scenario draaien
    python run.py --naam "Buffer 60 °C" --strategie congestie --set buffer.t_laad_c=60 --set strategie.congestie.verlaging_pct=50
                                                                    # nieuw scenario op basis van config/basis.yaml
"""
import argparse
import json

import yaml

from botu_sim.kpi import bod_vergelijking
from webapp import main as app
from webapp import schema


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scenario", help="id van een bestaand scenario (scenarios/<id>.yaml)")
    ap.add_argument("--naam", help="naam van een nieuw scenario op basis van config/basis.yaml")
    ap.add_argument("--omschrijving", default="aangemaakt via run.py")
    ap.add_argument("--strategie", choices=["referentie", "congestie"])
    ap.add_argument("--set", action="append", default=[], metavar="SLEUTEL=WAARDE", help="bv. buffer.volume_m3=300 (zie webapp/schema.py)")
    a = ap.parse_args()
    if bool(a.scenario) == bool(a.naam):
        ap.error("geef --scenario of --naam")

    if a.naam:
        waarden = schema.waarden_uit_config(app.BASIS)
        sets = [s.split("=", 1) for s in a.set] + ([["strategie.naam", a.strategie]] if a.strategie else [])
        for k, v in sets:
            if k not in schema.SLEUTELS:
                ap.error(f"onbekende instelling {k}; kies uit webapp/schema.py")
            waarden[k] = yaml.safe_load(v)
        sid = app.nieuw_scenario(app.Scenario(naam=a.naam, omschrijving=a.omschrijving, waarden=waarden))["id"]
        print(f"scenario aangemaakt: scenarios/{sid}.yaml")
    else:
        sid = a.scenario

    try:
        rid, cfg = app.maak_run(sid)
    except app.HTTPException as e:
        raise SystemExit(f"{e.detail}: {sid}")
    app._uitvoeren(rid, cfg)
    m = app._meta(rid)
    if m["status"] != "klaar":
        raise SystemExit(m.get("fout", "run mislukt"))
    k = json.loads((app.RUNS / rid / "kpi.json").read_text())
    print(f"== run {rid} ({m['duur_s']} s)")
    print(json.dumps({g: k[g] for g in ("elektra", "buffer", "warmte", "worstcase_met_condensor")}, indent=1, ensure_ascii=False))
    print("\nVergelijking met BOD (MWh/jr):")
    for label, bod, sim in bod_vergelijking(k):
        print(f"  {label:22s} BOD {bod:6.0f}   model {sim:7.1f}")


if __name__ == "__main__":
    main()
