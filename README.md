# Thermische Flex Simulator

Streamlit-prototype voor WKO, warmtepomp, CV-buffer, piekshaving en dynamische energieprijzen.

De app is opgezet voor een eerste uur-tot-uur verkenning van thermische flexibiliteit:

- buffervolume en temperatuursprong;
- warmtepompvermogen en COP voor direct leveren versus bufferladen;
- nacht laden, prijsoptimalisatie, piekshaving en SOC-doelen;
- scenariovergelijking voor variant 3a, variant 3b en custom instellingen;
- CSV-export van de simulatieresultaten.

## Starten

```bash
python3 -m pip install -r requirements.txt
streamlit run app.py --server.address 0.0.0.0 --server.port 8501
```

Als `streamlit` niet op het PATH staat:

```bash
python3 -m streamlit run app.py --server.address 0.0.0.0 --server.port 8501
```

## Login configureren

De app gebruikt Streamlit secrets voor eenvoudige login. Maak lokaal een secrets-file:

```bash
cp .streamlit/secrets.example.toml .streamlit/secrets.toml
```

Vul daarna in `.streamlit/secrets.toml` de gewenste gebruikersnaam en het wachtwoord in. Dit bestand staat bewust in `.gitignore`.

## CSV input

Upload optioneel een 8760-uurs CSV met kolommen:

- `datetime`
- `heat_demand_kwh`
- `cooling_demand_kwh`
- `price_eur_mwh`
- `outdoor_temp_c`

Zonder CSV gebruikt de app een synthetisch profiel gebaseerd op de projectuitgangspunten.
