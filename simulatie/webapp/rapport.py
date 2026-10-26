"""A4-rapport (PDF) dat 2 tot 4 simulatieruns met elkaar vergelijkt.

Opbouw: samenvatting en kerncijfers · pieken en flexibiliteit · de koude reeks · toelichting en instellingen.
Teksten en conclusies worden uit de runs afgeleid, zodat het rapport voor elke combinatie van runs klopt.
"""
import io
import json
import os
from datetime import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
import yaml  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.enums import TA_RIGHT  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import ParagraphStyle  # noqa: E402
from reportlab.lib.units import mm  # noqa: E402
from reportlab.pdfbase import pdfmetrics  # noqa: E402
from reportlab.pdfbase.ttfonts import TTFont  # noqa: E402
from reportlab.platypus import (CondPageBreak, Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer,  # noqa: E402
                                Table, TableStyle)

from botu_sim.kpi import max_vermogen  # noqa: E402
from . import schema  # noqa: E402
from .rekenen import dag_backup, nacht, vensterdagen  # noqa: E402

LOGO = os.path.join(os.path.dirname(__file__), "static/img/uu-logo.png")
RUNKLEUR = ["#001240", "#C00A35", "#24A793", "#F3965E"]     # gelijk aan de webapp
GEEL, ZWART, ROOD, GROEN = "#FFCD00", "#000000", "#C00A35", "#1E7A46"
GRIJS_1, GRIJS_2, TEKST_2 = "#F2F2F2", "#D9D9D9", "#5A5A5A"
MND = schema.MAANDEN
DAG = ["ma", "di", "wo", "do", "vr", "za", "zo"]
VENSTER_LEEG = 0.5   # kWe; daaronder telt een uur als "WP's uit"

# ------------------------------------------------------------------ lettertypen (DejaVu: volledige Unicode, meegeleverd met matplotlib)
_FONTS = os.path.join(os.path.dirname(matplotlib.__file__), "mpl-data/fonts/ttf")
for naam, bestand in (("Sans", "DejaVuSans.ttf"), ("Sans-B", "DejaVuSans-Bold.ttf"), ("Serif-B", "DejaVuSerif-Bold.ttf")):
    pdfmetrics.registerFont(TTFont(naam, os.path.join(_FONTS, bestand)))
pdfmetrics.registerFontFamily("Sans", normal="Sans", bold="Sans-B", italic="Sans", boldItalic="Sans-B")
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8, "axes.edgecolor": "#8A8A8A", "axes.linewidth": 0.6,
                     "axes.spines.top": False, "axes.spines.right": False, "xtick.color": TEKST_2, "ytick.color": TEKST_2,
                     "axes.labelcolor": TEKST_2, "axes.grid": True, "grid.color": "#E6E6E6", "grid.linewidth": 0.5,
                     "axes.axisbelow": True, "legend.frameon": False})

ST = {
    "titel": ParagraphStyle("titel", fontName="Serif-B", fontSize=20, leading=25, spaceAfter=2),
    "sub": ParagraphStyle("sub", fontName="Sans", fontSize=10, leading=14, textColor=TEKST_2, spaceAfter=10),
    "h2": ParagraphStyle("h2", fontName="Serif-B", fontSize=13, leading=17, spaceBefore=8, spaceAfter=4),
    "tekst": ParagraphStyle("tekst", fontName="Sans", fontSize=9, leading=13),
    "klein": ParagraphStyle("klein", fontName="Sans", fontSize=7.5, leading=10, textColor=TEKST_2),
    "bullet": ParagraphStyle("bullet", fontName="Sans", fontSize=8.8, leading=12, leftIndent=10, bulletIndent=0, spaceAfter=2.5),
    "cel": ParagraphStyle("cel", fontName="Sans", fontSize=8, leading=10),
    "celr": ParagraphStyle("celr", fontName="Sans", fontSize=8, leading=10, alignment=TA_RIGHT),
    "kop": ParagraphStyle("kop", fontName="Sans-B", fontSize=8, leading=10, textColor=colors.white),
    "kopr": ParagraphStyle("kopr", fontName="Sans-B", fontSize=8, leading=10, textColor=colors.white, alignment=TA_RIGHT),
}
BREED = A4[0] - 36 * mm


def nl(v, d=0):
    """Nederlandse notatie: 1.234,5."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "–"
    s = f"{v:,.{d}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def dag_label(datum):
    t = pd.Timestamp(datum)
    return f"{DAG[t.weekday()]} {t.day}-{t.month}"


# ------------------------------------------------------------------ data per run
def laad_run(map_):
    meta = json.loads((map_ / "meta.json").read_text())
    cfg = yaml.safe_load((map_ / "config.yaml").read_text())
    u = pd.read_csv(map_ / "uurdata.csv", parse_dates=["t_lokaal"])
    u["venster"] = u["congestievenster"].astype(str).eq("True")
    return {
        "map": map_, "meta": meta, "cfg": cfg, "u": u, "w": meta["waarden"],
        "kpi": json.loads((map_ / "kpi.json").read_text()),
        "flex": json.loads((map_ / "flex.json").read_text()),
        "typedagen": json.loads((map_ / "typedagen.json").read_text()),
        "vd": vensterdagen(u), "max": max_vermogen(cfg),
        "e_max_mwh": cfg["buffer"]["volume_m3"] * 1.163 * (cfg["buffer"]["t_laad_c"] - cfg["buffer"]["t_retour_c"]) / 1000,
    }


def dagtypen(r1):
    """Koude periode en gemiddelde dagen uit de typedagen van run 1 (met vaste terugval)."""
    td = {d["id"]: d for d in r1["typedagen"]}
    koud = td.get("koude_periode", {"datum": "2001-01-15", "dagen": 4})
    return {"koud": (koud["datum"], koud.get("dagen", 4)),
            "herfst": td.get("herfst", {"datum": "2001-11-08"})["datum"],
            "winter": td.get("winter", {"datum": "2001-01-09"})["datum"]}


def backup_en_nachten(r, dt):
    u = r["u"]
    datums = [dt["herfst"], dt["winter"]] + [str((pd.Timestamp(dt["koud"][0]) + pd.Timedelta(days=i)).date()) for i in range(dt["koud"][1])]
    idx = [i for d in datums for i in u.index[(u["t_lokaal"] >= pd.Timestamp(d)) & (u["t_lokaal"] < pd.Timestamp(d) + pd.Timedelta(days=1))]]
    b = {x["datum"]: x for x in dag_backup(r["map"], u, idx)}
    cap = r["cfg"]["warmtepompen"]["ht"]["aantal"] * r["cfg"]["warmtepompen"]["ht"]["p_max_kw"]
    r["backup"] = {d: b.get(d) for d in datums}
    r["nachten"] = {d: nacht(u, d, cap) for d in datums}
    r["datums"] = datums


def strategie_tekst(w):
    if w.get("strategie.naam") == "congestie":
        s = "WP's uit in het venster" if w.get("strategie.congestie.alles_uit") else f"{nl(w.get('strategie.congestie.reductie_kwe'))} kWe verlagen in het venster"
        return s + (" (adaptief)" if w.get("strategie.congestie.adaptief") else "")
    return "Referentie: WP's volgen de vraag"


def venster_tekst(w):
    m, uu = w.get("congestie.maanden", []), w.get("congestie.uren_lokaal", [8, 17])
    mtxt = f"{MND[m[0] - 1]}–{MND[m[-1] - 1]}" if m else ""
    return f"{'werkdagen' if w.get('congestie.alleen_werkdagen') else 'alle dagen'} {uu[0]:02d}–{uu[1]:02d} h, {mtxt}"


# ------------------------------------------------------------------ grafieken
def figuur(fig, breedte_mm):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=220, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    img = Image(buf)
    schaal = breedte_mm * mm / img.imageWidth
    img.drawWidth, img.drawHeight = img.imageWidth * schaal, img.imageHeight * schaal
    return img


def fig_pieken(runs, maanden):
    fig, (a, b) = plt.subplots(1, 2, figsize=(7.2, 2.6), gridspec_kw={"width_ratios": [2.2, 1]})
    n, bw = len(runs), 0.8 / len(runs)
    for i, r in enumerate(runs):
        p = r["u"][r["u"]["venster"]].groupby(r["u"]["t_lokaal"].dt.month)["el"].max()
        ys = [p.get(m, 0.0) for m in maanden]
        xs = [j + (i - (n - 1) / 2) * bw for j in range(len(maanden))]
        a.bar(xs, ys, bw * 0.92, color=RUNKLEUR[i], label=r["label"])
    a.set_xticks(range(len(maanden)), [MND[m - 1] for m in maanden])
    a.set_ylabel("kWe")
    a.set_title("Hoogste WP-uur in het venster per maand", fontsize=8.5, loc="left", color=ZWART)
    a.legend(fontsize=7, loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=n)
    a.grid(axis="x", visible=False)
    smp = [r["kpi"]["elektra"]["som_maandpieken_venster_kwe"] for r in runs]
    b.bar(range(n), smp, 0.6, color=RUNKLEUR[:n])
    for i, y in enumerate(smp):
        b.text(i, y + max(smp) * 0.02, nl(y), ha="center", va="bottom", fontsize=7)
    b.set_xticks(range(n), [str(i + 1) for i in range(n)])
    b.set_xlabel("run")
    b.set_title("Σ maandpieken in het venster [kWe]", fontsize=8.5, loc="left", color=ZWART)
    b.grid(axis="x", visible=False)
    fig.tight_layout()
    return fig


def fig_flex(runs):
    fig, a = plt.subplots(figsize=(7.2, 2.3))
    for i, r in enumerate(runs):
        lab = ["uit" if x["reductie_kwe"] == "alles" else str(x["reductie_kwe"]) for x in r["flex"]]
        a.plot(lab, [x["uren_volledig_pct"] for x in r["flex"]], color=RUNKLEUR[i], lw=1.8, label=r["label"])
    lab = ["uit" if x["reductie_kwe"] == "alles" else str(x["reductie_kwe"]) for x in runs[0]["flex"]]
    a.set_xticks([j for j, x in enumerate(lab) if x == "uit" or int(x) % 20 == 0])
    laagste = min(x["uren_volledig_pct"] for r in runs for x in r["flex"])
    a.set_ylim(max(0, (laagste - 5) // 5 * 5), 101)   # inzoomen: de verschillen zitten meestal vlak onder 100 %
    a.set_xlabel("gevraagde verlaging in elk vensteruur [kWe]")
    a.set_ylabel("% vensteruren volledig")
    a.set_title("Flexibiliteitsenvelop", fontsize=8.5, loc="left", color=ZWART)
    a.legend(fontsize=7, loc="lower left")
    fig.tight_layout()
    return fig


def fig_koud(runs, start, dagen):
    a0 = pd.Timestamp(start)
    fig, (a, b) = plt.subplots(2, 1, figsize=(7.2, 3.6), sharex=True)
    for i, r in enumerate(runs):
        u = r["u"]
        s = u[(u["t_lokaal"] >= a0) & (u["t_lokaal"] < a0 + pd.Timedelta(days=dagen))]
        a.step(s["t_lokaal"], s["el"], where="post", color=RUNKLEUR[i], lw=1.3, label=r["label"])
        b.step(s["t_lokaal"], s["soc"] * 100, where="post", color=RUNKLEUR[i], lw=1.3)
    u = runs[0]["u"]
    s = u[(u["t_lokaal"] >= a0) & (u["t_lokaal"] < a0 + pd.Timedelta(days=dagen))]
    for ax in (a, b):   # ontlaadvenster van run 1
        aan = None
        for t, v in zip(s["t_lokaal"], s["venster"]):
            if v and aan is None:
                aan = t
            if not v and aan is not None:
                ax.axvspan(aan, t, color=GEEL, alpha=0.25, lw=0)
                aan = None
    a.set_ylabel("kWe")
    a.set_title("Elektrisch vermogen warmtepompen · geel = ontlaadvenster (run 1)", fontsize=8.5, loc="left", color=ZWART)
    a.legend(fontsize=7, loc="upper center", bbox_to_anchor=(0.5, -0.02), ncol=len(runs))
    b.set_ylabel("%")
    b.set_ylim(0, 105)
    b.set_title("Buffervulling", fontsize=8.5, loc="left", color=ZWART)
    ticks = [a0 + pd.Timedelta(days=d, hours=12) for d in range(dagen)]
    b.set_xticks(ticks, [dag_label(t) for t in ticks])
    fig.tight_layout()
    return fig


# ------------------------------------------------------------------ tabellen
def tabel(rijen, kolombreedtes, kopkleuren=None, rechts_vanaf=1, zebra=True):
    t = Table(rijen, colWidths=kolombreedtes, repeatRows=1)
    stijl = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(ZWART)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, colors.HexColor(GRIJS_2)),
        ("TOPPADDING", (0, 0), (-1, -1), 2.2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]
    for j, k in enumerate(kopkleuren or []):
        if k:
            stijl.append(("BACKGROUND", (j, 0), (j, 0), colors.HexColor(k)))
    if zebra:
        for i in range(2, len(rijen), 2):
            stijl.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#FAFAFA")))
    t.setStyle(TableStyle(stijl))
    return t


def P(t, s="cel"):
    return Paragraph(t, ST[s])


KPI = [  # label, functie(run) → waarde, richting (−1 = lager is beter), decimalen, eenheid
    ("Elektriciteit warmtepompen", lambda r: r["kpi"]["elektra"]["totaal_mwhe"], -1, 0, "MWhe"),
    ("SPF warmtepompen", lambda r: r["kpi"]["elektra"]["spf_wp"], 1, 2, ""),
    ("Piek elektrisch vermogen", lambda r: r["kpi"]["elektra"]["piek_kwe"], -1, 0, "kWe"),
    ("Vensterdagen volledig uit", lambda r: float((r["vd"]["uit"] == r["vd"]["uren"]).mean() * 100), 1, 0, "%"),
    ("Gem. uren uit per vensterdag", lambda r: float(r["vd"]["uit"].mean()), 1, 1, "h"),
    ("Gem. WP-vermogen in venster", lambda r: r["kpi"]["elektra"]["gem_kwe_congestievenster"], -1, 1, "kWe"),
    ("Max. WP-vermogen in venster", lambda r: r["kpi"]["elektra"]["max_kwe_congestievenster"], -1, 0, "kWe"),
    ("Σ maandpieken in venster", lambda r: r["kpi"]["elektra"]["som_maandpieken_venster_kwe"], -1, 0, "kWe"),
    ("Bufferverlies", lambda r: r["kpi"]["buffer"]["verlies_mwh"], -1, 1, "MWh"),
    ("Back-up ≥ 24 h (vol buffer)", lambda r: r["kpi"]["worstcase_met_condensor"][">= 24 h"], 1, 0, "%"),
    ("Pendeluren HT / LT", lambda r: r["kpi"]["bedrijf"]["ht_pendeluren"] + r["kpi"]["bedrijf"]["lt_pendeluren"], -1, 0, "h"),
    ("Energiekosten WP's", lambda r: r["kpi"]["kosten"]["inkoop_vast_eur"], -1, 0, "€"),
    ("kW-max WP's in venster (indicatie)", lambda r: r["kpi"]["kosten"]["indicatie_kwmax_venster_eur"], -1, 0, "€"),
    ("Warmtetekort", lambda r: r["kpi"]["warmte"]["tekort_mwh"], -1, 1, "MWh"),
]


def kpi_tabel(runs):
    n = len(runs)
    kop = [P("Kerncijfer", "kop")] + [P(f"{i + 1} · {r['meta']['scenario_naam']}", "kopr") for i, r in enumerate(runs)]
    rijen = [kop]
    for lab, f, richting, d, eenh in KPI:
        basis = f(runs[0])
        rij = [P(f"{lab}{f' [{eenh}]' if eenh else ''}")]
        for i, r in enumerate(runs):
            v = f(r)
            tekst = nl(v, d)
            if i > 0 and richting and basis and abs(v - basis) / abs(basis) >= 0.005:
                pct = (v - basis) / abs(basis) * 100
                kleur = GROEN if pct * richting > 0 else ROOD
                tekst += f' <font color="{kleur}" size="7">({"+" if pct > 0 else ""}{nl(pct)} %)</font>'
            if lab == "Pendeluren HT / LT":
                tekst = f"{nl(r['kpi']['bedrijf']['ht_pendeluren'])} / {nl(r['kpi']['bedrijf']['lt_pendeluren'])}"
            if lab == "Warmtetekort" and v > 0:
                tekst = f'<font color="{ROOD}"><b>{tekst}</b></font>'
            rij.append(P(tekst, "celr"))
        rijen.append(rij)
    w0 = 58 * mm
    return tabel(rijen, [w0] + [(BREED - w0) / n] * n, [None] + RUNKLEUR[:n])


# ------------------------------------------------------------------ tekst die uit de resultaten volgt
def samenvatting(runs, dt):
    uit = []
    basis = runs[0]["kpi"]["elektra"]["som_maandpieken_venster_kwe"]
    for i, r in enumerate(runs):
        e, vd, naam = r["kpi"]["elektra"], r["vd"], f"<b>{i + 1} · {r['meta']['scenario_naam']}</b>"
        heel = int((vd["uit"] == vd["uren"]).sum())
        delta = f" ({'+' if e['som_maandpieken_venster_kwe'] >= basis else '−'}{nl(abs(e['som_maandpieken_venster_kwe'] - basis) / basis * 100)} % t.o.v. run 1)" if i and basis else ""
        if r["w"].get("strategie.naam") == "congestie":
            uit.append(f"{naam}: WP's op {heel} van {len(vd)} vensterdagen het hele venster uit (gemiddeld {nl(vd['uit'].mean(), 1)} van "
                       f"{nl(vd['uren'].mean())} h). Σ maandpieken in het venster {nl(e['som_maandpieken_venster_kwe'])} kWe{delta}.")
        else:
            uit.append(f"{naam}: WP's volgen de vraag; gemiddeld {nl(e['gem_kwe_congestievenster'])} kWe in het venster, "
                       f"Σ maandpieken {nl(e['som_maandpieken_venster_kwe'])} kWe{delta}.")
    for i, r in enumerate(runs):
        t = r["kpi"]["warmte"]
        if t["tekort_mwh"] > 0:
            uren = r["u"][(r["u"]["tekort_ht"] + r["u"]["tekort_lt"]) > 0.01]
            dagen = sorted({dag_label(x) for x in uren["t_lokaal"].dt.date})
            uit.append(f'<font color="{ROOD}"><b>Let op, run {i + 1}:</b></font> {nl(t["tekort_mwh"], 1)} MWh warmtetekort in {t["tekort_uren"]} uur '
                       f"({', '.join(dagen)}). De HT-vraag is dan hoger dan de HT-WP's leveren en het buffer is leeg.")
    laatste = dt["koud"][0] if not runs[0]["datums"] else runs[0]["datums"][-1]
    res = [f"run {i + 1}: {r['backup'][laatste]['nu_h'] if r['backup'].get(laatste) else '–'} h" for i, r in enumerate(runs)]
    uit.append(f"<b>Koude reeks</b> ({dag_label(dt['koud'][0])} t/m {dag_label(laatste)}): werkelijke reserve om "
               f"{runs[0]['cfg']['congestie']['uren_lokaal'][0]:02d}:00 op de laatste dag · {' · '.join(res)}.")
    koud = runs[0]["datums"][2:-1]
    if koud:
        flexruns = [r for r in runs if r["w"].get("strategie.naam") == "congestie"] or runs   # referentie laadt weinig: buffer is al vol
        laad = [r["nachten"][d]["laden_mwh"] for r in flexruns for d in koud]
        vraag = [runs[0]["nachten"][d]["ht_vraag_kw"] for d in koud]
        cap = runs[0]["cfg"]["warmtepompen"]["ht"]["aantal"] * runs[0]["cfg"]["warmtepompen"]["ht"]["p_max_kw"]
        uit.append(f"<b>Bijladen 's nachts:</b> in de koude nachten is de HT-vraag gemiddeld {nl(min(vraag))}–{nl(max(vraag))} kW, "
                   f"bij {nl(cap)} kW HT-vermogen. Er gaat dan maar {nl(min(laad), 2)}–{nl(max(laad), 2)} MWh per nacht in het buffer, "
                   "ongeacht de buffergrootte: de reserve wordt vooral bepaald door de voorraad aan het begin van de reeks.")
    return uit


def instellingen_tabel(runs):
    """Instellingen die tussen de runs verschillen, plus de belangrijkste vaste."""
    altijd = ["strategie.naam", "buffer.volume_m3", "buffer.t_laad_c", "congestie.uren_lokaal", "congestie.maanden"]
    velden = {v["k"]: v for g in schema.GROEPEN for v in g["velden"]}
    keys = [k for k in velden if k in altijd or len({json.dumps(r["w"].get(k)) for r in runs}) > 1]

    def fmt(k, v):
        if k == "congestie.maanden" and isinstance(v, list) and v:
            return f"{MND[v[0] - 1]}–{MND[v[-1] - 1]}"
        if k == "congestie.uren_lokaal" and isinstance(v, list):
            return f"{v[0]:02d}–{v[1]:02d} h"
        if k == "strategie.naam":
            return dict(velden[k].get("opties", [])).get(v, v)
        if isinstance(v, bool):
            return "ja" if v else "nee"
        if isinstance(v, (int, float)):
            return nl(v, 0 if float(v).is_integer() else 2)
        return str(v)

    n = len(runs)
    rijen = [[P("Instelling", "kop")] + [P(f"run {i + 1}", "kopr") for i in range(n)]]
    for k in keys:
        f = velden[k]
        lab = f["label"] + (f" [{f['eenheid']}]" if f.get("eenheid") else "")
        verschil = len({json.dumps(r["w"].get(k)) for r in runs}) > 1
        rijen.append([P(f"<b>{lab}</b>" if verschil else lab)] + [P(fmt(k, r["w"].get(k)), "celr") for r in runs])
    w0 = 70 * mm
    return tabel(rijen, [w0] + [(BREED - w0) / n] * n, [None] + RUNKLEUR[:n])


# ------------------------------------------------------------------ opbouw
def maak_rapport(mappen):
    runs = [laad_run(m) for m in mappen]
    for i, r in enumerate(runs):
        r["label"] = f"{i + 1} · {r['meta']['scenario_naam']}"
    dt = dagtypen(runs[0])
    for r in runs:
        backup_en_nachten(r, dt)
    maanden = runs[0]["cfg"]["congestie"]["maanden"]
    nu = datetime.now()
    verhaal = []

    # pagina 1 — samenvatting en kerncijfers
    verhaal += [P("Vergelijking simulaties", "titel"),
                P(f"Warmtepompen en buffer · Botanische Tuinen UU · {len(runs)} runs · {nu.strftime('%d-%m-%Y')}", "sub")]
    rijen = [[P("", "kop"), P("Scenario", "kop"), P("Strategie", "kop"), P("Buffer", "kop"), P("Ontlaadvenster", "kop")]]
    for i, r in enumerate(runs):
        rijen.append([P(f'<font color="white"><b>{i + 1}</b></font>'), P(f"<b>{r['meta']['scenario_naam']}</b><br/>"
                      f'<font size="6.5" color="{TEKST_2}">{r["meta"]["id"]}</font>'), P(strategie_tekst(r["w"])),
                      P(f"{nl(r['cfg']['buffer']['volume_m3'])} m³ · {nl(r['e_max_mwh'], 1)} MWh"), P(venster_tekst(r["w"]))])
    t = tabel(rijen, [7 * mm, 52 * mm, 48 * mm, 30 * mm, BREED - 137 * mm], zebra=False)
    t.setStyle(TableStyle([("BACKGROUND", (0, i + 1), (0, i + 1), colors.HexColor(RUNKLEUR[i])) for i in range(len(runs))]))
    verhaal += [t, P("Samenvatting", "h2")]
    verhaal += [Paragraph(s, ST["bullet"], bulletText="•") for s in samenvatting(runs, dt)]
    verhaal += [P("Kerncijfers", "h2"), kpi_tabel(runs),
                Spacer(1, 3), P("Tussen haakjes het verschil met run 1; groen = beter, rood = slechter. kW-max is een indicatie: "
                                "de besparing telt alleen als de campuspiek in het venster valt.", "klein")]

    # pagina 2 — pieken en flexibiliteit
    verhaal += [PageBreak(), P("Piekvermogen in het ontlaadvenster", "h2"),
                P("Per maand het hoogste uur van het elektrisch vermogen van de warmtepompen samen binnen het ontlaadvenster, en de som "
                  "daarvan over de maanden. Dit is de WP-bijdrage die maximaal in de kW-max van de campus terechtkomt. "
                  "0 betekent dat de WP's in elk vensteruur van die maand uit stonden.", "tekst"),
                Spacer(1, 4), figuur(fig_pieken(runs, maanden), BREED / mm),
                P("Hoeveel kWe, hoe lang?", "h2"),
                P("Uitgaande van een referentierun met dezelfde installatie: welk deel van de vensteruren lukt een gevraagde verlaging "
                  "volledig, als het buffer de warmte levert en de HT-WP's buiten het venster bijladen. Het jaar wordt aan één stuk "
                  "doorgerekend, dus een half leeg buffer na een koude dag telt mee voor de volgende dag.", "tekst"),
                Spacer(1, 4), figuur(fig_flex(runs), BREED / mm)]
    flex_rij = [[P("Verlaging · % vensteruren / % dagen volledig", "kop")] + [P(f"run {i + 1}", "kopr") for i in range(len(runs))]]
    for R in (50, 100, "alles"):
        flex_rij.append([P("WP's uit" if R == "alles" else f"{R} kWe")] + [P(next(
            (f"{nl(x['uren_volledig_pct'])} % / {nl(x['dagen_heel_venster_pct'])} %" for x in r["flex"] if x["reductie_kwe"] == R), "–"), "celr")
            for r in runs])
    verhaal += [Spacer(1, 4), tabel(flex_rij, [62 * mm] + [(BREED - 62 * mm) / len(runs)] * len(runs), [None] + RUNKLEUR[:len(runs)])]

    # pagina 3 — koude reeks
    k0, kd = dt["koud"]
    uur0 = runs[0]["cfg"]["congestie"]["uren_lokaal"][0]
    verhaal += [PageBreak(), P(f"De koude reeks: {dag_label(k0)} t/m {dag_label(pd.Timestamp(k0) + pd.Timedelta(days=kd - 1))}", "h2"),
                P("De koudste aaneengesloten werkdagen van het jaar. Hier blijkt of het buffer tussen twee vensters weer vol genoeg "
                  "raakt.", "tekst"), Spacer(1, 4), figuur(fig_koud(runs, k0, kd), BREED / mm)]
    rij_kop = [P("Dag", "kop")] + [P(f"run {i + 1}", "kopr") for i in range(len(runs))]
    labels = {runs[0]["datums"][0]: "Gem. herfstdag", runs[0]["datums"][1]: "Gem. winterdag"}
    b_rijen = [rij_kop]
    for d in runs[0]["datums"]:
        cellen = []
        for r in runs:
            x = r["backup"].get(d)
            if not x:
                cellen.append(P("–", "celr"))
                continue
            kleur = ROOD if x["nu_h"] < 9 else ZWART
            cellen.append(P(f'<font color="{kleur}"><b>{x["nu_h"]} h</b></font><br/><font size="6.5" color="{TEKST_2}">'
                            f'vulling {nl(x["soc_pct"])} % · vol {x["vol_h"]} h</font>', "celr"))
        b_rijen.append([P(f"{labels.get(d, '')} {dag_label(d)}".strip())] + cellen)
    n_rijen = [[P("Nacht na (17–08 h)", "kop")] + [P(f"run {i + 1}", "kopr") for i in range(len(runs))]]
    for d in runs[0]["datums"]:
        n0 = runs[0]["nachten"][d]
        n_rijen.append([P(f"{labels.get(d, '')} {dag_label(d)}".strip() + f"<br/><font size='6.5' color='{TEKST_2}'>{nl(n0['t_buiten'], 1)} °C · HT-vraag {nl(n0['ht_vraag_kw'])} kW</font>")]
                       + [P(f"<b>{nl(r['nachten'][d]['laden_mwh'], 2)} MWh</b><br/><font size='6.5' color='{TEKST_2}'>"
                            f"vulling {nl(r['nachten'][d]['soc_start'])} → {nl(r['nachten'][d]['soc_eind'])} %</font>", "celr") for r in runs])
    w0 = 38 * mm
    verhaal += [KeepTogether([P(f"Back-up met alleen het buffer vanaf {uur0:02d}:00", "h2"),
                              P("Hoeveel uur dekt het buffer (met condensorwarmte) de volledige vraag als alle WP's aan het begin "
                                "van het venster uitgaan? Vetgedrukt de reserve met de werkelijke vulling uit de simulatie; daaronder "
                                "de vulling op dat moment en de reserve bij een vol buffer. Rood = korter dan het venster (9 h).", "tekst"),
                              Spacer(1, 4), tabel(b_rijen, [w0] + [(BREED - w0) / len(runs)] * len(runs), [None] + RUNKLEUR[:len(runs)])]),
                KeepTogether([P("Bijladen 's nachts", "h2"),
                              P("Warmte die de HT-warmtepompen in de nacht na de dag in het buffer laden, met de vulling van 17:00 "
                                "naar 08:00. Op koude nachten gaat vrijwel het volle HT-vermogen direct naar de kassen.", "tekst"),
                              Spacer(1, 4), tabel(n_rijen, [w0] + [(BREED - w0) / len(runs)] * len(runs),
                                                  [None] + RUNKLEUR[:len(runs)])])]

    # pagina 4 — toelichting
    mx = runs[0]["max"]
    uitleg = [
        ("Elektriciteit en SPF", "Verbruik van de drie warmtepompen over 8.760 uur, inclusief laden van het buffer; SPF = alle "
         "WP-warmte gedeeld door het WP-verbruik. Pompen, regeling en koelmachine tellen niet mee."),
        ("Piek elektrisch vermogen", f"Hoogste uurwaarde van de WP's samen. Het maximum dat de WP's kunnen vragen is "
         f"{nl(mx['totaal_kwe'])} kWe (HT {nl(mx['ht']['kwe'])} kWe bij {nl(mx['ht']['t_c'])} °C, LT {nl(mx['lt']['kwe'])} kWe bij "
         f"{nl(mx['lt']['t_c'])} °C; volgens het COP-model, aanname)."),
        ("Vensterdagen volledig uit", f"Aandeel werkdagen in de congestieperiode waarop het WP-vermogen in elk vensteruur onder "
         f"{nl(VENSTER_LEEG, 1)} kWe blijft."),
        ("Σ maandpieken in venster", "Som over de congestiemaanden van het hoogste WP-uur binnen het venster."),
        ("Back-up ≥ 24 h", "Jaarcijfer: aandeel van de 8.760 starturen waarop een vol buffer met alle WP's uit minstens 24 uur "
         "de volledige vraag dekt."),
        ("Kosten", "Energiekosten met het tarief uit het scenario; kW-max is een indicatie op basis van de maandpieken in het venster."),
        ("Warmtetekort", "Warmte die in een uur niet geleverd kan worden: de vraag is groter dan WP's plus buffer."),
    ]
    verhaal += [CondPageBreak(70 * mm), P("Toelichting op de kerncijfers", "h2")]
    verhaal += [Paragraph(f"<b>{a}.</b> {b}", ST["bullet"], bulletText="•") for a, b in uitleg]
    verhaal += [P("Instellingen", "h2"), P("Vetgedrukt: instellingen die tussen de runs verschillen.", "klein"), Spacer(1, 3),
                instellingen_tabel(runs),
                Spacer(1, 8), P("Model: uurstap over het NEN 5060-referentiejaar; COP = η · T<sub>c</sub>/(T<sub>c</sub> − T<sub>v</sub>) · "
                                "f(deellast); buffer volledig gelaagd; aanvoertemperatuur volgens stooklijn. Uitgangspunten projectteam "
                                "(werkwaarden; status bron / afgeleid / aanname in de webapp).", "klein")]

    uit = io.BytesIO()
    doc = SimpleDocTemplate(uit, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=24 * mm, bottomMargin=16 * mm,
                            title="Vergelijking simulaties · Botanische Tuinen UU", author="Simulatiemodel BoTu (DEOG Fase 5)")

    def pagina(c, d):
        c.saveState()
        if os.path.exists(LOGO):
            c.drawImage(LOGO, 18 * mm, A4[1] - 15 * mm, width=30 * mm, height=30 * mm * 601 / 1897, mask="auto")
        c.setFont("Sans", 7.5)
        c.setFillColor(colors.HexColor(TEKST_2))
        c.drawRightString(A4[0] - 18 * mm, A4[1] - 11 * mm, "TVVL · Datagedreven energieoptimalisatie — Fase 5")
        c.drawRightString(A4[0] - 18 * mm, A4[1] - 14.5 * mm, "Warmtepompen en buffer · Botanische Tuinen")
        c.setStrokeColor(colors.HexColor(GEEL))
        c.setLineWidth(1.6)
        c.line(18 * mm, A4[1] - 18 * mm, A4[0] - 18 * mm, A4[1] - 18 * mm)
        c.drawString(18 * mm, 9 * mm, f"Simulatiemodel BoTu · gegenereerd {nu.strftime('%d-%m-%Y %H:%M')}")
        c.drawRightString(A4[0] - 18 * mm, 9 * mm, f"pagina {d.page}")
        c.restoreState()

    doc.build(verhaal, onFirstPage=pagina, onLaterPages=pagina)
    return uit.getvalue()
