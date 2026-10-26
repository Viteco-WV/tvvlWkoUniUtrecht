"""Invoerschema voor het scenarioscherm: welke parameters, in welke groep, met label, eenheid en status.

Sleutels zijn punt-paden in de configuratie; de speciale sleutels `stooklijn.*` worden omgezet naar de lijstnotatie.
Status volgt de skill: bron | afgeleid | aanname.
"""
import copy

MAANDEN = ["jan", "feb", "mrt", "apr", "mei", "jun", "jul", "aug", "sep", "okt", "nov", "dec"]

GROEPEN = [
    {"id": "strategie", "titel": "Strategie en ontlaadvenster", "velden": [
        {"k": "strategie.naam", "label": "Regelstrategie", "type": "select", "opties": [["referentie", "1 · Referentie"], ["congestie", "3 · Netcongestie"]], "status": "aanname"},
        {"k": "congestie.uren_lokaal", "label": "Ontlaadvenster", "type": "uren", "status": "afgeleid", "hulp": "Uren (lokale tijd) waarin het buffer de WP's vervangt."},
        {"k": "congestie.maanden", "label": "Periode", "type": "maandbereik", "status": "afgeleid"},
        {"k": "congestie.alleen_werkdagen", "label": "Alleen werkdagen", "type": "bool", "status": "afgeleid"},
        {"k": "strategie.congestie.alles_uit", "label": "WP's volledig uit in het venster", "type": "bool", "status": "aanname", "alleen": "congestie"},
        {"k": "strategie.congestie.reductie_kwe", "label": "Gevraagde verlaging", "eenheid": "kWe", "type": "number", "min": 0, "max": 1000, "step": 5, "status": "aanname", "alleen": "congestie", "verberg_als": "strategie.congestie.alles_uit"},
        {"k": "strategie.congestie.adaptief", "label": "Adaptief: per dag begrenzen tot wat in het buffer past", "type": "bool", "status": "aanname", "alleen": "congestie", "geavanceerd": True},
    ]},
    {"id": "buffer", "titel": "Buffer", "velden": [
        {"k": "buffer.volume_m3", "label": "Volume", "eenheid": "m³", "type": "number", "min": 0, "max": 2000, "step": 10, "status": "bron"},
        {"k": "buffer.t_laad_c", "label": "Laadtemperatuur", "eenheid": "°C", "type": "number", "min": 40, "max": 80, "step": 1, "status": "bron"},
        {"k": "buffer.t_retour_c", "label": "Retourtemperatuur", "eenheid": "°C", "type": "number", "min": 20, "max": 50, "step": 1, "status": "bron"},
        {"k": "buffer.p_max_kw", "label": "Max. laad-/ontlaadvermogen", "eenheid": "kW", "type": "number", "min": 50, "max": 3000, "step": 10, "status": "bron", "geavanceerd": True},
        {"k": "buffer.dt_wisselaar_k", "label": "ΔT warmtewisselaar", "eenheid": "K", "type": "number", "min": 0, "max": 10, "step": 0.5, "status": "bron", "geavanceerd": True},
        {"k": "buffer.ua_kw_per_k", "label": "Verlies UA (bij 200 m³)", "eenheid": "kW/K", "type": "number", "min": 0, "max": 1, "step": 0.005, "status": "afgeleid", "geavanceerd": True},
        {"k": "buffer.soc_start", "label": "Vulling bij start", "eenheid": "0–1", "type": "number", "min": 0, "max": 1, "step": 0.05, "status": "aanname", "geavanceerd": True},
    ]},
    {"id": "wp", "titel": "Warmtepompen en COP", "velden": [
        {"k": "warmtepompen.ht.aantal", "label": "HT · aantal", "type": "int", "min": 1, "max": 6, "status": "bron"},
        {"k": "warmtepompen.ht.p_max_kw", "label": "HT · max. vermogen per WP", "eenheid": "kW", "type": "number", "min": 10, "max": 2000, "step": 5, "status": "bron"},
        {"k": "warmtepompen.ht.p_min_kw", "label": "HT · min. last per WP", "eenheid": "kW", "type": "number", "min": 0, "max": 1000, "step": 1, "status": "bron"},
        {"k": "warmtepompen.lt.aantal", "label": "LT · aantal", "type": "int", "min": 1, "max": 6, "status": "bron"},
        {"k": "warmtepompen.lt.p_max_kw", "label": "LT · max. vermogen per WP", "eenheid": "kW", "type": "number", "min": 10, "max": 2000, "step": 5, "status": "bron"},
        {"k": "warmtepompen.lt.p_min_kw", "label": "LT · min. last per WP", "eenheid": "kW", "type": "number", "min": 0, "max": 1000, "step": 1, "status": "bron"},
        {"k": "cop.eta_carnot", "label": "Carnot-rendement η", "type": "number", "min": 0.3, "max": 0.7, "step": 0.01, "status": "afgeleid", "geavanceerd": True, "hulp": "0,55 geeft COP 4,5 bij 45 °C en ≈ 2,95 bij 70 °C."},
        {"k": "cop.t_verdamper_c", "label": "Verdampertemperatuur", "eenheid": "°C", "type": "number", "min": -5, "max": 15, "step": 0.5, "status": "bron", "geavanceerd": True},
    ]},
    {"id": "temperatuur", "titel": "Stooklijn (aanvoertemperatuur)", "velden": [
        {"k": "stooklijn.ht.m10", "label": "HT bij −10 °C buiten", "eenheid": "°C", "type": "number", "min": 30, "max": 80, "step": 1, "status": "aanname"},
        {"k": "stooklijn.ht.p15", "label": "HT bij +15 °C buiten", "eenheid": "°C", "type": "number", "min": 30, "max": 80, "step": 1, "status": "aanname"},
        {"k": "stooklijn.lt.m10", "label": "LT bij −10 °C buiten", "eenheid": "°C", "type": "number", "min": 20, "max": 60, "step": 1, "status": "aanname"},
        {"k": "stooklijn.lt.p15", "label": "LT bij +15 °C buiten", "eenheid": "°C", "type": "number", "min": 20, "max": 60, "step": 1, "status": "aanname"},
    ]},
    {"id": "tarieven", "titel": "Tarieven", "velden": [
        {"k": "tarieven.kwmax_eur_kw_maand", "label": "kW-max-tarief", "eenheid": "€/kW/maand", "type": "number", "min": 0, "max": 20, "step": 0.01, "status": "aanname"},
        {"k": "tarieven.inkoop_winter_eur_kwh", "label": "Energie winter (okt–mrt)", "eenheid": "€/kWh", "type": "number", "min": 0, "max": 1, "step": 0.001, "status": "aanname"},
        {"k": "tarieven.inkoop_zomer_eur_kwh", "label": "Energie zomer (apr–sep)", "eenheid": "€/kWh", "type": "number", "min": 0, "max": 1, "step": 0.001, "status": "aanname"},
        {"k": "tarieven.opslag_piek_eur_kwh", "label": "Opslag piek (werkdagen 07–23 h)", "eenheid": "€/kWh", "type": "number", "min": 0, "max": 0.1, "step": 0.001, "status": "aanname", "geavanceerd": True},
        {"k": "tarieven.opslag_dal_eur_kwh", "label": "Opslag dal", "eenheid": "€/kWh", "type": "number", "min": 0, "max": 0.1, "step": 0.001, "status": "aanname", "geavanceerd": True},
        {"k": "tarieven.energiebelasting_eur_kwh", "label": "Energiebelasting", "eenheid": "€/kWh", "type": "number", "min": 0, "max": 0.2, "step": 0.0001, "status": "aanname", "geavanceerd": True},
    ]},
]
SLEUTELS = {v["k"] for g in GROEPEN for v in g["velden"]}


def _get(cfg, pad):
    d = cfg
    for k in pad.split("."):
        d = d[k]
    return d


def _set(cfg, pad, v):
    delen = pad.split(".")
    d = cfg
    for k in delen[:-1]:
        d = d.setdefault(k, {})
    d[delen[-1]] = v


def waarden_uit_config(cfg):
    """Platte dict {sleutel: waarde} voor het formulier."""
    uit = {}
    for g in GROEPEN:
        for v in g["velden"]:
            k = v["k"]
            if k.startswith("stooklijn."):
                _, net, punt = k.split(".")
                uit[k] = cfg["temperatuur"]["stooklijn"][net][0 if punt == "m10" else 1][1]
            else:
                uit[k] = _get(cfg, k)
    return uit


def config_uit_waarden(basis, waarden):
    cfg = copy.deepcopy(basis)
    for k, v in waarden.items():
        if k not in SLEUTELS:          # vervallen invoer (bv. vraaggestuurd, condensortoggle) negeren
            continue
        if k.startswith("stooklijn."):
            _, net, punt = k.split(".")
            cfg["temperatuur"]["stooklijn"][net][0 if punt == "m10" else 1][1] = float(v)
        else:
            _set(cfg, k, v)
    return cfg
