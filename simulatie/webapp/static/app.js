/* Webapp simulatie BoTu UU — drie schermen: scenario's → simulatie → vergelijken. */
const K = {  // grafiekkleuren: UU-secundair, alleen in grafieken
  ht: "#C00A35", lt: "#F3965E", buffer: "#24A793", soc: "#5287C6", totaal: "#001240", temp: "#5287C6",
  venster: "rgba(255,205,0,0.22)", runs: ["#001240", "#C00A35", "#24A793", "#F3965E"],
};
const MND = ["jan", "feb", "mrt", "apr", "mei", "jun", "jul", "aug", "sep", "okt", "nov", "dec"];
const S = { geavanceerd: false, schema: null, scenarios: [], runs: [], gekozenScenario: null, gekozenRun: null, vergelijk: [], dag: null };
const $ = (sel, el = document) => el.querySelector(sel);
const app = $("#app");
const nl = (v, d = 0) => (v === null || v === undefined || Number.isNaN(v)) ? "–" : Number(v).toLocaleString("nl-NL", { minimumFractionDigits: d, maximumFractionDigits: d });
const esc = (t) => String(t ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

async function api(pad, opties = {}) {
  const r = await fetch(pad, { headers: { "Content-Type": "application/json" }, ...opties });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json();
}
const PL = { displaylogo: false, responsive: true, modeBarButtonsToRemove: ["lasso2d", "select2d"] };
const layoutBasis = (extra = {}) => ({
  font: { family: "Open Sans, Arial", size: 12, color: "#1A1A1A" }, paper_bgcolor: "#fff", plot_bgcolor: "#fff",
  margin: { l: 60, r: 20, t: 30, b: 40 }, hovermode: "x unified", legend: { orientation: "h", y: -0.12 }, ...extra,
});

/* ------------------------------------------------------------------ router */
async function route() {
  const stap = (location.hash.replace("#/", "") || "scenarios").split("?")[0];
  document.querySelectorAll(".stappen a").forEach((a) => a.classList.toggle("actief", a.dataset.stap === stap));
  if (!S.schema) S.schema = await api("/api/schema");
  if (stap === "simulatie") return schermSimulatie();
  if (stap === "vergelijken") return schermVergelijken();
  return schermScenarios();
}
window.addEventListener("hashchange", route);

/* ================================================================== 1 · SCENARIO'S */
async function schermScenarios() {
  S.scenarios = await api("/api/scenarios");
  const huidig = S.gekozenScenario && S.scenarios.find((s) => s.id === S.gekozenScenario)
    || { id: null, naam: "Nieuw scenario", omschrijving: "", waarden: { ...S.schema.basis } };
  const opties = [`<option value="">＋ Nieuw scenario (basisinstellingen)</option>`,
    ...S.scenarios.map((s) => `<option value="${s.id}" ${s.id === huidig.id ? "selected" : ""}>${esc(s.naam)}</option>`)].join("");
  app.innerHTML = `
    <h2>Scenario's</h2>
    <p class="sub">Kies een opgeslagen scenario of begin een nieuw scenario. Pas de invoer aan, sla op en ga naar stap 2.</p>
    <div class="kaart geel">
      <div class="scenariobalk">
        <div><label>Scenario</label><select class="tekstveld" id="kiesSc">${opties}</select></div>
        <div><label>Naam</label><input class="tekstveld" id="naam" value="${esc(huidig.naam)}"></div>
        <div class="breed"><label>Omschrijving</label><input class="tekstveld" id="omschr" value="${esc(huidig.omschrijving)}" placeholder="bv. buffer 300 m³, WP's uit in venster"></div>
      </div>
      <div class="rij" style="margin-top:14px">
        <button class="knop primair" id="opslaan">${huidig.id ? "Opslaan" : "Opslaan als nieuw scenario"}</button>
        ${huidig.id ? '<button class="knop" id="kopie">Opslaan als kopie</button><button class="knop gevaar" id="weg">Verwijderen</button>' : ""}
        <span style="flex:1"></span>
        <label class="rij" style="gap:6px;cursor:pointer"><input type="checkbox" id="adv" ${S.geavanceerd ? "checked" : ""}> Geavanceerde parameters tonen</label>
        <button class="knop zwart" id="naarSim">Opslaan en naar simulatie →</button>
        <span id="bewaard" class="eenheid"></span>
      </div>
    </div>
    <div class="groepen sectie" id="formulier"></div>`;
  $("#kiesSc").onchange = (e) => { S.gekozenScenario = e.target.value || null; schermScenarios(); };
  $("#adv").onchange = (e) => { S.geavanceerd = e.target.checked; teken(); };
  const w = { ...S.schema.basis, ...huidig.waarden };
  const teken = () => bouwFormulier($("#formulier"), w);
  teken();
  const bewaar = async (alsKopie) => {
    const body = JSON.stringify({ naam: $("#naam").value || "scenario", omschrijving: $("#omschr").value, waarden: w });
    const doc = (huidig.id && !alsKopie)
      ? await api(`/api/scenarios/${huidig.id}`, { method: "PUT", body })
      : await api("/api/scenarios", { method: "POST", body });
    S.gekozenScenario = doc.id;
    return doc;
  };
  $("#opslaan").onclick = async () => { await bewaar(false); await schermScenarios(); $("#bewaard").textContent = "✓ opgeslagen"; };
  if ($("#kopie")) $("#kopie").onclick = async () => { $("#naam").value += " (kopie)"; await bewaar(true); schermScenarios(); };
  if ($("#weg")) $("#weg").onclick = async () => {
    if (!confirm(`Scenario '${huidig.naam}' verwijderen?`)) return;
    await api(`/api/scenarios/${huidig.id}`, { method: "DELETE" });
    S.gekozenScenario = null; schermScenarios();
  };
  $("#naarSim").onclick = async () => { await bewaar(false); location.hash = "#/simulatie"; };
}

function maandenNaarBereik(lijst) {
  if (!lijst.length) return [11, 3];
  const set = new Set(lijst);
  const start = lijst.find((m) => !set.has(((m + 10) % 12) + 1)) ?? lijst[0];
  const eind = lijst.find((m) => !set.has((m % 12) + 1)) ?? lijst[lijst.length - 1];
  return [start, eind];
}
function bereikNaarMaanden(start, eind) {
  const uit = [];
  let m = start;
  for (let i = 0; i < 12; i++) { uit.push(m); if (m === eind) break; m = (m % 12) + 1; }
  return uit.sort((a, b) => a - b);
}

function bouwFormulier(doel, w) {
  const teken = () => {
    doel.innerHTML = "";
    S.schema.groepen.forEach((g) => {
      const velden = g.velden.filter((v) => (!v.alleen || v.alleen === w["strategie.naam"]) && (!v.verberg_als || !w[v.verberg_als]) && (!v.geavanceerd || S.geavanceerd));
      if (!velden.length) return;
      const kaart = document.createElement("div");
      kaart.className = "kaart";
      kaart.innerHTML = `<h3>${esc(g.titel)}</h3>`;
      velden.forEach((v) => {
        const rij = document.createElement("div");
        rij.className = "veld" + (v.geavanceerd ? " geavanceerd" : "");
        const lab = `<label>${esc(v.label)}<span class="status ${v.status}">${v.status}</span>${v.hulp ? `<span class="hulp">${esc(v.hulp)}</span>` : ""}</label>`;
        if (v.type === "maandbereik") {
          const [a, b] = maandenNaarBereik(w[v.k]);
          const sel = (x, id) => `<select data-i="${id}">${MND.map((m, i) => `<option value="${i + 1}" ${i + 1 === x ? "selected" : ""}>${m}</option>`).join("")}</select>`;
          rij.innerHTML = lab + `<div class="invoer-eenheid">${sel(a, 0)}<span class="eenheid">t/m</span>${sel(b, 1)}</div>`;
          rij.querySelectorAll("select").forEach((s) => s.onchange = () => {
            const [x, y] = [...rij.querySelectorAll("select")].map((e) => +e.value);
            w[v.k] = bereikNaarMaanden(x, y);
          });
        } else if (v.type === "uren") {
          const sel = (x, id) => `<select data-i="${id}">${Array.from({ length: 25 }, (_, h) => `<option value="${h}" ${h === x ? "selected" : ""}>${String(h).padStart(2, "0")}:00</option>`).join("")}</select>`;
          rij.innerHTML = lab + `<div class="invoer-eenheid">${sel(w[v.k][0], 0)}<span class="eenheid">–</span>${sel(w[v.k][1], 1)}</div>`;
          rij.querySelectorAll("select").forEach((s) => s.onchange = () => { w[v.k] = [...rij.querySelectorAll("select")].map((e) => +e.value); });
        } else if (v.type === "bool") {
          rij.innerHTML = lab + `<div><input type="checkbox" class="schakel" ${w[v.k] ? "checked" : ""}></div>`;
          rij.querySelector("input").onchange = (e) => { w[v.k] = e.target.checked; teken(); };
        } else if (v.type === "select") {
          rij.innerHTML = lab + `<select>${v.opties.map(([k, t]) => `<option value="${k}" ${w[v.k] === k ? "selected" : ""}>${esc(t)}</option>`).join("")}</select>`;
          rij.querySelector("select").onchange = (e) => { w[v.k] = e.target.value; teken(); };
        } else {
          rij.innerHTML = lab + `<div class="invoer-eenheid"><input type="number" min="${v.min}" max="${v.max}" step="${v.step || 1}" value="${w[v.k]}">${v.eenheid ? `<span class="eenheid">${esc(v.eenheid)}</span>` : ""}</div>`;
          rij.querySelector("input").oninput = (e) => { w[v.k] = v.type === "int" ? parseInt(e.target.value) : parseFloat(e.target.value); afgeleid(); };
        }
        kaart.appendChild(rij);
      });
      if (g.id === "buffer") { const a = document.createElement("div"); a.className = "afgeleid-info"; a.id = "opslag"; kaart.appendChild(a); }
      if (g.id === "wp") { const a = document.createElement("div"); a.className = "afgeleid-info"; a.id = "copinfo"; kaart.appendChild(a); }
      doel.appendChild(kaart);
    });
    afgeleid();
  };
  const afgeleid = () => {
    const e = w["buffer.volume_m3"] * 1.163 * (w["buffer.t_laad_c"] - w["buffer.t_retour_c"]) / 1000;
    if ($("#opslag")) $("#opslag").innerHTML = `Opslagcapaciteit ≈ <b>${nl(e, 1)} MWh</b> · ≈ ${nl(e / 0.592, 0)} h piekvraag (592 kW)`;
    const cop = (t) => w["cop.eta_carnot"] * (t + 273.15) / (t - w["cop.t_verdamper_c"]);
    const tl = w["buffer.t_laad_c"] + w["buffer.dt_wisselaar_k"];
    if ($("#copinfo")) $("#copinfo").innerHTML = `COP (nominaal): 45 °C → <b>${nl(cop(45), 2)}</b> · 55 °C → <b>${nl(cop(55), 2)}</b> · 65 °C → <b>${nl(cop(65), 2)}</b> · buffer laden ${nl(tl, 0)} °C → <b>${nl(cop(tl), 2)}</b>`;
  };
  teken();
}

/* ================================================================== 2 · SIMULATIE */
async function schermSimulatie() {
  [S.scenarios, S.runs] = await Promise.all([api("/api/scenarios"), api("/api/runs")]);
  const opties = S.scenarios.map((s) => `<option value="${s.id}" ${s.id === S.gekozenScenario ? "selected" : ""}>${esc(s.naam)}</option>`).join("");
  app.innerHTML = `
    <h2>Simulatie</h2>
    <p class="sub">Kies een scenario en draai de jaarsimulatie (8.760 uur). Daarna: KPI's, deep dive op standaarddagen en het jaaroverzicht.</p>
    <div class="raster twee">
      <div class="kaart geel">
        <h3>Draai simulatie</h3>
        ${S.scenarios.length ? `<select class="tekstveld" id="sc">${opties}</select>
          <div style="margin-top:12px"><button class="knop primair groot" id="draai">▶ Draai simulatie</button></div>
          <div id="status" style="margin-top:12px"></div>` : '<div class="leeg">Maak eerst een scenario in stap 1.</div>'}
        <h3 style="margin-top:22px">Eerdere runs</h3>
        <div class="lijst runlijst" id="runs"></div>
      </div>
      <div id="resultaat"><div class="kaart leeg">Kies een run of draai een nieuwe simulatie.</div></div>
    </div>`;
  tekenRunlijst();
  if ($("#draai")) $("#draai").onclick = async () => {
    const sid = $("#sc").value;
    S.gekozenScenario = sid;
    $("#draai").disabled = true;
    $("#status").innerHTML = '<span class="spinner"></span> Rekenen…';
    const m = await api("/api/runs", { method: "POST", body: JSON.stringify({ scenario_id: sid }) });
    let r;
    do { await new Promise((ok) => setTimeout(ok, 700)); r = await api(`/api/runs/${m.id}`); } while (r.status === "bezig");
    $("#draai").disabled = false;
    if (r.status === "fout") { $("#status").innerHTML = `<div class="melding fout">${esc(r.fout)}</div>`; return; }
    $("#status").innerHTML = `✓ klaar in ${nl(r.duur_s, 1)} s`;
    S.gekozenRun = r.id;
    S.runs = await api("/api/runs");
    tekenRunlijst();
    toonRun(r);
  };
  if (S.gekozenRun && S.runs.find((r) => r.id === S.gekozenRun && r.status === "klaar")) toonRun(await api(`/api/runs/${S.gekozenRun}`));
}

function tekenRunlijst() {
  const doel = $("#runs");
  if (!doel) return;
  doel.innerHTML = S.runs.length ? "" : '<div class="leeg">Nog geen runs.</div>';
  S.runs.forEach((r) => {
    const el = document.createElement("div");
    el.className = "item" + (r.id === S.gekozenRun ? " gekozen" : "");
    el.innerHTML = `<div class="t">${esc(r.scenario_naam)}</div><div class="o">${esc(r.omschrijving || "")}</div>
      <div class="rij tussen"><div class="d">${esc(r.gestart.replace("T", " "))} · ${r.status}</div><button class="knop klein gevaar" data-weg>Verwijder</button></div>`;
    el.onclick = async (e) => {
      if (e.target.hasAttribute("data-weg")) return;
      if (r.status !== "klaar") return;
      S.gekozenRun = r.id; tekenRunlijst(); toonRun(await api(`/api/runs/${r.id}`));
    };
    el.querySelector("[data-weg]").onclick = async () => {
      if (!confirm("Run verwijderen?")) return;
      await api(`/api/runs/${r.id}`, { method: "DELETE" });
      if (S.gekozenRun === r.id) S.gekozenRun = null;
      schermSimulatie();
    };
    doel.appendChild(el);
  });
}

function kpiKaarten(k, wc) {
  const e = k.elektra, b = k.buffer, bd = k.bedrijf, ko = k.kosten;
  const items = [
    [nl(e.totaal_mwhe) + " MWhe", "elektriciteit warmtepompen / jaar"],
    [nl(e.spf_wp, 2), "SPF warmtepompen"],
    [nl(e.piek_kwe) + " kWe", "piek elektrisch vermogen"],
    [nl(e.gem_kwe_congestievenster, 1) + " kWe", "gem. vermogen in ontlaadvenster"],
    [nl(e.som_maandpieken_venster_kwe) + " kWe", "Σ maandpieken in venster"],
    [nl(b.geladen_mwh) + " / " + nl(b.naar_ht_mwh + b.naar_lt_mwh) + " MWh", "buffer geladen / ontladen"],
    [nl(bd.ht_pendeluren) + " / " + nl(bd.lt_pendeluren) + " h", "pendeluren HT / LT"],
    [nl(wc[">= 24 h"]) + " %", "back-up ≥ 24 h (alleen buffer)"],
    ["€ " + nl(ko.inkoop_vast_eur), "energiekosten WP's (UU-contract, incl. EB)"],
    [nl(k.warmte.tekort_mwh, 1) + " MWh", "warmtetekort"],
  ];
  return `<div class="kpis">${items.map(([w, l]) => `<div class="kpi"><div class="w">${w}</div><div class="l">${l}</div></div>`).join("")}</div>`;
}

async function toonRun(r) {
  const doel = $("#resultaat");
  const w = r.waarden;
  const strategie = w["strategie.naam"] === "congestie"
    ? `Netcongestie · ${w["strategie.congestie.alles_uit"] ? "WP's uit" : nl(w["strategie.congestie.reductie_kwe"]) + " kWe verlaging"}${w["strategie.congestie.adaptief"] ? " (adaptief)" : ""}`
    : "Referentie";
  doel.innerHTML = `
    <div class="kaart geel">
      <div class="rij tussen"><div><h3 style="margin:0">${esc(r.scenario_naam)}</h3>
        <div class="eenheid">${strategie} · buffer ${nl(w["buffer.volume_m3"])} m³ tot ${nl(w["buffer.t_laad_c"])} °C · venster ${w["congestie.uren_lokaal"][0]}–${w["congestie.uren_lokaal"][1]} h</div></div>
        <div class="eenheid">run ${esc(r.id)} · ${nl(r.duur_s, 1)} s</div></div>
    </div>
    <div class="sectie">${kpiKaarten(r.kpi, r.kpi.worstcase_met_condensor)}</div>
    <div class="kaart sectie">
      <h3>Deep dive · standaarddagen</h3>
      <div class="dagkeuze" id="dagen"></div>
      <div class="rij" style="margin-bottom:8px"><span class="eenheid">Of kies zelf:</span>
        <input type="date" id="eigen" class="tekstveld" style="width:170px" min="2001-01-01" max="2001-12-31">
        <select id="aantal" class="tekstveld" style="width:110px"><option value="1">1 dag</option><option value="3">3 dagen</option><option value="7">7 dagen</option></select></div>
      <div id="dagplot" class="grafiek"></div>
    </div>
    <div class="raster sectie" style="grid-template-columns:1fr 1fr">
      <div class="kaart"><h3>Elektrisch vermogen · dag × uur</h3><div id="heat" class="grafiek"></div></div>
      <div class="kaart"><h3>Maandpiek warmtepompen</h3><div id="maand" class="grafiek"></div></div>
      <div class="kaart"><h3>Duurkromme elektrisch vermogen</h3><div id="duur" class="grafiek"></div></div>
      <div class="kaart"><h3>Flexibiliteit: hoeveel kWe, hoe lang?</h3><div id="flex" class="grafiek"></div>
        <div class="eenheid">Referentie-basislijn met dezelfde systeeminstellingen; buffer levert in het venster, HT-WP's laden daarbuiten bij.</div></div>
    </div>`;
  const dagen = $("#dagen");
  r.typedagen.forEach((d, i) => {
    const c = document.createElement("div");
    c.className = "chip" + (i === 0 ? " aan" : "");
    c.innerHTML = `${esc(d.label)}<small>${d.datum.slice(5).split("-").reverse().join("-")} · ${esc(d.toelichting)}</small>`;
    c.onclick = () => { dagen.querySelectorAll(".chip").forEach((x) => x.classList.remove("aan")); c.classList.add("aan"); S.dag = d.datum; tekenDag(r.id); };
    dagen.appendChild(c);
  });
  S.dag = r.typedagen[0].datum;
  $("#eigen").onchange = (e) => { dagen.querySelectorAll(".chip").forEach((x) => x.classList.remove("aan")); S.dag = e.target.value; tekenDag(r.id); };
  $("#aantal").onchange = () => tekenDag(r.id);
  tekenDag(r.id);
  tekenJaar(r);
}

function vensterVormen(t, vens) {
  const vormen = [];
  let i = 0;
  while (i < vens.length) {
    if (vens[i]) {
      let j = i;
      while (j + 1 < vens.length && vens[j + 1]) j++;
      const eind = new Date(new Date(t[j]).getTime() + 3600e3).toISOString().slice(0, 16);
      vormen.push({ type: "rect", xref: "x", yref: "paper", x0: t[i], x1: eind, y0: 0, y1: 1, fillcolor: K.venster, line: { width: 0 }, layer: "below" });
      i = j + 1;
    } else i++;
  }
  return vormen;
}

async function tekenDag(rid) {
  const d = await api(`/api/runs/${rid}/dag?datum=${S.dag}&dagen=${$("#aantal").value}`);
  const t = d.t_lokaal, vens = d.congestievenster.map((v) => v === true || v === "True");
  const ontl = d.buf_ht.map((v, i) => -(v + d.buf_lt[i]));
  const sporen = [
    { x: t, y: d.el_ht, name: "WP HT [kWe]", type: "bar", marker: { color: K.ht }, xaxis: "x", yaxis: "y", offset: 0, width: 3600e3 },
    { x: t, y: d.el_lt, name: "WP LT [kWe]", type: "bar", marker: { color: K.lt }, xaxis: "x", yaxis: "y", offset: 0, width: 3600e3 },
    { x: t, y: d.laad, name: "buffer laden [kW]", type: "bar", marker: { color: K.buffer }, xaxis: "x", yaxis: "y2", offset: 0, width: 3600e3 },
    { x: t, y: ontl, name: "buffer ontladen [kW]", type: "bar", marker: { color: "#AA1555" }, xaxis: "x", yaxis: "y2", offset: 0, width: 3600e3 },
    { x: t, y: d.soc.map((v) => v * 100), name: "buffervulling [%]", line: { color: K.soc, width: 3, shape: "hv" }, xaxis: "x", yaxis: "y3" },
    { x: t, y: d.q_ht, name: "vraag HT [kW]", line: { color: K.ht, shape: "hv" }, xaxis: "x", yaxis: "y4" },
    { x: t, y: d.q_lt, name: "vraag LT [kW]", line: { color: K.lt, shape: "hv" }, xaxis: "x", yaxis: "y4" },
    { x: t, y: d.t_buiten, name: "T buiten [°C]", line: { color: K.temp, dash: "dot" }, xaxis: "x", yaxis: "y5" },
  ];
  const ly = layoutBasis({
    height: 760, barmode: "relative", bargap: 0.05, shapes: vensterVormen(t, vens),
    grid: { rows: 4, columns: 1, pattern: "coupled", roworder: "top to bottom" },
    yaxis: { title: "kWe", domain: [0.77, 1] }, yaxis2: { title: "kW", domain: [0.52, 0.73] },
    yaxis3: { title: "%", domain: [0.29, 0.48], range: [0, 105] }, yaxis4: { title: "kW", domain: [0, 0.25] },
    yaxis5: { title: "°C", overlaying: "y4", side: "right", showgrid: false },
    xaxis: { anchor: "y4", type: "date" }, legend: { orientation: "h", y: -0.07 },
    annotations: [
      { text: "<b>Elektrisch vermogen warmtepompen</b>", xref: "paper", yref: "paper", x: 0, y: 1.02, showarrow: false, xanchor: "left" },
      { text: "<b>Buffer laden (+) / ontladen (−)</b>", xref: "paper", yref: "paper", x: 0, y: 0.75, showarrow: false, xanchor: "left" },
      { text: "<b>Buffervulling</b>", xref: "paper", yref: "paper", x: 0, y: 0.50, showarrow: false, xanchor: "left" },
      { text: "<b>Warmtevraag en buitentemperatuur</b> · geel = ontlaadvenster", xref: "paper", yref: "paper", x: 0, y: 0.27, showarrow: false, xanchor: "left" },
    ],
  });
  Plotly.react("dagplot", sporen, ly, PL);
}

async function tekenJaar(r) {
  const j = await api(`/api/runs/${r.id}/jaar`);
  Plotly.react("heat", [{ type: "heatmap", x: j.heatmap.dagen, y: j.heatmap.uren, z: j.heatmap.z, colorscale: "Turbo", colorbar: { title: "kWe" } }],
    layoutBasis({ height: 330, xaxis: { title: "dag van het jaar" }, yaxis: { title: "uur" }, hovermode: "closest" }), PL);
  Plotly.react("maand", [
    { type: "bar", x: j.maand.maand.map((m) => MND[m - 1]), y: j.maand.piek, name: "maandpiek", marker: { color: "#9A9A9A" } },
    { type: "bar", x: j.maand.maand.map((m) => MND[m - 1]), y: j.maand.piek_venster, name: "piek in ontlaadvenster", marker: { color: K.totaal } },
  ], layoutBasis({ height: 330, barmode: "group", yaxis: { title: "kWe" } }), PL);
  Plotly.react("duur", [
    { y: j.duur, name: "hele jaar", line: { color: K.totaal, width: 2 } },
    { y: j.duur_venster, name: "alleen ontlaadvenster", line: { color: K.ht, width: 2 } },
  ], layoutBasis({ height: 330, xaxis: { title: "uren (gesorteerd)" }, yaxis: { title: "kWe" } }), PL);
  const lab = r.flex.map((x) => x.reductie_kwe === "alles" ? "uit" : String(x.reductie_kwe));
  Plotly.react("flex", [
    { x: lab, y: r.flex.map((x) => x.uren_volledig_pct), name: "% vensteruren volledig verlaagd", line: { color: K.totaal, width: 3 } },
    { x: lab, y: r.flex.map((x) => x.dagen_heel_venster_pct), name: "% dagen hele venster", line: { color: K.ht, width: 3, dash: "dot" } },
  ], layoutBasis({ height: 330, xaxis: { title: "gevraagde verlaging [kWe]", type: "category" }, yaxis: { title: "%", range: [0, 102] } }), PL);
}

/* ================================================================== 3 · VERGELIJKEN */
async function schermVergelijken() {
  S.runs = (await api("/api/runs")).filter((r) => r.status === "klaar");
  S.vergelijk = S.vergelijk.filter((id) => S.runs.find((r) => r.id === id));
  app.innerHTML = `
    <h2>Vergelijken</h2>
    <p class="sub">Kies 2 tot 4 runs. Verschillen worden getoond ten opzichte van de eerste gekozen run.</p>
    <div class="raster twee">
      <div class="kaart geel"><h3>Runs</h3><div class="lijst runlijst" id="kies" style="max-height:520px"></div></div>
      <div id="vgl"><div class="kaart leeg">Kies minstens twee runs.</div></div>
    </div>`;
  const kies = $("#kies");
  if (!S.runs.length) kies.innerHTML = '<div class="leeg">Nog geen afgeronde runs.</div>';
  S.runs.forEach((r) => {
    const el = document.createElement("div");
    const pos = S.vergelijk.indexOf(r.id);
    el.className = "item" + (pos >= 0 ? " gekozen" : "");
    el.innerHTML = `<div class="rij tussen"><div class="t">${esc(r.scenario_naam)}</div>${pos >= 0 ? `<span class="chip aan" style="background:${K.runs[pos]};border-color:${K.runs[pos]};color:#fff">${pos + 1}</span>` : ""}</div>
      <div class="o">${esc(r.omschrijving || "")}</div><div class="d">${esc(r.gestart.replace("T", " "))}</div>`;
    el.onclick = () => {
      const i = S.vergelijk.indexOf(r.id);
      if (i >= 0) S.vergelijk.splice(i, 1); else if (S.vergelijk.length < 4) S.vergelijk.push(r.id);
      schermVergelijken();
    };
    kies.appendChild(el);
  });
  if (S.vergelijk.length >= 2) toonVergelijking();
}

const KPI_RIJEN = [
  ["Elektriciteit WP's [MWhe]", (k) => k.elektra.totaal_mwhe, -1, 0],
  ["SPF warmtepompen [-]", (k) => k.elektra.spf_wp, 1, 2],
  ["Piek elektrisch [kWe]", (k) => k.elektra.piek_kwe, -1, 0],
  ["Gem. kWe in ontlaadvenster", (k) => k.elektra.gem_kwe_congestievenster, -1, 1],
  ["Max. kWe in ontlaadvenster", (k) => k.elektra.max_kwe_congestievenster, -1, 0],
  ["Σ maandpieken in venster [kWe]", (k) => k.elektra.som_maandpieken_venster_kwe, -1, 0],
  ["Buffer geladen [MWh]", (k) => k.buffer.geladen_mwh, 0, 0],
  ["Buffer ontladen [MWh]", (k) => k.buffer.naar_ht_mwh + k.buffer.naar_lt_mwh, 0, 0],
  ["Bufferverlies [MWh]", (k) => k.buffer.verlies_mwh, -1, 1],
  ["Pendeluren HT", (k) => k.bedrijf.ht_pendeluren, -1, 0],
  ["Pendeluren LT", (k) => k.bedrijf.lt_pendeluren, -1, 0],
  ["Back-up ≥ 24 h [%]", (k) => k.worstcase_met_condensor[">= 24 h"], 1, 0],
  ["Energiekosten WP's [€]", (k) => k.kosten.inkoop_vast_eur, -1, 0],
  ["kW-max WP's in venster (Σ maanden) [€]", (k) => k.kosten.indicatie_kwmax_venster_eur, -1, 0],
  ["Warmtetekort [MWh]", (k) => k.warmte.tekort_mwh, -1, 1],
];

async function toonVergelijking() {
  const runs = await Promise.all(S.vergelijk.map((id) => api(`/api/runs/${id}`)));
  const kop = runs.map((r, i) => `<th><span style="display:inline-block;width:10px;height:10px;background:${K.runs[i]};margin-right:6px"></span>${esc(r.scenario_naam)}</th>`).join("");
  const rijen = KPI_RIJEN.map(([lab, f, richting, d]) => {
    const basis = f(runs[0].kpi);
    return `<tr><td>${lab}</td>${runs.map((r, i) => {
      const v = f(r.kpi);
      let delta = "";
      if (i > 0 && basis !== 0 && richting !== 0 && v !== basis) {
        const pct = (v - basis) / Math.abs(basis) * 100;
        if (Math.abs(pct) >= 0.5) delta = ` <span class="${pct * richting > 0 ? "beter" : "slechter"}">(${pct > 0 ? "+" : ""}${nl(pct, 0)} %)</span>`;
      }
      return `<td class="num">${nl(v, d)}${delta}</td>`;
    }).join("")}</tr>`;
  }).join("");
  $("#vgl").innerHTML = `
    <div class="kaart"><h3>KPI's</h3><table class="tab"><thead><tr><th></th>${kop}</tr></thead><tbody>${rijen}</tbody></table>
      <div class="eenheid" style="margin-top:6px">Groen = beter, rood = slechter dan run 1.</div></div>
    <div class="kaart sectie"><h3>Standaarddag naast elkaar</h3><div class="dagkeuze" id="vdagen"></div><div id="vdag" class="grafiek"></div></div>
    <div class="raster sectie" style="grid-template-columns:1fr 1fr">
      <div class="kaart"><h3>Maandpiek WP's in ontlaadvenster</h3><div id="vmaand" class="grafiek"></div></div>
      <div class="kaart"><h3>Flexibiliteitsenvelop</h3><div id="vflex" class="grafiek"></div></div>
    </div>`;
  const vd = $("#vdagen");
  runs[0].typedagen.forEach((d, i) => {
    const c = document.createElement("div");
    c.className = "chip" + (i === 0 ? " aan" : "");
    c.innerHTML = `${esc(d.label)}<small>${d.datum.slice(5).split("-").reverse().join("-")}</small>`;
    c.onclick = () => { vd.querySelectorAll(".chip").forEach((x) => x.classList.remove("aan")); c.classList.add("aan"); tekenVergelijkDag(runs, d.datum); };
    vd.appendChild(c);
  });
  tekenVergelijkDag(runs, runs[0].typedagen[0].datum);

  const jaren = await Promise.all(runs.map((r) => api(`/api/runs/${r.id}/jaar`)));
  Plotly.react("vmaand", jaren.map((j, i) => ({ type: "bar", x: j.maand.maand.map((m) => MND[m - 1]), y: j.maand.piek_venster, name: runs[i].scenario_naam, marker: { color: K.runs[i] } })),
    layoutBasis({ height: 340, barmode: "group", yaxis: { title: "kWe" } }), PL);
  Plotly.react("vflex", runs.map((r, i) => ({ x: r.flex.map((x) => x.reductie_kwe === "alles" ? "uit" : String(x.reductie_kwe)), y: r.flex.map((x) => x.uren_volledig_pct), name: r.scenario_naam, line: { color: K.runs[i], width: 3 } })),
    layoutBasis({ height: 340, xaxis: { title: "gevraagde verlaging [kWe]", type: "category" }, yaxis: { title: "% vensteruren volledig", range: [0, 102] } }), PL);
}

async function tekenVergelijkDag(runs, datum) {
  const data = await Promise.all(runs.map((r) => api(`/api/runs/${r.id}/dag?datum=${datum}&dagen=1`)));
  const t = data[0].t_lokaal;
  const vens = data[0].congestievenster.map((v) => v === true || v === "True");
  const sporen = [];
  data.forEach((d, i) => {
    const kleur = K.runs[i], naam = runs[i].scenario_naam;
    sporen.push({ x: d.t_lokaal, y: d.el, name: naam, legendgroup: naam, line: { color: kleur, width: 3, shape: "hv" }, yaxis: "y" });
    sporen.push({ x: d.t_lokaal, y: d.buf_ht.map((v, j) => v + d.buf_lt[j] - d.laad[j]), name: naam + " · buffer", legendgroup: naam, showlegend: false, line: { color: kleur, width: 2, shape: "hv" }, yaxis: "y2" });
    sporen.push({ x: d.t_lokaal, y: d.soc.map((v) => v * 100), name: naam + " · vulling", legendgroup: naam, showlegend: false, line: { color: kleur, width: 2, dash: "dot" }, yaxis: "y3" });
  });
  Plotly.react("vdag", sporen, layoutBasis({
    height: 620, shapes: vensterVormen(t, vens), xaxis: { anchor: "y3", type: "date" },
    yaxis: { title: "kWe", domain: [0.68, 1] }, yaxis2: { title: "kW", domain: [0.36, 0.62] }, yaxis3: { title: "%", domain: [0, 0.3], range: [0, 105] },
    annotations: [
      { text: "<b>Elektrisch vermogen warmtepompen</b>", xref: "paper", yref: "paper", x: 0, y: 1.03, showarrow: false, xanchor: "left" },
      { text: "<b>Buffer: ontladen (+) / laden (−)</b>", xref: "paper", yref: "paper", x: 0, y: 0.64, showarrow: false, xanchor: "left" },
      { text: "<b>Buffervulling</b> · geel = ontlaadvenster", xref: "paper", yref: "paper", x: 0, y: 0.32, showarrow: false, xanchor: "left" },
    ],
  }), PL);
}

route();
