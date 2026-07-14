from __future__ import annotations

import hmac
from dataclasses import dataclass

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st


st.set_page_config(
    page_title="Thermische Flex Simulator",
    page_icon="TH",
    layout="wide",
    initial_sidebar_state="expanded",
)


PROJECT_DEFAULTS = {
    "Warmtevraag jaar": 1877.0,
    "Warmtepiek": 592.0,
    "Koudevraag jaar": 493.0,
    "Koudepiek": 287.0,
}


@dataclass
class SimulationConfig:
    buffer_volume_m3: float
    buffer_hot_c: float
    buffer_return_c: float
    buffer_min_pct: float
    initial_soc_pct: float
    daily_loss_pct: float
    wp_thermal_max_kw: float
    cop_direct: float
    cop_buffer: float
    normal_electric_cap_kw: float
    peak_electric_cap_kw: float
    strategy: str
    low_price_quantile: float
    high_price_quantile: float
    night_start: int
    night_end: int
    morning_start: int
    morning_end: int
    evening_start: int
    evening_end: int
    target_soc_pct: float


def check_password() -> bool:
    if st.session_state.get("authenticated"):
        return True

    st.title("Thermische Flex Simulator")
    st.caption("Log in om scenario's voor WKO, warmtepomp en CV-buffer te simuleren.")

    with st.form("login_form"):
        username = st.text_input("Gebruikersnaam")
        password = st.text_input("Wachtwoord", type="password")
        submitted = st.form_submit_button("Inloggen")

    if submitted:
        expected_user = st.secrets.get("auth", {}).get("username", "")
        expected_password = st.secrets.get("auth", {}).get("password", "")
        valid_user = hmac.compare_digest(username, expected_user)
        valid_password = hmac.compare_digest(password, expected_password)
        if valid_user and valid_password:
            st.session_state["authenticated"] = True
            st.rerun()
        st.error("Ongeldige gebruikersnaam of wachtwoord.")

    return False


def buffer_capacity_kwh(volume_m3: float, hot_c: float, return_c: float) -> float:
    return max(0.0, volume_m3 * 1.163 * max(0.0, hot_c - return_c))


def make_synthetic_profile(seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2026-01-01 00:00", periods=8760, freq="h")
    hour = idx.hour.to_numpy()
    day = idx.dayofyear.to_numpy()

    seasonal = np.cos(2 * np.pi * (day - 15) / 365.0)
    outdoor_temp = 10 + 10 * -seasonal + 3 * np.sin(2 * np.pi * (hour - 6) / 24.0)
    outdoor_temp += rng.normal(0, 1.2, len(idx))

    winter_shape = np.clip((17 - outdoor_temp) / 25, 0, None) ** 1.55
    morning_bump = 1 + 0.28 * ((hour >= 6) & (hour <= 10))
    heat_kw = winter_shape * morning_bump
    heat_kw = heat_kw / heat_kw.max() * PROJECT_DEFAULTS["Warmtepiek"]
    heat_kw *= PROJECT_DEFAULTS["Warmtevraag jaar"] * 1000 / heat_kw.sum()
    heat_kw = np.clip(heat_kw, 0, PROJECT_DEFAULTS["Warmtepiek"])

    cooling_shape = np.clip((outdoor_temp - 15) / 15, 0, None) ** 1.3
    solar_bump = 1 + 0.35 * ((hour >= 11) & (hour <= 17))
    cooling_kw = cooling_shape * solar_bump
    if cooling_kw.max() > 0:
        cooling_kw = cooling_kw / cooling_kw.max() * PROJECT_DEFAULTS["Koudepiek"]
        cooling_kw *= PROJECT_DEFAULTS["Koudevraag jaar"] * 1000 / max(cooling_kw.sum(), 1)
    cooling_kw = np.clip(cooling_kw, 0, PROJECT_DEFAULTS["Koudepiek"])

    price = 75.0 + 18.0 * ((hour >= 7) & (hour <= 10)) + 28.0 * ((hour >= 17) & (hour <= 21))
    price = price.astype(float)
    price -= 20.0 * ((hour >= 0) & (hour <= 5))
    price += 12 * np.sin(2 * np.pi * (day - 30) / 365.0)
    price += rng.normal(0, 13, len(idx))
    price = np.clip(price, -20, 220)

    return pd.DataFrame(
        {
            "datetime": idx,
            "outdoor_temp_c": outdoor_temp,
            "heat_demand_kwh": heat_kw,
            "cooling_demand_kwh": cooling_kw,
            "price_eur_mwh": price,
        }
    )


def normalize_uploaded_profile(uploaded_file) -> pd.DataFrame:
    df = pd.read_csv(uploaded_file)
    lower = {c.lower().strip(): c for c in df.columns}

    datetime_col = lower.get("datetime") or lower.get("timestamp") or lower.get("time")
    heat_col = lower.get("heat_demand_kwh") or lower.get("warmtevraag_kwh") or lower.get("heat_kw")
    cooling_col = lower.get("cooling_demand_kwh") or lower.get("koudevraag_kwh") or lower.get("cooling_kw")
    price_col = lower.get("price_eur_mwh") or lower.get("prijs_eur_mwh") or lower.get("price")

    if heat_col is None:
        raise ValueError("CSV mist een kolom voor warmtevraag, bijvoorbeeld heat_demand_kwh.")

    out = pd.DataFrame()
    out["datetime"] = pd.to_datetime(df[datetime_col]) if datetime_col else pd.date_range("2026-01-01", periods=len(df), freq="h")
    out["heat_demand_kwh"] = pd.to_numeric(df[heat_col], errors="coerce").fillna(0)
    out["cooling_demand_kwh"] = pd.to_numeric(df[cooling_col], errors="coerce").fillna(0) if cooling_col else 0.0
    out["price_eur_mwh"] = pd.to_numeric(df[price_col], errors="coerce").fillna(75) if price_col else 75.0
    out["outdoor_temp_c"] = pd.to_numeric(df[lower["outdoor_temp_c"]], errors="coerce").fillna(np.nan) if "outdoor_temp_c" in lower else np.nan
    return out.sort_values("datetime").reset_index(drop=True)


def is_between_hour(hour: int, start: int, end: int) -> bool:
    if start <= end:
        return start <= hour < end
    return hour >= start or hour < end


def simulate(df: pd.DataFrame, cfg: SimulationConfig) -> pd.DataFrame:
    capacity = buffer_capacity_kwh(cfg.buffer_volume_m3, cfg.buffer_hot_c, cfg.buffer_return_c)
    min_soc = capacity * cfg.buffer_min_pct / 100
    target_soc = capacity * cfg.target_soc_pct / 100
    soc = capacity * cfg.initial_soc_pct / 100
    daily_loss = cfg.daily_loss_pct / 100
    low_price = df["price_eur_mwh"].quantile(cfg.low_price_quantile / 100)
    high_price = df["price_eur_mwh"].quantile(cfg.high_price_quantile / 100)

    rows = []
    for item in df.itertuples(index=False):
        ts = item.datetime
        hour = int(pd.Timestamp(ts).hour)
        demand = float(item.heat_demand_kwh)
        price = float(item.price_eur_mwh)

        morning_peak = is_between_hour(hour, cfg.morning_start, cfg.morning_end)
        evening_peak = is_between_hour(hour, cfg.evening_start, cfg.evening_end)
        night_charge = is_between_hour(hour, cfg.night_start, cfg.night_end)
        high_price_hour = price >= high_price
        low_price_hour = price <= low_price

        shave_hour = morning_peak or evening_peak or high_price_hour
        electric_cap = cfg.peak_electric_cap_kw if shave_hour else cfg.normal_electric_cap_kw
        direct_limit = min(cfg.wp_thermal_max_kw, electric_cap * cfg.cop_direct)

        direct_heat = min(demand, direct_limit)
        electric_direct = direct_heat / cfg.cop_direct if cfg.cop_direct > 0 else 0
        remaining = demand - direct_heat
        discharge = min(max(0.0, soc - min_soc), remaining)
        unmet = max(0.0, remaining - discharge)
        soc -= discharge

        charge_allowed = False
        if cfg.strategy == "Nachtladen":
            charge_allowed = night_charge
        elif cfg.strategy == "Prijsoptimalisatie":
            charge_allowed = low_price_hour
        elif cfg.strategy == "Piekshaving + prijs":
            charge_allowed = night_charge or low_price_hour or (soc < target_soc and not shave_hour)
        else:
            charge_allowed = soc < target_soc and not shave_hour

        available_electric = max(0.0, electric_cap - electric_direct)
        charge_limit = min(cfg.wp_thermal_max_kw, available_electric * cfg.cop_buffer)
        charge = 0.0
        if charge_allowed and capacity > 0:
            charge_target = capacity if cfg.strategy in {"Nachtladen", "Prijsoptimalisatie"} else target_soc
            charge = min(max(0.0, charge_target - soc), charge_limit)
            soc += charge

        loss = min(soc, capacity * daily_loss / 24)
        soc -= loss
        electric_charge = charge / cfg.cop_buffer if cfg.cop_buffer > 0 else 0
        electric_total = electric_direct + electric_charge

        rows.append(
            {
                "datetime": ts,
                "heat_demand_kwh": demand,
                "cooling_demand_kwh": float(item.cooling_demand_kwh),
                "price_eur_mwh": price,
                "outdoor_temp_c": float(item.outdoor_temp_c) if not pd.isna(item.outdoor_temp_c) else np.nan,
                "direct_heat_kwh": direct_heat,
                "buffer_charge_kwh": charge,
                "buffer_discharge_kwh": discharge,
                "buffer_loss_kwh": loss,
                "buffer_soc_kwh": soc,
                "buffer_soc_pct": 100 * soc / capacity if capacity > 0 else 0,
                "electricity_kwh": electric_total,
                "electricity_direct_kwh": electric_direct,
                "electricity_charge_kwh": electric_charge,
                "unmet_heat_kwh": unmet,
                "is_shave_hour": shave_hour,
                "is_night_charge": night_charge,
                "electric_cap_kw": electric_cap,
            }
        )

    result = pd.DataFrame(rows)
    result["cost_eur"] = result["electricity_kwh"] * result["price_eur_mwh"] / 1000
    result["electric_power_kw"] = result["electricity_kwh"]
    return result


def baseline(df: pd.DataFrame, cop: float, wp_thermal_max_kw: float) -> pd.DataFrame:
    out = df.copy()
    delivered = np.minimum(out["heat_demand_kwh"], wp_thermal_max_kw)
    out["electricity_kwh"] = delivered / cop
    out["electric_power_kw"] = out["electricity_kwh"]
    out["unmet_heat_kwh"] = np.maximum(0, out["heat_demand_kwh"] - wp_thermal_max_kw)
    out["cost_eur"] = out["electricity_kwh"] * out["price_eur_mwh"] / 1000
    return out


def metric(label: str, value: str, delta: str | None = None):
    st.metric(label, value, delta=delta)


def plot_timeseries(result: pd.DataFrame, start, days: int) -> go.Figure:
    end = pd.Timestamp(start) + pd.Timedelta(days=days)
    view = result[(result["datetime"] >= pd.Timestamp(start)) & (result["datetime"] < end)]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=view["datetime"], y=view["heat_demand_kwh"], name="Warmtevraag kWhth/h", line=dict(color="#3949ab")))
    fig.add_trace(go.Scatter(x=view["datetime"], y=view["direct_heat_kwh"], name="Direct WP", line=dict(color="#00897b")))
    fig.add_trace(go.Scatter(x=view["datetime"], y=view["buffer_charge_kwh"], name="Buffer laden", line=dict(color="#f9a825")))
    fig.add_trace(go.Scatter(x=view["datetime"], y=view["buffer_discharge_kwh"], name="Buffer ontladen", line=dict(color="#c62828")))
    fig.update_layout(height=360, margin=dict(l=20, r=20, t=20, b=20), legend=dict(orientation="h"))
    return fig


def plot_soc(result: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=result["datetime"], y=result["buffer_soc_pct"], name="Buffer SOC %", line=dict(color="#6d4c41", width=1)))
    fig.update_layout(height=260, margin=dict(l=20, r=20, t=20, b=20), yaxis_title="%", showlegend=False)
    return fig


def plot_price_power(result: pd.DataFrame, base: pd.DataFrame, start, days: int) -> go.Figure:
    end = pd.Timestamp(start) + pd.Timedelta(days=days)
    view = result[(result["datetime"] >= pd.Timestamp(start)) & (result["datetime"] < end)]
    base_view = base[(base["datetime"] >= pd.Timestamp(start)) & (base["datetime"] < end)]
    fig = go.Figure()
    fig.add_trace(go.Bar(x=view["datetime"], y=base_view["electric_power_kw"], name="Referentie kWe", marker_color="#b0bec5"))
    fig.add_trace(go.Bar(x=view["datetime"], y=view["electric_power_kw"], name="Flex kWe", marker_color="#1565c0"))
    fig.add_trace(go.Scatter(x=view["datetime"], y=view["price_eur_mwh"], name="Prijs €/MWh", yaxis="y2", line=dict(color="#ef6c00")))
    fig.update_layout(
        height=360,
        margin=dict(l=20, r=20, t=20, b=20),
        barmode="overlay",
        legend=dict(orientation="h"),
        yaxis=dict(title="kWe"),
        yaxis2=dict(title="€/MWh", overlaying="y", side="right"),
    )
    return fig


def scenario_table(df: pd.DataFrame, base_cfg: SimulationConfig) -> pd.DataFrame:
    scenarios = [
        ("3a klein", 157, 497, 240, 110),
        ("3b groot", 402, 763, 280, 120),
        ("custom", base_cfg.buffer_volume_m3, base_cfg.wp_thermal_max_kw, base_cfg.normal_electric_cap_kw, base_cfg.peak_electric_cap_kw),
    ]
    rows = []
    for name, volume, wp_max, normal_cap, peak_cap in scenarios:
        cfg = SimulationConfig(**{**base_cfg.__dict__, "buffer_volume_m3": volume, "wp_thermal_max_kw": wp_max, "normal_electric_cap_kw": normal_cap, "peak_electric_cap_kw": peak_cap})
        flex = simulate(df, cfg)
        base = baseline(df, cfg.cop_direct, cfg.wp_thermal_max_kw)
        rows.append(
            {
                "Scenario": name,
                "Buffer m3": volume,
                "Buffer kWhth": round(buffer_capacity_kwh(volume, cfg.buffer_hot_c, cfg.buffer_return_c)),
                "WP max kWth": wp_max,
                "Max kWe flex": round(flex["electric_power_kw"].max(), 1),
                "Max kWe ref": round(base["electric_power_kw"].max(), 1),
                "Piekreductie kWe": round(base["electric_power_kw"].max() - flex["electric_power_kw"].max(), 1),
                "Kosten flex €": round(flex["cost_eur"].sum()),
                "Kosten ref €": round(base["cost_eur"].sum()),
                "Ongeleverd MWhth": round(flex["unmet_heat_kwh"].sum() / 1000, 2),
            }
        )
    return pd.DataFrame(rows)


if not check_password():
    st.stop()

st.markdown(
    """
    <style>
    .block-container {padding-top: 1.5rem;}
    [data-testid="stMetric"] {background: #f7f7f4; border: 1px solid #e2e0d8; padding: 12px; border-radius: 8px;}
    h1, h2, h3 {letter-spacing: 0;}
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("Thermische Flex Simulator")
st.caption("Uur-tot-uur scenarioverkenning voor WKO, warmtepomp, CV-buffer, piekshaving en dynamische prijzen.")

with st.sidebar:
    st.header("Profiel")
    uploaded = st.file_uploader("Upload 8760 CSV", type=["csv"])
    if uploaded:
        try:
            profile = normalize_uploaded_profile(uploaded)
            st.success("CSV geladen.")
        except Exception as exc:
            st.error(str(exc))
            profile = make_synthetic_profile()
    else:
        profile = make_synthetic_profile()

    st.header("Installatie")
    preset = st.selectbox("Preset", ["Variant 3a - 157 m3", "Variant 3b - 402 m3", "Custom"])
    if preset.startswith("Variant 3a"):
        default_volume, default_wp, default_normal, default_peak = 157.0, 497.0, 240.0, 110.0
    elif preset.startswith("Variant 3b"):
        default_volume, default_wp, default_normal, default_peak = 402.0, 763.0, 280.0, 120.0
    else:
        default_volume, default_wp, default_normal, default_peak = 250.0, 600.0, 260.0, 120.0

    volume = st.slider("Buffervolume m3", 50.0, 650.0, default_volume, 1.0)
    hot_c = st.number_input("Buffer hoog °C", 50.0, 90.0, 70.0, 1.0)
    return_c = st.number_input("Gemiddelde retour °C", 25.0, 65.0, 50.0, 1.0)
    wp_max = st.slider("WP maximaal kWth", 100.0, 900.0, default_wp, 1.0)
    cop_direct = st.number_input("COP direct leveren", 1.5, 6.0, 3.23, 0.05)
    cop_buffer = st.number_input("COP buffer laden", 1.5, 6.0, 2.91, 0.05)

    st.header("Flexstrategie")
    strategy = st.selectbox("Regelstrategie", ["Piekshaving + prijs", "Nachtladen", "Prijsoptimalisatie", "SOC-doel"])
    normal_cap = st.slider("Elektrische cap normaal kWe", 50.0, 450.0, default_normal, 1.0)
    peak_cap = st.slider("Elektrische cap piekuren kWe", 0.0, 300.0, default_peak, 1.0)
    min_soc = st.slider("Minimale reserve SOC %", 0.0, 60.0, 15.0, 1.0)
    initial_soc = st.slider("Start SOC %", 0.0, 100.0, 50.0, 1.0)
    target_soc = st.slider("Doel SOC %", 20.0, 100.0, 85.0, 1.0)
    daily_loss = st.slider("Dagelijks bufferverlies %", 0.0, 3.0, 0.35, 0.05)
    low_q = st.slider("Lage-prijs grens percentiel", 1, 50, 25, 1)
    high_q = st.slider("Hoge-prijs grens percentiel", 50, 99, 75, 1)

    st.header("Tijdvensters")
    night_start = st.number_input("Nachtladen start uur", 0, 23, 0)
    night_end = st.number_input("Nachtladen eind uur", 1, 24, 6)
    morning_start = st.number_input("Ochtendpiek start uur", 0, 23, 7)
    morning_end = st.number_input("Ochtendpiek eind uur", 1, 24, 10)
    evening_start = st.number_input("Avondpiek start uur", 0, 23, 16)
    evening_end = st.number_input("Avondpiek eind uur", 1, 24, 20)

cfg = SimulationConfig(
    buffer_volume_m3=volume,
    buffer_hot_c=hot_c,
    buffer_return_c=return_c,
    buffer_min_pct=min_soc,
    initial_soc_pct=initial_soc,
    daily_loss_pct=daily_loss,
    wp_thermal_max_kw=wp_max,
    cop_direct=cop_direct,
    cop_buffer=cop_buffer,
    normal_electric_cap_kw=normal_cap,
    peak_electric_cap_kw=peak_cap,
    strategy=strategy,
    low_price_quantile=low_q,
    high_price_quantile=high_q,
    night_start=night_start,
    night_end=night_end,
    morning_start=morning_start,
    morning_end=morning_end,
    evening_start=evening_start,
    evening_end=evening_end,
    target_soc_pct=target_soc,
)

result = simulate(profile, cfg)
base = baseline(profile, cfg.cop_direct, cfg.wp_thermal_max_kw)
capacity = buffer_capacity_kwh(cfg.buffer_volume_m3, cfg.buffer_hot_c, cfg.buffer_return_c)

total_cost = result["cost_eur"].sum()
base_cost = base["cost_eur"].sum()
peak_reduction = base["electric_power_kw"].max() - result["electric_power_kw"].max()
shifted = result["buffer_discharge_kwh"].sum()

col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    metric("Buffercapaciteit", f"{capacity:,.0f} kWhth".replace(",", "."))
with col2:
    metric("Max elektrisch", f"{result['electric_power_kw'].max():.0f} kWe", f"{-peak_reduction:.0f} kWe t.o.v. ref")
with col3:
    metric("Kosten flex", f"€ {total_cost:,.0f}".replace(",", "."), f"€ {base_cost - total_cost:,.0f}".replace(",", "."))
with col4:
    metric("Ontladen uit buffer", f"{shifted / 1000:.1f} MWhth")
with col5:
    metric("Ongeleverd", f"{result['unmet_heat_kwh'].sum() / 1000:.2f} MWhth")

tabs = st.tabs(["Simulatie", "Profiel", "Scenario's", "Data"])

with tabs[0]:
    start = st.date_input("Startdatum detailweergave", value=pd.Timestamp("2026-01-15"))
    days = st.slider("Aantal dagen", 1, 21, 7)
    st.plotly_chart(plot_price_power(result, base, start, days), use_container_width=True)
    st.plotly_chart(plot_timeseries(result, start, days), use_container_width=True)
    st.plotly_chart(plot_soc(result), use_container_width=True)

with tabs[1]:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Warmtevraag", f"{profile['heat_demand_kwh'].sum() / 1000:.0f} MWhth")
    c2.metric("Warmtepiek", f"{profile['heat_demand_kwh'].max():.0f} kWth")
    c3.metric("Koudevraag", f"{profile['cooling_demand_kwh'].sum() / 1000:.0f} MWhth")
    c4.metric("Koudepiek", f"{profile['cooling_demand_kwh'].max():.0f} kWth")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=profile["datetime"], y=profile["heat_demand_kwh"], name="Warmte", line=dict(color="#c62828", width=1)))
    fig.add_trace(go.Scatter(x=profile["datetime"], y=profile["cooling_demand_kwh"], name="Koude", line=dict(color="#1565c0", width=1)))
    fig.add_trace(go.Scatter(x=profile["datetime"], y=profile["price_eur_mwh"], name="Prijs", yaxis="y2", line=dict(color="#ef6c00", width=1)))
    fig.update_layout(height=420, margin=dict(l=20, r=20, t=20, b=20), yaxis_title="kWh/h", yaxis2=dict(title="€/MWh", overlaying="y", side="right"), legend=dict(orientation="h"))
    st.plotly_chart(fig, use_container_width=True)

with tabs[2]:
    st.dataframe(scenario_table(profile, cfg), width="stretch", hide_index=True)
    st.caption("Scenario's gebruiken dezelfde prijsreeks, COP's, tijdvensters en reserve-instellingen als de huidige sidebar.")

with tabs[3]:
    st.download_button(
        "Download simulatieresultaat CSV",
        data=result.to_csv(index=False).encode("utf-8"),
        file_name="thermische_flex_simulatie.csv",
        mime="text/csv",
    )
    st.dataframe(result.head(500), width="stretch", hide_index=True)
