# Simulatie warmtepompen en thermisch buffer · Botanische Tuinen Universiteit Utrecht

Onderzoeksmodel binnen **TVVL Datagedreven energieoptimalisatie in gebouwen, Fase 5**. Het model simuleert per uur, over een referentiejaar, hoe de HT- en LT-warmtepompen en een thermisch buffer (200 m³) het nieuwe kassencomplex van warmte voorzien. De hoofdvraag is **hoeveel elektrisch vermogen de warmtepompen in een congestievenster kunnen verlagen, en hoe lang**.

## Starten

```bash
cd simulatie
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn webapp.main:app --port 8000      # webapp op http://localhost:8000
.venv/bin/python -m pytest -q                       # tests
```

De webapp heeft drie stappen:
1. **Scenario's:** invoer vastleggen.
2. **Simulatie:** KPI's, deep dive op standaarddagen en een jaaroverzicht.
3. **Vergelijken:** runs naast elkaar.

Vanaf de opdrachtregel: `.venv/bin/python run.py --strategie congestie --naam test`.

## Model

- **Warmtevraag:** HT- en LT-net per uur, uit een kasklimaatmodel (20 afdelingen, ingedeeld op temperatuurniveau).
- **Warmtepompen:** 2 × 205 kW HT en 1 × 105 kW LT, met minimale last. COP = η · T_c/(T_c − T_v) · f(deellast).
- **Buffer:** volledig gelaagd (laden tot 67 °C, retour 35 °C). Wordt alleen door de HT-WP's geladen; het verlies schaalt met V^(2/3).
- **Strategieën:**
  - 1 · referentie: WP's volgen de vraag;
  - 3 · netcongestie: WP's verlagen of gaan uit in een instelbaar venster, het buffer levert, en de verlaging wordt per dag begrensd tot wat in het buffer past.
- **KPI's:** MWhe, SPF, (maand)pieken in het venster, pendeluren, back-up (alleen buffer), flexibiliteitsenvelop en kosten.

## Data in deze repo

| Bestand | Herkomst |
|---|---|
| `data/warmte/warmtedata_netten_2001.csv` | Warmtevraag HT/LT per uur (kasklimaatmodel van het projectteam) |
| `data/warmte/condensorwarmte_zlt_2001.csv` | Condensorwarmte van de ZLT-koelmachine naar het LT-net |
| `data/klimaat/klimaatdata_knmi_debilt_samengesteld.csv` | Benadering van het NEN 5060-energiejaar, samengesteld uit open KNMI-uurdata De Bilt (CC BY 4.0, KNMI) |
| `data/prijzen/dayahead_nl_op_simulatiejaar.csv` | Day-ahead NL 2024/2025 (Bundesnetzagentur / SMARD via energy-charts.info, CC BY 4.0) |

De officiële NEN 5060-reeks, de campusdata en de contracttarieven zijn **niet** opgenomen. De tarieven in `simulatie/config/basis.yaml` zijn openbare voorbeeldwaarden.
