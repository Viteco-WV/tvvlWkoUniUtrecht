/* Webapp simulatie BoTu UU — drie schermen: scenario's → simulatie → vergelijken. */
const K = {  // grafiekkleuren: UU-secundair, alleen in grafieken
  ht: "#C00A35", lt: "#F3965E", buffer: "#24A793", soc: "#5287C6", totaal: "#001240", temp: "#5287C6",
  venster: "rgba(255,205,0,0.22)", runs: ["#001240", "#C00A35", "#24A793", "#F3965E"],
};
const TURBO = [[0, "#30123B"], [0.1, "#4662D7"], [0.2, "#36AAF9"], [0.3, "#1AE4B6"], [0.4, "#72FE5E"], [0.5, "#C7EF34"],
  [0.6, "#FABA39"], [0.7, "#F66B19"], [0.8, "#CA2A04"], [0.9, "#8F0D02"], [1, "#7A0403"]];  // regenboogschaal (Turbo)
const MAANDSTART = [1, 32, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335];
// categorie-as van de flexibiliteitsenvelop: label bij 20, 60, … kWe en "uit"
const flexAs = (lab) => ({ title: "gevraagde verlaging [kWe]", type: "category", tickangle: 0,
  tickvals: lab.filter((x) => x === "uit" || Number(x) % 40 === 20) });
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
  margin: { l: 60, r: 20, t: 40, b: 50 }, hovermode: "x unified",
  legend: { orientation: "h", x: 0, xanchor: "left", y: 1.02, yanchor: "bottom" }, ...extra,
});

// gestapelde panelen met vaste tussenruimte; titel net boven elk paneel
// gestapelde panelen met vaste tussenruimte; per paneel de titel met daaronder een eigen legenda (legend, legend2, …).
// Let op: zet `showlegend: true` in de layout, anders verbergt Plotly bij meerdere legenda's de eerste.
function panelen(hoogtes, titels, gat = 0.075) {
  const schaal = (1 - gat * (hoogtes.length - 1)) / hoogtes.reduce((a, b) => a + b, 0);
  const uit = { assen: {}, annotations: [], legendes: {} };
  let top = 1;
  hoogtes.forEach((h, i) => {
    const onder = top - h * schaal;
    uit.assen[i === 0 ? "yaxis" : `yaxis${i + 1}`] = { domain: [Math.max(0, onder), top] };
    uit.annotations.push({ text: titels[i], xref: "paper", yref: "paper", x: 0, y: top, yshift: 26, yanchor: "bottom", xanchor: "left", showarrow: false });
    uit.legendes[i === 0 ? "legend" : `legend${i + 1}`] = { orientation: "h", x: 0, xanchor: "left", y: top, yanchor: "bottom", yref: "paper",
      font: { size: 11 }, bgcolor: "rgba(0,0,0,0)", itemwidth: 30 };
    top = onder - gat;
  });
  return uit;
}

// koppel elk spoor aan de legenda van zijn paneel; `paneel` vertaalt een y-as naar het paneelnummer (1, 2, …)
function legendaPerPaneel(sporen, paneel) {
  sporen.forEach((sp) => { const n = paneel[sp.yaxis || "y"]; sp.legend = n === 1 ? "legend" : `legend${n}`; });
}
const TIJDAS = { type: "date", tickformat: "%H:%M<br>%d-%m", hoverformat: "%d-%m %H:%M", showgrid: true };

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
    const n = (await api("/api/runs")).filter((r) => r.scenario_id === huidig.id).length;
    if (!confirm(`Scenario '${huidig.naam}' verwijderen?${n ? `\n\nOok de ${n} resultaten van dit scenario worden verwijderd.` : ""}`)) return;
    await api(`/api/scenarios/${huidig.id}`, { method: "DELETE" });
    S.vergelijk = []; S.gekozenRun = null;
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
  S.runs = S.runs.filter((r) => r.scenario_bestaat);   // resultaten van verwijderde scenario's niet tonen
  if (!S.scenarios.length) { app.innerHTML = '<h2>Simulatie</h2><div class="kaart leeg sectie">Maak eerst een scenario in stap 1.</div>'; return; }
  // gekozen scenario (uit stap 1) heeft voorrang; het resultaat volgt het scenario
  const gekozen = S.runs.find((r) => r.id === S.gekozenRun);
  const laatste = S.runs.find((r) => r.status === "klaar" && S.scenarios.find((s) => s.id === r.scenario_id));
  if (!S.scenarios.find((s) => s.id === S.gekozenScenario))   // niets gekozen: open op het scenario van de laatste run
    S.gekozenScenario = (gekozen || laatste || { scenario_id: S.scenarios[0].id }).scenario_id;
  if (!gekozen || gekozen.scenario_id !== S.gekozenScenario)
    S.gekozenRun = (S.runs.find((r) => r.scenario_id === S.gekozenScenario && r.status === "klaar") || {}).id || null;
  app.innerHTML = `
    <h2>Simulatie</h2>
    <div class="kaart geel simbalk">
      <div><label for="sc">Scenario</label><select class="tekstveld" id="sc">${S.scenarios.map((s) =>
        `<option value="${s.id}">${esc(s.naam)}</option>`).join("")}</select></div>
      <button class="knop zwart" id="draai">▶ Draai simulatie</button>
      <div><label for="run">Resultaat</label><select class="tekstveld" id="run"></select></div>
      <button class="knop klein gevaar" id="weg" title="Gekozen resultaat verwijderen">Verwijder</button>
    </div>
    <div id="status" class="sectie" hidden></div>
    <div id="resultaat" class="sectie"></div>`;
  $("#sc").value = S.gekozenScenario;
  vulRunkeuze();

  $("#sc").onchange = () => {   // ander scenario: toon het laatste resultaat daarvan, als dat er is
    S.gekozenScenario = $("#sc").value;
    const laatste = S.runs.find((r) => r.scenario_id === S.gekozenScenario && r.status === "klaar");
    S.gekozenRun = laatste ? laatste.id : null;
    vulRunkeuze(); toonGekozen();
  };
  $("#run").onchange = () => {   // resultaat van een ander scenario: scenariokeuze volgt mee
    S.gekozenRun = $("#run").value || null;
    const r = S.runs.find((x) => x.id === S.gekozenRun);
    if (r && S.scenarios.find((s) => s.id === r.scenario_id)) { S.gekozenScenario = r.scenario_id; $("#sc").value = r.scenario_id; }
    vulRunkeuze(); toonGekozen();
  };
  $("#weg").onclick = async () => {
    if (!S.gekozenRun || !confirm("Dit resultaat verwijderen?")) return;
    await api(`/api/runs/${S.gekozenRun}`, { method: "DELETE" });
    S.gekozenRun = null; schermSimulatie();
  };
  $("#draai").onclick = async () => {
    const st = $("#status");
    $("#draai").disabled = true; st.hidden = false;
    st.innerHTML = '<div class="kaart"><span class="spinner"></span> Jaarsimulatie rekenen (8.760 uur)…</div>';
    const m = await api("/api/runs", { method: "POST", body: JSON.stringify({ scenario_id: S.gekozenScenario }) });
    let r;
    do { await new Promise((ok) => setTimeout(ok, 700)); r = await api(`/api/runs/${m.id}`); } while (r.status === "bezig");
    $("#draai").disabled = false;
    if (r.status === "fout") { st.innerHTML = `<div class="melding fout">${esc(r.fout)}</div>`; return; }
    st.hidden = true;
    S.gekozenRun = r.id;
    S.runs = (await api("/api/runs")).filter((r) => r.scenario_bestaat);
    vulRunkeuze(); toonRun(r);
  };
  toonGekozen();
}

// resultatenlijst: alleen afgeronde runs, nieuwste eerst
function vulRunkeuze() {
  const klaar = S.runs.filter((r) => r.status === "klaar");
  if (S.gekozenRun && !klaar.find((r) => r.id === S.gekozenRun)) S.gekozenRun = null;
  $("#run").innerHTML = (S.gekozenRun ? "" : '<option value="">— nog geen resultaat gekozen —</option>')
    + klaar.map((r) => `<option value="${r.id}">${esc(r.scenario_naam)} · ${r.gestart.slice(8, 10)}-${r.gestart.slice(5, 7)} ${r.gestart.slice(11, 16)}${r.nieuwste ? "" : " · eerdere run"}</option>`).join("");
  $("#run").value = S.gekozenRun || "";
  $("#weg").disabled = !S.gekozenRun;
}

async function toonGekozen() {
  if (!S.gekozenRun) {
    $("#resultaat").innerHTML = '<div class="kaart leeg">Nog geen resultaat voor dit scenario. Klik op <b>Draai simulatie</b>.</div>';
    return;
  }
  toonRun(await api(`/api/runs/${S.gekozenRun}`));
}

function vensterTekst(w) {
  const mnd = w["congestie.maanden"] || [], uren = w["congestie.uren_lokaal"] || [];
  return `${w["congestie.alleen_werkdagen"] ? "werkdagen" : "alle dagen"} ${uren[0]}–${uren[1]} h, ${MND[mnd[0] - 1]}–${MND[mnd[mnd.length - 1] - 1]}`;
}

// ⓘ-knop met uitlegpopup; plaatsen als direct kind van een .kpi of .kaart
const info = (titel, html) => `<button class="info" type="button" aria-label="Uitleg: ${esc(titel)}" aria-expanded="false">i</button><div class="uitleg" role="dialog" hidden>${html}</div>`;

// uitleg bij de grafieken; w = scenariowaarden van de (eerste) run
const UITLEG = {
  dag: (w) => `<b>Wat:</b> het uurbeeld van de gekozen dag(en), van boven naar beneden:
    de warmte uit de HT-WP's, verdeeld over de kassen en het buffer; het elektrisch vermogen van de HT- en LT-WP's; het laden (+) en ontladen (−) van het buffer; de buffervulling; en de warmtevraag per net met de buitentemperatuur.
    <b>Stippellijnen:</b> zwart is het maximale warmtevermogen van de HT-WP's (aantal × vermogen per WP). Raken de staven die lijn, dan kan het buffer niet sneller laden. Rood is de grens van de elektrische aansluiting.
    <b>Geel:</b> het ontlaadvenster (${vensterTekst(w)}). Daarin levert het buffer de warmte en gaan de WP's omlaag of uit.
    <b>Back-up-tabel:</b> per dag hoeveel uur het buffer alleen de vraag kan dekken als alle WP's aan het begin van het venster uitgaan.`,
  heat: () => `<b>Wat:</b> elk vakje is één uur van het jaar. Horizontaal staat de dag, verticaal het uur van de dag (lokale tijd). De kleur is het elektrisch vermogen van de WP's samen.
    <b>Zo lees je het:</b> rood is veel vermogen, blauw is weinig of uit. Een blauwe band overdag in de wintermaanden is het ontlaadvenster. Rode banden ervoor en erna laten zien waar het bijladen van het buffer naartoe verschuift.`,
  maand: (w) => `<b>Wat:</b> per maand de hoogste uurwaarde van het elektrisch vermogen van de WP's samen.
    <b>Grijs, maandpiek:</b> het hoogste uur van de hele maand, ook 's nachts en in het weekend. Hierop is het kW-max-tarief gebaseerd.
    <b>Donker, piek in het ontlaadvenster:</b> het hoogste uur binnen het venster (${vensterTekst(w)}). Zoveel dragen de WP's op z'n hoogst nog bij aan de campuspiek tijdens congestie.
    <b>Zo lees je het:</b> donker 0 betekent dat de WP's die maand in elk vensteruur uit stonden. Geen donkere balk betekent dat de maand buiten de congestieperiode valt. De grijze piek daalt meestal niet, want het bijladen buiten het venster vraagt ook vermogen: de piek verschuift en verdwijnt niet.`,
  duur: () => `<b>Wat:</b> alle uurwaarden van het WP-vermogen, gesorteerd van hoog naar laag.
    <b>Zo lees je het:</b> op x = 1.000 staat het vermogen dat 1.000 uur per jaar wordt gehaald of overschreden. Het oppervlak onder de lijn is het jaarverbruik.
    <b>Donker:</b> alle 8.760 uren. <b>Rood:</b> alleen de vensteruren; hoe sneller die naar 0 zakt, hoe vaker de WP's in het venster uit staan.`,
  flex: () => `<b>Vraag:</b> als we in elk vensteruur R kWe minder willen afnemen (x-as), hoe vaak lukt dat dan?
    <b>Berekening:</b> uitgaande van een referentierun met dezelfde installatie levert het buffer het weggevallen vermogen, en de HT-WP's laden het buiten het venster weer bij. Het model rekent het hele jaar aan één stuk door: een buffer dat na een koude dag niet vol is, telt mee voor de volgende dag.
    <b>Doorgetrokken lijn:</b> het aandeel vensteruren waarin de volledige verlaging wordt gehaald.
    <b>Stippellijn:</b> het aandeel dagen waarop dat het hele venster lukt.
    <b>"uit":</b> de WP's helemaal uit in het venster.`,
  vdag: (w) => `<b>Wat:</b> dezelfde dag(en) voor alle gekozen runs, elk in een eigen kleur. Van boven naar beneden: het elektrisch vermogen van de WP's samen; het ontladen (+) en laden (−) van het buffer; de buffervulling.
    <b>Geel:</b> het ontlaadvenster van de eerste run (${vensterTekst(w)}).`,
  vmaand: (w) => `<b>Wat:</b> per maand het hoogste uur van het WP-vermogen binnen het ontlaadvenster (${vensterTekst(w)}), per run.
    <b>Zo lees je het:</b> 0 betekent dat de WP's in elk vensteruur van die maand uit stonden. Geen balk betekent dat er die maand geen venster is.`,
  vflex: () => `<b>Wat:</b> het aandeel vensteruren waarin een gevraagde verlaging van R kWe volledig lukt, per run.
    De berekening is dezelfde als bij de flexibiliteitsgrafiek in het Simulatie-scherm: buffer levert, HT-WP's laden buiten het venster bij, en het jaar wordt aan één stuk doorgerekend.`,
};

function kpiKaarten(k, wc, w, mx) {
  const e = k.elektra, a = k.aansluiting;
  const venster = vensterTekst(w);
  const items = [
    [nl(e.totaal_mwhe) + " MWhe", "elektriciteit warmtepompen / jaar",
      `<b>Wat:</b> het totale elektriciteitsverbruik van de drie warmtepompen (2 × HT, 1 × LT) over het simulatiejaar (8.760 uur).
       <b>Telt mee:</b> directe warmtelevering aan het HT- en LT-net én het laden van het buffer.
       <b>Telt niet mee:</b> circulatiepompen, regeling en de ZLT-koelmachine.
       <div class="formule">Σ<sub>uren</sub> (P<sub>el,HT</sub> + P<sub>el,LT</sub>) × 1 h ÷ 1.000</div>`],
    [nl(e.spf_wp, 2), "SPF warmtepompen",
      `<b>Wat:</b> de seizoensprestatiefactor, dus de jaargemiddelde COP van de warmtepompen samen.
       <b>Telt mee:</b> alle warmte die de WP's leveren, zowel direct aan de netten als voor het laden van het buffer.
       <b>Telt niet mee:</b> de condensorwarmte van de ZLT-koelmachine. Bufferverliezen drukken de SPF dus niet, maar kosten wel extra laadwerk.
       <div class="formule">SPF = Σ Q<sub>WP</sub> ÷ Σ E<sub>el,WP</sub></div>Hoger = efficiënter.`],
    [nl(e.piek_kwe) + " kWe", `piek elektrisch vermogen (${[mx ? `max. ${nl(mx.totaal_kwe)}` : "", a ? `aansluiting ${nl(a.grens_kwe)}` : ""].filter(Boolean).join(" · ")} kWe)`
        + (a && a.uren_boven ? ` · <span class="slechter">${nl(a.uren_boven)} h erboven</span>` : ""),
      `<b>Wat:</b> het hoogste elektrische vermogen van de warmtepompen samen in het hele jaar, binnen én buiten het ontlaadvenster.
       ${a ? `<b>Aansluiting:</b> grens voor de WP's ${nl(a.grens_kwe)} kWe (${nl(a.kva)} kVA × cos φ − overige gebruikers).
       ${a.uren_boven ? `Overschreden in <b>${nl(a.uren_boven)} uur</b>, met maximaal ${nl(a.max_overschrijding_kwe)} kWe en ${nl(a.kwh_boven)} kWh boven de grens.` : "Nergens overschreden."}
       Het model begrenst de WP's niet; dit laat zien wat de gekozen instellingen van de aansluiting vragen.` : ""}
       ${mx ? `<b>Max. tussen haakjes:</b> wat de WP's samen maximaal kunnen vragen: alle WP's op hun maximale thermische vermogen bij de slechtste COP.
       <div class="formule">HT ${nl(w["warmtepompen.ht.aantal"])} × ${nl(w["warmtepompen.ht.p_max_kw"])} kW bij ${nl(mx.ht.t_c)} °C, COP ${nl(mx.ht.cop, 2)} → ${nl(mx.ht.kwe)} kWe<br>
       LT ${nl(w["warmtepompen.lt.aantal"])} × ${nl(w["warmtepompen.lt.p_max_kw"])} kW bij ${nl(mx.lt.t_c)} °C, COP ${nl(mx.lt.cop, 2)} → ${nl(mx.lt.kwe)} kWe</div>
       Dit volgt uit het COP-model (aanname). Het echte aansluitvermogen staat op de typeplaat van de WP's en kan hoger liggen, bijvoorbeeld door hulpaandrijvingen en aanloopstroom.` : ""}
       <b>Let op:</b> het model rekent per uur, dus dit is een uurgemiddelde. Kwartierpieken kunnen hoger liggen, bijvoorbeeld bij het opstarten.
       <div class="formule">max<sub>uren</sub> (P<sub>el,HT</sub> + P<sub>el,LT</sub>)</div>`],
    [nl(e.gem_kwe_congestievenster, 1) + " kWe", "gem. vermogen in ontlaadvenster",
      `<b>Wat:</b> het gemiddelde elektrische vermogen van de warmtepompen samen over alle uren van het ontlaadvenster (hier: ${venster}).
       <b>Zo lees je het:</b> 0 kWe betekent dat de WP's in het venster altijd uit staan en het buffer alle warmte levert. Vergelijk met de referentie om de gemiddelde verlaging te zien.
       <div class="formule">gem<sub>vensteruren</sub> (P<sub>el,HT</sub> + P<sub>el,LT</sub>)</div>`],
    [nl(wc[">= 24 h"]) + " %", "back-up ≥ 24 h (alleen buffer)",
      `<b>Wat:</b> een worst-case-test, los van de gekozen strategie. Alle warmtepompen vallen uit en het buffer (${nl(w["buffer.volume_m3"])} m³) is vol.
       <b>Berekening:</b> voor elk van de 8.760 mogelijke starturen bepaalt het model hoeveel uur het buffer, samen met de condensorwarmte naar LT, de volledige HT- en LT-vraag nog kan leveren. Het getal is het aandeel starturen waarop dat minstens 24 uur lukt.
       <b>Stopt zodra:</b> het buffer leeg is, het ontlaadvermogen tekortschiet, of de buffertemperatuur onder de gevraagde aanvoertemperatuur zakt.
       <div class="formule">kortst ${nl(wc.kortst_h)} h · mediaan ${nl(wc.mediaan_h)} h</div>
       <b>Let op:</b> dit is een jaarcijfer met steeds een vol buffer. Per dag, ook vanaf de werkelijke vulling in de simulatie, zie je het in de deep dive.`],
  ];
  return `<div class="kpis">${items.map(([v, l, uitleg]) => `<div class="kpi">${info(l.replace(/<[^>]+>/g, ""), uitleg)}<div class="w">${v}</div><div class="l">${l}</div></div>`).join("")}</div>`;
}

// één uitleg-popup tegelijk; sluit bij klik buiten de popup of met Escape
function sluitUitleg(behalve) {
  document.querySelectorAll(".uitleg").forEach((u) => { if (u !== behalve) { u.hidden = true; u.parentElement.querySelector(".info").setAttribute("aria-expanded", "false"); } });
}
document.addEventListener("click", (e) => {
  const knop = e.target.closest(".info");
  if (!knop) { if (!e.target.closest(".uitleg")) sluitUitleg(); return; }
  const u = knop.parentElement.querySelector(".uitleg");
  sluitUitleg(u);
  u.hidden = !u.hidden; knop.setAttribute("aria-expanded", String(!u.hidden));
  const tegel = knop.parentElement.getBoundingClientRect();   // klap open naar de kant waar ruimte is
  u.classList.toggle("links", tegel.right - u.offsetWidth < 8);
});
document.addEventListener("keydown", (e) => { if (e.key === "Escape") sluitUitleg(); });

// verlaging in het venster; oude runs hadden "volledig uit" of een verlaging in kWe
function verlagingTekst(w) {
  const pct = w["strategie.congestie.verlaging_pct"];
  if (pct !== undefined) return pct >= 100 ? "WP's uit" : `${nl(pct)} % minder vermogen`;
  return w["strategie.congestie.alles_uit"] ? "WP's uit" : `${nl(w["strategie.congestie.reductie_kwe"])} kWe verlaging`;
}

async function toonRun(r) {
  const doel = $("#resultaat");
  const w = r.waarden;
  S.grens = r.kpi.aansluiting?.grens_kwe;
  S.htMax = (w["warmtepompen.ht.aantal"] || 0) * (w["warmtepompen.ht.p_max_kw"] || 0);   // maximaal warmtevermogen HT-WP's
  const strategie = w["strategie.naam"] === "congestie"
    ? `Netcongestie · ${verlagingTekst(w)}${w["strategie.congestie.adaptief"] ? " (adaptief)" : ""}`
    : "Referentie";
  doel.innerHTML = `
    <div class="kaart">
      <div class="rij tussen"><div><h3 style="margin:0">${esc(r.scenario_naam)}</h3>
        <div class="eenheid">${strategie} · buffer ${nl(w["buffer.volume_m3"])} m³ tot ${nl(w["buffer.t_laad_c"])} °C · venster ${w["congestie.uren_lokaal"][0]}–${w["congestie.uren_lokaal"][1]} h</div></div>
        <div class="eenheid">run ${esc(r.id)} · ${nl(r.duur_s, 1)} s</div></div>
    </div>
    <div class="sectie">${kpiKaarten(r.kpi, r.kpi.worstcase_met_condensor, r.waarden, r.max_vermogen)}</div>
    <div class="kaart sectie">
      <h3>Deep dive · standaarddagen</h3>${info("Deep dive", UITLEG.dag(r.waarden))}
      <div class="rij" style="margin-bottom:8px">
        <select id="dagen" class="tekstveld" style="width:auto;min-width:260px"></select>
        <input type="date" id="eigen" class="tekstveld" style="width:170px" min="2001-01-01" max="2001-12-31">
        <select id="aantal" class="tekstveld" style="width:110px"><option value="1">1 dag</option><option value="3">3 dagen</option><option value="4">4 dagen</option><option value="7">7 dagen</option></select></div>
      <div id="dagtoel" class="eenheid" style="margin-bottom:8px"></div>
      <div id="backup"></div>
      <div id="dagplot" class="grafiek"></div>
    </div>
    <div class="raster sectie" style="grid-template-columns:1fr 1fr">
      <div class="kaart"><h3>Elektrisch vermogen · dag × uur</h3>${info("Heatmap", UITLEG.heat())}<div id="heat" class="grafiek"></div></div>
      <div class="kaart"><h3>Maandpiek warmtepompen</h3>${info("Maandpiek", UITLEG.maand(r.waarden))}<div id="maand" class="grafiek"></div></div>
      <div class="kaart"><h3>Duurkromme elektrisch vermogen</h3>${info("Duurkromme", UITLEG.duur())}<div id="duur" class="grafiek"></div></div>
      <div class="kaart"><h3>Flexibiliteit: hoeveel kWe, hoe lang?</h3>${info("Flexibiliteit", UITLEG.flex())}<div id="flex" class="grafiek"></div>
        <div class="eenheid">Referentie-basislijn met dezelfde systeeminstellingen; buffer levert in het venster, HT-WP's laden daarbuiten bij.</div></div>
    </div>`;
  const dagen = $("#dagen");
  dagOpties(dagen, r.typedagen, true);
  const kies = () => {
    const d = r.typedagen[dagen.value];
    if (!d) return;
    S.dag = d.datum; $("#eigen").value = d.datum; $("#aantal").value = d.dagen || 1;
    $("#dagtoel").textContent = d.toelichting;
    tekenDag(r.id);
  };
  dagen.onchange = kies;
  $("#eigen").onchange = (e) => { dagen.value = "eigen"; $("#dagtoel").textContent = ""; S.dag = e.target.value; tekenDag(r.id); };
  $("#aantal").onchange = () => tekenDag(r.id);
  kies();
  tekenJaar(r);
}

function dagOpties(sel, typedagen, eigen) {
  sel.innerHTML = typedagen.map((d, i) => `<option value="${i}">${esc(d.label)} · ${d.datum.slice(5).split("-").reverse().join("-")}</option>`).join("")
    + (eigen ? `<option value="eigen" disabled>Eigen datum</option>` : "");
}

// back-up per getoonde dag: alle WP's uit vanaf het begin van het venster
function tekenBackup(rijen) {
  const doel = $("#backup");
  if (!rijen || !rijen.length) { doel.innerHTML = ""; return; }
  const dag = (iso) => new Date(iso).toLocaleDateString("nl-NL", { weekday: "short", day: "2-digit", month: "2-digit" });
  const uur = (h, max) => h >= max ? `&gt; ${max} h` : `${h} h`;
  doel.innerHTML = `<div class="backup"><div class="rij tussen"><h4>Back-up alleen buffer · start ${rijen[0].start}, alle WP's uit</h4>
      <span class="eenheid">hoeveel uur dekt het buffer (met condensorwarmte) nog de volledige vraag?</span></div>
    <table class="tab"><thead><tr><th>Dag</th><th>Vulling om ${rijen[0].start}</th><th>Vanaf vol buffer</th><th>Vanaf werkelijke vulling</th></tr></thead>
    <tbody>${rijen.map((r) => `<tr><td>${dag(r.datum)}</td><td>${r.soc_pct ?? "–"} %</td><td>${uur(r.vol_h, r.max_h)}</td>
      <td class="${r.nu_h < 24 ? "krap" : ""}"><b>${uur(r.nu_h, r.max_h)}</b></td></tr>`).join("")}</tbody></table>
    <div class="eenheid">"Vanaf vol" is het theoretische maximum op deze dag; "werkelijk" gaat uit van de vulling die het buffer in deze simulatie op dat moment heeft. Rood = minder dan 24 h.</div></div>`;
}

// "2001-01-15T16:00" + 1 uur, in lokale notatie (toISOString zou naar UTC omrekenen en een uur verschuiven)
function plusUur(t) {
  const d = new Date(t); d.setHours(d.getHours() + 1);
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:00`;
}

// horizontale stippellijn op de grens van de elektrische aansluiting
function grensSpoor(t, grens, kleur = "#C00A35", naam, yaxis = "y") {
  return { x: [t[0], plusUur(t[t.length - 1])], y: [grens, grens], mode: "lines", name: naam || `aansluiting ${nl(grens)} kWe`,
    line: { color: kleur, width: 2, dash: "dash" }, xaxis: "x", yaxis, hoverinfo: "skip" };
}

function vensterVormen(t, vens) {
  const vormen = [];
  let i = 0;
  while (i < vens.length) {
    if (vens[i]) {
      let j = i;
      while (j + 1 < vens.length && vens[j + 1]) j++;
      const eind = plusUur(t[j]);
      vormen.push({ type: "rect", xref: "x", yref: "paper", x0: t[i], x1: eind, y0: 0, y1: 1, fillcolor: K.venster, line: { width: 0 }, layer: "below" });
      i = j + 1;
    } else i++;
  }
  return vormen;
}

async function tekenDag(rid) {
  const d = await api(`/api/runs/${rid}/dag?datum=${S.dag}&dagen=${$("#aantal").value}`);
  tekenBackup(d.backup);
  const t = d.t_lokaal, vens = d.congestievenster.map((v) => v === true || v === "True");
  const ontl = d.buf_ht.map((v, i) => -(v + d.buf_lt[i]));
  const staaf = (y, name, color, yaxis) => ({ x: t, y, name, type: "bar", marker: { color }, xaxis: "x", yaxis, offset: 0, width: 3600e3 });
  const sporen = [
    // 1 · warmte uit de HT-WP's: direct naar de kassen of in het buffer, tegen het maximale HT-vermogen
    staaf(d.htwp_dir, "HT-WP's → kassen [kW]", "#9FB3A8", "y"),
    staaf(d.laad, "HT-WP's → buffer [kW]", K.buffer, "y"),
    // 2 · elektrisch vermogen, tegen de aansluiting
    staaf(d.el_ht, "WP HT [kWe]", K.ht, "y2"),
    staaf(d.el_lt, "WP LT [kWe]", K.lt, "y2"),
    // 3–5 · buffer, vulling, vraag en buitentemperatuur
    staaf(d.laad, "buffer laden [kW]", K.buffer, "y3"),
    staaf(ontl, "buffer ontladen [kW]", "#AA1555", "y3"),
    { x: t, y: d.soc.map((v) => v * 100), name: "buffervulling [%]", line: { color: K.soc, width: 3, shape: "hv" }, xaxis: "x", yaxis: "y4" },
    { x: t, y: d.q_ht, name: "vraag HT [kW]", line: { color: K.ht, shape: "hv" }, xaxis: "x", yaxis: "y5" },
    { x: t, y: d.q_lt, name: "vraag LT [kW]", line: { color: K.lt, shape: "hv" }, xaxis: "x", yaxis: "y5" },
    { x: t, y: d.t_buiten, name: "T buiten [°C]", line: { color: K.temp, dash: "dot" }, xaxis: "x", yaxis: "y6" },
  ];
  if (S.htMax) sporen.push(grensSpoor(t, S.htMax, "#1A1A1A", `max. HT-warmte ${nl(S.htMax)} kW`, "y"));
  if (S.grens) sporen.push(grensSpoor(t, S.grens, "#C00A35", undefined, "y2"));
  const p = panelen([0.22, 0.17, 0.15, 0.11, 0.2], ["<b>Warmte uit de HT-warmtepompen</b> [kW] · naar kassen en naar buffer",
    "<b>Elektrisch vermogen warmtepompen</b> [kWe]", "<b>Buffer laden (+) / ontladen (−)</b> [kW]",
    "<b>Buffervulling</b> [%]", "<b>Warmtevraag</b> [kW] <b>en buitentemperatuur</b> [°C] · geel = ontlaadvenster"], 0.085);
  legendaPerPaneel(sporen, { y: 1, y2: 2, y3: 3, y4: 4, y5: 5, y6: 5 });
  sporen.find((sp) => sp.yaxis === "y4").showlegend = false;   // buffervulling: één lijn, de titel zegt genoeg
  const ly = layoutBasis({
    height: 1120, showlegend: true, barmode: "relative", bargap: 0.05, shapes: vensterVormen(t, vens), margin: { l: 60, r: 55, t: 60, b: 50 },
    yaxis: { ...p.assen.yaxis, rangemode: "tozero" }, yaxis2: { ...p.assen.yaxis2, rangemode: "tozero" },
    yaxis3: { ...p.assen.yaxis3, zeroline: true, zerolinecolor: "#9A9A9A" },
    yaxis4: { ...p.assen.yaxis4, range: [0, 105], tickvals: [0, 50, 100] }, yaxis5: { ...p.assen.yaxis5, rangemode: "tozero" },
    yaxis6: { overlaying: "y5", side: "right", showgrid: false, zeroline: false, ticksuffix: " °C" },
    xaxis: { ...TIJDAS, anchor: "y5" }, ...p.legendes, annotations: p.annotations,
  });
  Plotly.react("dagplot", sporen, ly, PL);
}

async function tekenJaar(r) {
  const j = await api(`/api/runs/${r.id}/jaar`);
  Plotly.react("heat", [{ type: "heatmap", x: j.heatmap.dagen, y: j.heatmap.uren, z: j.heatmap.z, colorscale: TURBO, colorbar: { title: { text: "kWe" }, thickness: 12 } }],
    layoutBasis({ height: 330, margin: { l: 60, r: 10, t: 20, b: 40 }, xaxis: { tickvals: MAANDSTART.filter((_, i) => i % 2 === 0), ticktext: MND.filter((_, i) => i % 2 === 0), tickangle: 0 },
      yaxis: { title: "uur", tickvals: [0, 6, 12, 18, 23] }, hovermode: "closest" }), PL);
  Plotly.react("maand", [
    { type: "bar", x: j.maand.maand.map((m) => MND[m - 1]), y: j.maand.piek, name: "maandpiek", marker: { color: "#9A9A9A" } },
    { type: "bar", x: j.maand.maand.map((m) => MND[m - 1]), y: j.maand.piek_venster, name: "piek in ontlaadvenster", marker: { color: K.totaal },
      text: j.maand.piek_venster.map((v) => v === null ? "" : nl(v)), textposition: "outside", cliponaxis: false, textfont: { size: 10 } },
  ], layoutBasis({ height: 330, barmode: "group", yaxis: { title: "kWe" } }), PL);
  Plotly.react("duur", [
    { y: j.duur, name: "hele jaar", line: { color: K.totaal, width: 2 } },
    { y: j.duur_venster, name: "alleen ontlaadvenster", line: { color: K.ht, width: 2 } },
  ], layoutBasis({ height: 330, xaxis: { title: "uren (gesorteerd)" }, yaxis: { title: "kWe" } }), PL);
  const lab = r.flex.map((x) => x.reductie_kwe === "alles" ? "uit" : String(x.reductie_kwe));
  Plotly.react("flex", [
    { x: lab, y: r.flex.map((x) => x.uren_volledig_pct), name: "% vensteruren volledig verlaagd", line: { color: K.totaal, width: 3 } },
    { x: lab, y: r.flex.map((x) => x.dagen_heel_venster_pct), name: "% dagen hele venster", line: { color: K.ht, width: 3, dash: "dot" } },
  ], layoutBasis({ height: 330, xaxis: flexAs(lab), yaxis: { title: "%", range: [0, 102] } }), PL);
}

/* ================================================================== 3 · VERGELIJKEN */
async function schermVergelijken() {
  S.runs = (await api("/api/runs")).filter((r) => r.status === "klaar" && r.scenario_bestaat);   // resultaten van verwijderde scenario's niet tonen
  S.vergelijk = S.vergelijk.filter((id) => S.runs.find((r) => r.id === id));
  app.innerHTML = `
    <h2>Vergelijken</h2>
    <div class="kaart geel vglbalk">
      <label>Runs vergelijken <span class="eenheid">· 2 tot 4; de eerste gekozen run is de basis</span></label>
      <div class="vglrij">
        <div class="multikeuze" id="mk">
          <div class="mk-knop" id="mk-knop" role="button" tabindex="0" aria-haspopup="listbox" aria-expanded="false"></div>
          <div class="mk-paneel" id="mk-paneel" role="listbox" aria-multiselectable="true" hidden></div>
        </div>
        <button class="knop zwart" id="pdf" type="button" disabled title="A4-rapport van de gekozen runs">⬇ Rapport (PDF)</button>
      </div>
    </div>
    <div id="vgl" class="sectie"></div>`;
  const knop = $("#mk-knop"), paneel = $("#mk-paneel");
  const datum = (r) => `${r.gestart.slice(8, 10)}-${r.gestart.slice(5, 7)} ${r.gestart.slice(11, 16)}`;
  const open = (ja) => { paneel.hidden = !ja; knop.setAttribute("aria-expanded", String(ja)); };

  const tekenKeuze = () => {
    knop.innerHTML = (S.vergelijk.length
      ? S.vergelijk.map((id, i) => { const r = S.runs.find((x) => x.id === id);
          return `<span class="mk-chip" style="background:${K.runs[i]}"><b>${i + 1}</b> ${esc(r.scenario_naam)} <small>${datum(r)}</small><button type="button" data-weg="${id}" aria-label="Verwijder ${esc(r.scenario_naam)}">×</button></span>`; }).join("")
      : '<span class="eenheid">Kies runs…</span>') + '<span class="mk-pijl">▾</span>';
    // opties alleen bijwerken (niet opnieuw opbouwen), zodat de scrollpositie in de lijst blijft staan
    paneel.querySelectorAll(".mk-optie").forEach((o) => {
      const inp = o.querySelector("input"), pos = S.vergelijk.indexOf(inp.value), vol = S.vergelijk.length >= 4 && pos < 0;
      inp.checked = pos >= 0; inp.disabled = vol; o.classList.toggle("uit", vol);
      const nr = o.querySelector(".mk-nr");
      nr.textContent = pos >= 0 ? pos + 1 : ""; nr.style.background = pos >= 0 ? K.runs[pos] : "";
    });
  };
  paneel.innerHTML = S.runs.length ? S.runs.map((r) => `<label class="mk-optie"><input type="checkbox" value="${r.id}"><span class="mk-nr"></span>
      <span><span class="t">${esc(r.scenario_naam)}</span> <span class="d">${datum(r)}${r.nieuwste ? "" : " · eerdere run"}</span><br><span class="o">${esc(r.omschrijving || "")}</span></span></label>`).join("")
    : '<div class="leeg">Nog geen afgeronde runs.</div>';
  const wijzig = () => {
    tekenKeuze();
    $("#pdf").disabled = S.vergelijk.length < 2;
    if (S.vergelijk.length >= 2) toonVergelijking();
    else $("#vgl").innerHTML = '<div class="kaart leeg">Kies minstens twee runs in de balk hierboven.</div>';
  };

  // rapport: server maakt de PDF van de gekozen runs (in volgorde), browser slaat hem op
  $("#pdf").onclick = async () => {
    const k = $("#pdf"), tekst = k.textContent;
    k.disabled = true; k.innerHTML = '<span class="spinner"></span> Rapport maken…';
    try {
      const r = await fetch(`/api/rapport?runs=${encodeURIComponent(S.vergelijk.join(","))}`);
      if (!r.ok) throw new Error(await r.text());
      const naam = (r.headers.get("Content-Disposition") || "").match(/filename="(.+)"/)?.[1] || "vergelijking.pdf";
      const a = document.createElement("a");
      a.href = URL.createObjectURL(await r.blob()); a.download = naam;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 10000);
    } catch (e) {
      alert(`Rapport maken mislukt: ${e.message}`);
    } finally {
      k.textContent = tekst; k.disabled = S.vergelijk.length < 2;
    }
  };

  knop.onclick = (e) => {
    const weg = e.target.closest("[data-weg]");
    if (weg) { S.vergelijk = S.vergelijk.filter((id) => id !== weg.dataset.weg); wijzig(); return; }
    open(paneel.hidden);
  };
  knop.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(paneel.hidden); } };
  paneel.onchange = (e) => {
    const id = e.target.value;
    if (e.target.checked) { if (S.vergelijk.length < 4) S.vergelijk.push(id); } else S.vergelijk = S.vergelijk.filter((x) => x !== id);
    wijzig();
  };
  // sluiten bij klik buiten de keuzelijst of Escape (één keer registreren, werkt op de actuele lijst)
  if (!S.mkLuisteraars) {
    const sluit = () => { const p = $("#mk-paneel"); if (p) { p.hidden = true; $("#mk-knop").setAttribute("aria-expanded", "false"); } };
    document.addEventListener("click", (e) => { if (!e.target.closest("#mk")) sluit(); });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") sluit(); });
    S.mkLuisteraars = true;
  }
  wijzig();
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
  ["Aansluiting: grens WP's [kWe]", (k) => k.aansluiting.grens_kwe, 0, 0],
  ["Aansluiting: uren overschreden", (k) => k.aansluiting.uren_boven, -1, 0],
  ["Aansluiting: max. overschrijding [kWe]", (k) => k.aansluiting.max_overschrijding_kwe, -1, 0],
  ["Aansluiting: energie boven grens [kWh]", (k) => k.aansluiting.kwh_boven, -1, 0],
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
    <div class="kaart sectie"><h3>Standaarddag naast elkaar</h3>${info("Standaarddag", UITLEG.vdag(runs[0].waarden))}<div class="rij" style="margin-bottom:8px"><select id="vdagen" class="tekstveld" style="width:auto;min-width:260px"></select><span id="vdagtoel" class="eenheid"></span></div><div id="vdag" class="grafiek"></div></div>
    <div class="raster sectie" style="grid-template-columns:1fr 1fr">
      <div class="kaart"><h3>Maandpiek WP's in ontlaadvenster</h3>${info("Maandpiek", UITLEG.vmaand(runs[0].waarden))}<div id="vmaand" class="grafiek"></div></div>
      <div class="kaart"><h3>Flexibiliteitsenvelop</h3>${info("Flexibiliteitsenvelop", UITLEG.vflex())}<div id="vflex" class="grafiek"></div></div>
    </div>`;
  const vd = $("#vdagen");
  dagOpties(vd, runs[0].typedagen, false);
  vd.onchange = () => { const d = runs[0].typedagen[vd.value]; $("#vdagtoel").textContent = d.toelichting; tekenVergelijkDag(runs, d.datum, d.dagen); };
  vd.onchange();

  const jaren = await Promise.all(runs.map((r) => api(`/api/runs/${r.id}/jaar`)));
  Plotly.react("vmaand", jaren.map((j, i) => ({ type: "bar", x: j.maand.maand.map((m) => MND[m - 1]), y: j.maand.piek_venster, name: runs[i].scenario_naam, marker: { color: K.runs[i] },
    text: j.maand.piek_venster.map((v) => v === null ? "" : nl(v)), textposition: "outside", cliponaxis: false, textfont: { size: 10 } })),
    layoutBasis({ height: 340, barmode: "group", yaxis: { title: "kWe" } }), PL);
  Plotly.react("vflex", runs.map((r, i) => ({ x: r.flex.map((x) => x.reductie_kwe === "alles" ? "uit" : String(x.reductie_kwe)), y: r.flex.map((x) => x.uren_volledig_pct), name: r.scenario_naam, line: { color: K.runs[i], width: 3 } })),
    layoutBasis({ height: 340, xaxis: flexAs(runs[0].flex.map((x) => x.reductie_kwe === "alles" ? "uit" : String(x.reductie_kwe))), yaxis: { title: "% vensteruren volledig", range: [0, 102] } }), PL);
}

async function tekenVergelijkDag(runs, datum, dagen = 1) {
  const data = await Promise.all(runs.map((r) => api(`/api/runs/${r.id}/dag?datum=${datum}&dagen=${dagen}`)));
  const t = data[0].t_lokaal;
  const vens = data[0].congestievenster.map((v) => v === true || v === "True");
  const sporen = [];
  data.forEach((d, i) => {
    const kleur = K.runs[i], naam = runs[i].scenario_naam;
    sporen.push({ x: d.t_lokaal, y: d.el, name: naam, legendgroup: naam, line: { color: kleur, width: 3, shape: "hv" }, yaxis: "y" });
    sporen.push({ x: d.t_lokaal, y: d.buf_ht.map((v, j) => v + d.buf_lt[j] - d.laad[j]), name: naam + " · buffer", legendgroup: naam, showlegend: false, line: { color: kleur, width: 2, shape: "hv" }, yaxis: "y2" });
    sporen.push({ x: d.t_lokaal, y: d.soc.map((v) => v * 100), name: naam + " · vulling", legendgroup: naam, showlegend: false, line: { color: kleur, width: 2, dash: "dot" }, yaxis: "y3" });
  });
  const grenzen = [...new Set(runs.map((r) => r.kpi.aansluiting?.grens_kwe).filter((g) => g))];
  grenzen.forEach((g) => {
    const i = runs.findIndex((r) => r.kpi.aansluiting?.grens_kwe === g);
    sporen.push(grensSpoor(t, g, grenzen.length > 1 ? K.runs[i] : "#C00A35", `aansluiting ${nl(g)} kWe${grenzen.length > 1 ? ` (run ${i + 1})` : ""}`));
  });
  const vp = panelen([0.36, 0.3, 0.24], ["<b>Elektrisch vermogen warmtepompen</b> [kWe]", "<b>Buffer ontladen (+) / laden (−)</b> [kW]",
    "<b>Buffervulling</b> [%] · geel = ontlaadvenster"], 0.11);
  legendaPerPaneel(sporen, { y: 1, y2: 2, y3: 3 });   // runkleuren staan bij paneel 1; paneel 2 en 3 gebruiken dezelfde kleuren
  Plotly.react("vdag", sporen, layoutBasis({
    height: 760, showlegend: true, shapes: vensterVormen(t, vens), margin: { l: 60, r: 20, t: 60, b: 50 }, xaxis: { ...TIJDAS, anchor: "y3" },
    yaxis: { ...vp.assen.yaxis, rangemode: "tozero" }, yaxis2: { ...vp.assen.yaxis2, zeroline: true, zerolinecolor: "#9A9A9A" },
    yaxis3: { ...vp.assen.yaxis3, range: [0, 105], tickvals: [0, 50, 100] }, ...vp.legendes, annotations: vp.annotations,
  }), PL);
}

route();
