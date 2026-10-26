# Simulatie warmtepompen en thermisch buffer · Botanische Tuinen Universiteit Utrecht

Onderzoeksmodel binnen **TVVL Datagedreven energieoptimalisatie in gebouwen, Fase 5**. Het model rekent per uur een referentiejaar door. Het laat zien hoe de HT- en LT-warmtepompen en een thermisch buffer het nieuwe kassencomplex van warmte voorzien. De hoofdvraag is **hoeveel elektrisch vermogen de warmtepompen in een congestievenster kunnen verlagen, en hoe lang**.

## Starten (lokaal)

```bash
cd simulatie
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn webapp.main:app --port 8000      # webapp op http://localhost:8000
.venv/bin/python -m pytest -q                       # tests
```

De webapp heeft drie stappen:
1. **Scenario's:** de invoer vastleggen.
2. **Simulatie:** een scenario kiezen en draaien. Je krijgt KPI's met uitleg, een deep dive op standaarddagen met back-up per dag, en een jaaroverzicht.
3. **Vergelijken:** 2 tot 4 runs naast elkaar zetten. Met **Rapport (PDF)** download je een A4-rapport van de vergelijking.

Vanaf de opdrachtregel draai je een bestaand scenario met `.venv/bin/python run.py --scenario netcongestie-200-m`. Een nieuw scenario maak je met `--naam "…" --set sleutel=waarde`. Scenario en run verschijnen ook in de app.

## Hosten

De repo bevat een `Dockerfile`:

```bash
docker build -t botu-sim .
docker run -p 8000:8000 -v botu-scenarios:/app/simulatie/scenarios -v botu-runs:/app/simulatie/runs botu-sim
```

Zonder Docker start je de app met `uvicorn webapp.main:app --app-dir simulatie --host 0.0.0.0 --port 8000`, vanuit de hoofdmap en met de pakketten uit `simulatie/requirements.txt`.

- **Opslag:** scenario's staan als YAML in `simulatie/scenarios/` en runs als map per run in `simulatie/runs/<id>/`. Er is geen database. Bewaar deze twee mappen persistent, bijvoorbeeld als volume.
- **Toegang:** de app heeft geen eigen login. Iedereen met de URL kan scenario's en runs aanmaken en verwijderen. Zet hem daarom achter een afgeschermde omgeving of een reverse proxy met authenticatie.

## Model

- **Warmtevraag:** de HT- en LT-netten per uur, uit een kasklimaatmodel (20 afdelingen, ingedeeld op temperatuurniveau).
- **Warmtepompen:** 2 × 205 kW HT en 1 × 105 kW LT, met een minimale last. COP = η · T_c/(T_c − T_v) · f(deellast). De aanvoertemperatuur volgt de stooklijn.
- **Buffer:** volledig gelaagd, geladen tot 67 °C met een retour van 35 °C. Alleen de HT-WP's laden het buffer. Het verlies schaalt met V^(2/3).
- **Strategieën:**
  - 1 · referentie: de WP's volgen de vraag.
  - 3 · netcongestie: de WP's verlagen of gaan uit in een instelbaar venster en het buffer levert de warmte. Per dag wordt de verlaging begrensd tot wat in het buffer past.
- **KPI's:**
  - MWhe, SPF en piekvermogen (met het maximum dat de WP's kunnen vragen);
  - de maandpieken in het venster en het aandeel vensterdagen waarop de WP's volledig uit zijn;
  - de back-up met alleen het buffer, voor het hele jaar en per dag;
  - het nachtelijk bijladen, de flexibiliteitsenvelop, de kosten en het warmtetekort.

## Data in deze repo

| Bestand | Herkomst |
|---|---|
| `data/warmte/warmtedata_netten_2001.csv` | Warmtevraag HT/LT per uur (kasklimaatmodel van het projectteam) |
| `data/warmte/condensorwarmte_zlt_2001.csv` | Condensorwarmte van de ZLT-koelmachine naar het LT-net |
| `data/klimaat/klimaatdata_knmi_debilt_samengesteld.csv` | Benadering van het NEN 5060-energiejaar, samengesteld uit open KNMI-uurdata De Bilt (CC BY 4.0, KNMI) |
| `data/prijzen/dayahead_nl_op_simulatiejaar.csv` | Day-ahead NL 2024/2025 (Bundesnetzagentur / SMARD via energy-charts.info, CC BY 4.0) |
| `simulatie/scenarios/`, `simulatie/runs/` | Referentie en netcongestie met 100, 200 en 300 m³, doorgerekend met de data hierboven en voorbeeldtarieven |

Het logo en de favicon in `simulatie/webapp/static/img/` zijn beeldmerken van de Universiteit Utrecht. Ze vallen onder de merkregels van de UU en vallen niet onder een open licentie.

De officiële NEN 5060-reeks, de campusdata en de contracttarieven zitten **niet** in deze repo. De tarieven in `simulatie/config/basis.yaml` en in de scenario's zijn openbare voorbeeldwaarden. De uitkomsten wijken daardoor iets af van de interne projectresultaten.
