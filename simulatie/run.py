"""Draai een simulatie.

    python run.py                                  # config/basis.yaml, strategie uit de config
    python run.py --config config/basis.yaml --strategie referentie --naam ref_stooklijn
    python run.py --set temperatuur.modus=vraaggestuurd --naam ref_vraag
"""
import argparse
import json
from pathlib import Path

import yaml

from botu_sim.config import laad_config
from botu_sim.data import laad_invoer
from botu_sim.kpi import bereken, bod_vergelijking
from botu_sim.simulatie import simuleer
from botu_sim.strategieen import maak_regelaar
from botu_sim import worstcase

HIER = Path(__file__).parent


def _set(overr, sleutel, waarde):
    d = overr
    delen = sleutel.split(".")
    for k in delen[:-1]:
        d = d.setdefault(k, {})
    d[delen[-1]] = yaml.safe_load(waarde)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(HIER / "config/basis.yaml"))
    ap.add_argument("--strategie")
    ap.add_argument("--naam")
    ap.add_argument("--set", action="append", default=[], help="sleutel.pad=waarde, bv. buffer.t_laad_c=60")
    ap.add_argument("--worstcase", action="store_true", help="ook overbruggingstijd berekenen")
    a = ap.parse_args()

    overr = {}
    for s in a.set:
        k, v = s.split("=", 1)
        _set(overr, k, v)
    if a.strategie:
        _set(overr, "strategie.naam", a.strategie)
    cfg = laad_config(a.config, overr)
    naam = a.naam or f"{cfg['naam']}_{cfg['strategie']['naam']}"

    df = laad_invoer(cfg)
    res = simuleer(cfg, df, maak_regelaar(cfg["strategie"]["naam"]))
    k = bereken(res, cfg)
    if a.worstcase:
        k["worstcase_met_condensor"] = worstcase.samenvatting(worstcase.overbrugging(cfg, df, True))
        k["worstcase_zonder_condensor"] = worstcase.samenvatting(worstcase.overbrugging(cfg, df, False))

    uit = HIER / "resultaten" / naam
    uit.mkdir(parents=True, exist_ok=True)
    res.to_csv(uit / "uurdata.csv", index=False)
    (uit / "kpi.json").write_text(json.dumps(k, indent=1, ensure_ascii=False))
    (uit / "config.yaml").write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False))

    print(f"== {naam}")
    print(json.dumps({x: k[x] for x in k if x != "elektra"} | {"elektra": {y: v for y, v in k["elektra"].items() if y != "maandpieken_kwe"}}, indent=1, ensure_ascii=False))
    print("\nVergelijking met BOD (MWh/jr):")
    for label, bod, sim in bod_vergelijking(k):
        print(f"  {label:22s} BOD {bod:6.0f}   model {sim:7.1f}")


if __name__ == "__main__":
    main()
