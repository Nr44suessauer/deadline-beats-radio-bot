#!/usr/bin/env python3
"""Baut ANHANG/n8n-oberflaeche.html: der Bot in der n8n-Oberfläche.

Aufbau: je Ablauf eine Übersicht (Gesamtbild) und darunter **je Modul ein Bild**,
dazu die Erklärung des Abschnitts und die Knotenliste. Jedes Bild lässt sich im
Dokument anklicken und dann zoomen (Mausrad, Knöpfe, Ziehen, Esc).

Die Bilder entstehen mit `modulbilder-plan.py` (Plan), der Aufnahme in der
laufenden Oberfläche (Kacheln) und `bilder-stitch.py` (Zusammensetzen).

Aufruf: python3 werkzeuge/n8n-doku-bauen.py
"""
from __future__ import annotations

import base64
import datetime as dt
import html
import json
import re
from pathlib import Path

HIER = Path(__file__).resolve().parent
ZIEL_ORDNER = HIER.parent.parent / "ANHANG"
BILDER = ZIEL_ORDNER / "bilder"
MODULE = BILDER / "module"
PLAN = BILDER / "modulplan.json"
AUSGABE = ZIEL_ORDNER / "n8n-oberflaeche.html"

BAUZEIT = dt.datetime.now().strftime("%d.%m.%Y um %H:%M")

# Erklärung je Modul (Schluessel = Name des Rahmens im Ablauf)
TEXTE = {
    # --- Agent -----------------------------------------------------------
    "Notiz Doku": "Diese Notiz steht in der Oberfläche über der Fläche: was der Ablauf "
                  "ist, wie er geändert und geprüft wird und welche Dateien ihn beschreiben.",
    "Notiz Uebersicht": "Die Legende: die Farben der Rahmen entsprechen den Stufen — "
                        "gelb = Befehle erkennen, blau = planen, rot = ausführen, "
                        "violett = prüfen und antworten, grün = Dienste und Postfach.",
    "Notiz Eingang": "Zwei Eingänge (Telegram und Test-Eingang) laufen in dieselbe "
                     "Nachrichtenaufbereitung. Danach prüft <code>Zugang</code>, ob der "
                     "Absender der Betreiber ist; die kurzen Wege antworten über "
                     "<code>Senden (Kurzmeldung)</code>, ohne das Modell zu bemühen.",
    "Notiz Sprachnachricht": "Sprachnachrichten bekommen einen eigenen Zweig oben: Datei "
                             "holen, herunterladen, auf der GPU in Text wandeln "
                             "(faster-whisper) und den erkannten Text weiterreichen. Ist "
                             "nichts zu verstehen, gibt es eine kurze Rückfrage.",
    "Notiz Analyse": "Stufe 0 und 1: Zuerst erkennen feste Regeln einfache Befehle "
                     "(Titelwunsch, skip, Status, Überblick, Postfachfrage) — das kostet "
                     "keine Modellzeit. Erst wenn nichts passt, plant das Sprachmodell und "
                     "<code>Befehle lesen</code> macht daraus die Befehlsliste.",
    "Notiz Ausfuehrung": "Stufe 2 ist eine Schleife: jeder Befehl wird der Reihe nach "
                         "abgearbeitet — Musik über den Dienstweg, Steuerbefehle über feste "
                         "Adressen, alles andere über den Agenten mit seinen Werkzeugen. "
                         "Sonderfälle hängen an eigenen Weichen: Postfach, Themen-Überblick "
                         "und der Ersatzweg ohne Modell.",
    "Notiz Pruefung": "Stufe 3: das Ergebnis wird geprüft (hat jeder Befehl geliefert, was "
                      "er sollte?), bei Bedarf nachgefasst (bis zu zwei Runden) und zuletzt "
                      "die Antwort gebaut, die im Chat erscheint.",
    "Notiz Dienste": "Die Dienste-Wege in einem Bereich: Wiedergabelisten (anlegen, füllen, "
                     "starten, löschen) und Meldungen (ansagen, verwerfen). Beides läuft "
                     "über den Dienst <code>radio-tts</code>; <code>Dienst Antwort</code> "
                     "sammelt die Rückgabe ein.",
    "Notiz Postfach": "Das Postfach: alle fünf Minuten holt der Zeitplan neue Meldungen und "
                      "legt sie als Karte mit Knöpfen vor. <code>Meldung anbieten</code> "
                      "merkt sie als angeboten — kein zweites Angebot für dieselbe Meldung.",
    "Notiz Werkzeuge": "Die acht Werkzeugknoten des Agenten. Jeder zeigt auf einen eigenen "
                       "Ablauf (Radio, AzuraCast, Meldungen) — so bleibt der Hauptablauf "
                       "lesbar und die Werkzeuge sind einzeln prüfbar.",
    # --- Werkzeug - Radio ------------------------------------------------
    "Notiz W Weichen": "Der Eingang des Werkzeugs: <code>Richtung?</code> entscheidet "
                       "zwischen Stimmungswunsch, Titelsuche und reinem Zustand.",
    "Notiz W Richtung": "Richtungswünsche („was Peppiges“, „90er“) gehen an den "
                        "Katalogdienst; die Vorschläge kommen als Auswahlliste zurück.",
    "Notiz W Suche": "Die Titelsuche fragt zuerst den Katalogdienst (unscharf, "
                     "tippfehlertolerant) und dann die Volltextsuche des Senders; "
                     "<code>Treffer aufbereiten</code> führt beide Listen zusammen.",
    "Notiz W Status": "Der Zustand: laufender Titel, danach, Hörerzahl — aufbereitet als "
                      "kurzer Text.",
    "Notiz W Abspielen": "Der Abspielweg: Warteschlange leeren, dann sofort eintragen oder "
                         "danach eintragen. Genau ein Weg wird genommen, je nach Wunsch.",
    "Notiz W Ausgabe": "Der Ausgabeknoten: hier endet der Werkzeugablauf und gibt das "
                       "Ergebnis an den Agenten zurück.",
    # --- Werkzeug - AzuraCast -------------------------------------------
    "Notiz AZ Weichen": "Der Eingang: Adresse nachschlagen, Schnittstelle aufrufen oder "
                        "einen Überblick geben.",
    "Notiz AZ Adressen": "Die Adressen kommen aus der Beschreibung der Sendeschnittstelle "
                         "(263 Endpunkte) — das Modell muss keine Adresse raten.",
    "Notiz AZ Aufruf": "Der Aufruf: <code>Wache</code> schützt vor gefährlichen Aufrufen, "
                       "<code>Nur lesen?</code> trennt Lesen und Schreiben, und ein "
                       "Trockenlauf zeigt, was passieren würde.",
    "Notiz AZ Ueberblick": "Der Überblick sammelt Anlagen, Zustand und Wiedergabelisten mit "
                           "Titelzahl in einem Text.",
    # --- Werkzeug - Meldungen -------------------------------------------
    "Notiz M Weichen": "Der Eingang: Recherche holen, sprechen oder das Postfach bedienen.",
    "Notiz M Recherche": "Die Recherche fragt den Dienst (Wetter, Nachrichten, Feeds, "
                         "Themen-Überblick) und legt das Ergebnis als Meldung ab.",
    "Notiz M Ansage": "Sprechen: freier Text oder eine abgelegte Meldung — beides geht über "
                      "den DJ-Hafen in den laufenden Sendebetrieb.",
    "Notiz M Postfach": "Das Postfach: Meldung verwerfen, Sprechtext ansehen oder offene "
                        "Meldungen auflisten.",
    "Notiz M Ausgabe": "Der Ausgabeknoten des Werkzeugs.",
    # --- Archiv ----------------------------------------------------------
    "Notiz Eingaenge": "Drei Startwege (von Hand, Formular, Webhook) laufen in dieselbe "
                       "Kette.",
    "Notiz Kontext": "Was läuft gerade, und was ist zuletzt passiert? Das ist die Grundlage "
                     "für den Moderationstext.",
    "Notiz Text und Stimme": "Aus dem Kontext wird ein Sprechtext (Modell), der gesäubert "
                             "und dann von Piper gesprochen wird.",
    "Notiz Ausgabe": "Entweder live sprechen (unterbricht kurz) oder als Titel hochladen.",
    "Notiz Nachverfolgung": "Nach dem Hochladen: warten, den Titel im Archiv finden, den "
                            "Wunsch zuordnen und abgeben.",
    "Notiz Alte Hilfsmittel": "Reste der ersten Fassung — nicht angeschlossen, nur zur "
                              "Erinnerung.",
    # --- Konfiguration - alle Werte --------------------------------------
    "Notiz Zentrale": "Die Zentrale des Bots: der Knoten <code>Werte</code> hält alle "
                      "Adressen, Schlüssel und Aufgabentexte an EINER Stelle. Geändert "
                      "wird nur dieser Code-Knoten — speichern genügt, kein Neustart.",
    # --- Stimmen aus Filmen ----------------------------------------------
    "Hinweis 214": "Der Start: das Formular <code>…/form/DEIN-WEBHOOK-PFAD</code> oder "
                   "der Webhook nehmen Serie und Auftragsnamen entgegen.",
    "Hinweis 566": "Die Suche: <code>/finden</code> findet Serie oder Film in den "
                   "Bibliotheken, <code>/extrahieren</code> startet den Auftrag beim "
                   "Stimmen-Dienst (Port 8890).",
    "Hinweis 132": "Warten und melden: die Schleife fragt <code>/job</code>, bricht nach "
                   "60 Minuten ab (der Auftrag läuft im Container weiter) und schickt "
                   "Ergebnis oder Fehler per Telegram.",
}

ABLAEUFE = [
    ("RadioAgentBot", "Radio - Telegram-Agent", "in Betrieb · 83 Knoten in 10 Modulen"),
    ("RadioWerkzeug", "Werkzeug - Radio", "in Betrieb · 17 Knoten in 7 Modulen"),
    ("AzuraWerkzeug", "Werkzeug - AzuraCast", "in Betrieb · 17 Knoten in 5 Modulen"),
    ("MeldungenWerkzeug", "Werkzeug - Meldungen", "in Betrieb · 14 Knoten in 6 Modulen"),
    ("Konfiguration", "Konfiguration - alle Werte", "in Betrieb · 2 Knoten in 2 Modulen"),
    ("StimmenBot", "Stimmen aus Filmen", "in Betrieb · 20 Knoten in 3 Modulen"),
    ("bjFSfXGqpLg7AAXw", "Radio - AI-Moderator", "Archiv · 19 Knoten in 7 Modulen"),
]


def einbetten(pfad: Path) -> str:
    return base64.b64encode(pfad.read_bytes()).decode("ascii")


def bild_html(datei: str, beschriftung: str, klasse: str = "modul") -> str:
    pfad = MODULE / datei
    if not pfad.exists():
        return f'<p class="fehlt">Bild fehlt: {datei}</p>'
    # alt-Attribut maskieren (Anfuehrungszeichen in Beschriftungen sprengen sonst Tags)
    return (f'<figure class="{klasse}"><img alt="{html.escape(beschriftung, quote=True)}" loading="lazy" '
            f'src="data:image/png;base64,{einbetten(pfad)}">'
            f'<figcaption>{html.escape(beschriftung)}</figcaption></figure>')


def tabelle(zeilen: list[tuple[str, str]], koepfe=("Vorgang", "Befehl")) -> str:
    kopf = "".join(f"<th>{k}</th>" for k in koepfe)
    inhalt = "".join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in zeilen)
    return f'<table><thead><tr>{kopf}</tr></thead><tbody>{inhalt}</tbody></table>'


plan = json.loads(PLAN.read_text(encoding="utf-8"))
teile: list[str] = []

teile.append(f"""
<p class="vorspann">Der Bot <strong>in der n8n-Oberfläche</strong>: für jeden Ablauf eine
Übersicht und darunter <strong>je Modul ein Bild</strong> mit der Erklärung des
Abschnitts. <span class="zoomhinweis">Jedes Bild lässt sich anklicken und dann zoomen
(Mausrad, Knöpfe, ziehen) — mit <kbd>Esc</kbd> schließt es sich wieder.</span>
Stand: {BAUZEIT}.</p>

<div class="kasten">
<h3>Wo die Oberfläche liegt</h3>
<ul>
  <li><strong>Adresse:</strong> <code>https://DEIN-N8N-HOST</code>
      (im Hausnetz <code>http://192.168.178.53:5678</code>)</li>
  <li><strong>Sieben Radio-Abläufe:</strong> Agent, drei Werkzeuge, Zentrale
      („Konfiguration – alle Werte“), „Stimmen aus Filmen“ und das Archiv (Kapitel unten)</li>
  <li><strong>Regel:</strong> in der Oberfläche nur <em>ansehen</em> — geändert wird der
      Plan in <code>NACHBAU/bau/agent-wf-bauen.py</code></li>
</ul>
</div>""")

for kennung, titel, zusatz in ABLAEUFE:
    daten = plan.get(kennung)
    if not daten:
        continue
    kapitel = [f'<p class="kennung">{zusatz}</p>']
    kapitel.append(bild_html(daten["gesamt"]["datei"],
                             "Gesamtbild: der ganze Ablauf auf einen Blick (anklicken zum Zoomen)",
                             klasse="gesamt"))
    kapitel.append('<table class="module"><thead><tr><th>Modul</th><th>Knoten</th>'
                   "</tr></thead><tbody>")
    for m in daten["module"]:
        anker = re.sub(r"[^a-z0-9]+", "-", m["rahmen"].lower()).strip("-")
        kapitel.append(f'<tr><td><a href="#{kennung}-{anker}">{m["titel"]}</a></td>'
                       f'<td>{len(m["knoten"])}</td></tr>')
    kapitel.append("</tbody></table>")
    for m in daten["module"]:
        anker = re.sub(r"[^a-z0-9]+", "-", m["rahmen"].lower()).strip("-")
        text = TEXTE.get(m["rahmen"], "")
        kapitel.append(f'<h3 id="{kennung}-{anker}">{m["titel"]}</h3>')
        if text:
            kapitel.append(f"<p>{text}</p>")
        kapitel.append(bild_html(m["datei"], f'Modul „{m["titel"]}“ (anklicken zum Zoomen)'))
        if m["knoten"]:
            kapitel.append('<p class="knoten">Enthält: '
                           + ", ".join(f"<code>{k}</code>" for k in m["knoten"]) + "</p>")
    teile.append(f'<h2>{titel}</h2>\n' + "\n".join(kapitel))

teile.append(f"""<h2>Notizen und Dokumentation in der Oberfläche</h2>
<p>Jeder Ablauf erklärt sich selbst: <strong>Rahmen</strong> mit Überschrift und
Erklärsatz, eine <strong>Notiz an jedem Knoten</strong>, eine
<strong>Dokumentations-Notiz</strong> oben (was der Ablauf ist, wie man ihn ändert und
prüft, welche Dateien ihn beschreiben) und bei alten Abläufen eine
<strong>Altfassung-Notiz</strong>.</p>
{bild_html("modul-radio-telegram-agent-10.png", "Die Dokumentations-Notiz des Agenten")}
{bild_html("modul-radio-telegram-agent-09.png", "Die Legende (Übersichts-Notiz) erklärt die Farben der Bereiche")}

<h2>Und wenn man etwas ändern will?</h2>
<p><strong>Nicht</strong> in der Oberfläche klicken: Anordnung, Rahmen und Notizen
entstehen aus dem Bauwerkzeug; ein Klick in n8n wäre beim nächsten Einspielen weg.</p>
{tabelle([
    ("Ablauf ändern", "<code>agent-patchen.sh --aufraeumen</code> → <code>agent-einspielen-nur.sh /tmp/radio-agent-neu.json</code> → <code>docker restart n8n</code>"),
    ("Anordnung prüfen", "<code>python3 werkzeuge/anordnung-pruefen.py NACHBAU/ablaeufe-laufend/*.json</code> (Ziel: 0 Befunde)"),
    ("Bilder neu aufnehmen", "<code>modulbilder-plan.py</code> → Kacheln aufnehmen → <code>bilder-stitch.py</code> → <code>n8n-doku-bauen.py</code>"),
    ("Fassung sichern", "<code>bash werkzeuge/fassung-sichern.sh &lt;name&gt; [beschreibung.md]</code>"),
])}""")

seiten = "\n".join(teile)
anzahl = sum(len(v["module"]) for v in plan.values())

html = f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Der Bot in der n8n-Oberfläche</title>
<style>
  :root {{ color-scheme: dark; }}
  body {{ margin: 0; padding: 0 0 4rem; background: #14161b; color: #dfe3ea;
         font: 16px/1.65 "Segoe UI", system-ui, sans-serif; }}
  header {{ padding: 2.6rem 2rem 1.6rem; background: linear-gradient(180deg,#1d2027,#181b21);
            border-bottom: 1px solid #2c313b; }}
  header h1 {{ margin: 0 0 .4rem; font-size: 2rem; }}
  header p {{ margin: 0; color: #9aa4b2; }}
  main {{ max-width: 1120px; margin: 0 auto; padding: 0 1.5rem; }}
  h2 {{ margin: 3rem 0 .8rem; font-size: 1.4rem; color: #ff7a45;
        border-bottom: 1px solid #2c313b; padding-bottom: .4rem; }}
  h3 {{ margin: 2.2rem 0 .5rem; font-size: 1.1rem; color: #ffb08a; }}
  p {{ margin: .7rem 0; }}
  ul, ol {{ margin: .6rem 0 .6rem 1.2rem; padding: 0; }}
  code {{ background: #23272f; padding: .1rem .35rem; border-radius: 4px;
          font: .87em/1.4 "Cascadia Mono", ui-monospace, monospace; color: #ffcb9a; }}
  kbd {{ background: #23272f; border: 1px solid #3a4049; border-radius: 4px;
         padding: 0 .3rem; font-size: .85em; }}
  figure {{ margin: 1rem 0 1.6rem; }}
  figure img {{ width: 100%; height: auto; display: block; border: 1px solid #2c313b;
                border-radius: 10px; background: #101216; cursor: zoom-in; }}
  figure.gesamt img {{ border-color: #3d4657; }}
  figcaption {{ margin-top: .45rem; font-size: .9rem; color: #9aa4b2; }}
  .zoomhinweis {{ color: #ffb08a; }}
  .kennung {{ color: #9aa4b2; font-size: .92rem; margin: .2rem 0 .6rem; }}
  .knoten {{ color: #9aa4b2; font-size: .9rem; }}
  table {{ width: 100%; border-collapse: collapse; margin: 1rem 0; font-size: .92rem; }}
  table.module {{ margin: 1rem 0 2rem; }}
  th, td {{ text-align: left; padding: .45rem .6rem; border-bottom: 1px solid #262b34;
            vertical-align: top; }}
  th {{ background: #1d2027; color: #cfd6e0; font-weight: 600; }}
  a {{ color: #7fb2ff; }}
  .kasten {{ background: #1b1f26; border: 1px solid #2c313b; border-left: 4px solid #ff7a45;
             border-radius: 8px; padding: .8rem 1.1rem; margin: 1.2rem 0; }}
  .vorspann {{ font-size: 1.05rem; }}
  .fehlt {{ color: #ff6b6b; }}
  footer {{ max-width: 1120px; margin: 3rem auto 0; padding: 1rem 1.5rem;
            color: #7c8798; font-size: .88rem; border-top: 1px solid #2c313b; }}
  #zoom {{ position: fixed; inset: 0; background: #0b0d11ee; display: none;
           z-index: 50; overflow: hidden; cursor: grab; }}
  #zoom.offen {{ display: block; }}
  #zoom img {{ position: absolute; transform-origin: 0 0; border: 1px solid #2c313b;
               border-radius: 8px; background: #101216; }}
  #zoomleiste {{ position: fixed; bottom: 1rem; left: 50%; transform: translateX(-50%);
                 background: #1d2027ee; border: 1px solid #2c313b; border-radius: 999px;
                 padding: .4rem .6rem; display: flex; gap: .4rem; align-items: center; }}
  #zoomleiste button {{ background: #262b34; color: #dfe3ea; border: 1px solid #3a4049;
                        border-radius: 8px; padding: .3rem .7rem; cursor: pointer;
                        font-size: .95rem; }}
  #zoomleiste button:hover {{ background: #313846; }}
  #zoomtitel {{ color: #9aa4b2; font-size: .85rem; max-width: 44vw; overflow: hidden;
                text-overflow: ellipsis; white-space: nowrap; }}
</style>
</head>
<body>
<header>
  <h1>Der Bot in der n8n-Oberfläche</h1>
  <p>{anzahl} Module in {len(plan)} Abläufen · ein Bild je Modul, anklickbar zum Zoomen · {BAUZEIT}</p>
</header>
<main>
{seiten}
</main>
<footer>
  <p>Erzeugt von <code>werkzeuge/n8n-doku-bauen.py</code> aus den Modulbildern in
  <code>ANHANG/bilder/module/</code> (Plan: <code>modulbilder-plan.py</code>, Aufnahme in
  der laufenden Oberfläche, Zusammensetzen: <code>bilder-stitch.py</code>).</p>
  <p>Am Bot wurde dabei nichts geändert; Knotenlisten: <code>ANHANG/ANORDNUNG.md</code>.</p>
</footer>

<div id="zoom"><img id="zoombild" alt=""><div id="zoomleiste">
  <span id="zoomtitel"></span>
  <button id="zr">−</button><button id="zp">+</button>
  <button id="z1">1:1</button><button id="zen">einpassen</button><button id="zx">schließen</button>
</div></div>
<script>
(function () {{
  const huelle = document.getElementById('zoom');
  const bild = document.getElementById('zoombild');
  const titel = document.getElementById('zoomtitel');
  let s = 1, x = 0, y = 0, zieht = false, lx = 0, ly = 0;

  function malen() {{
    bild.style.transform = 'translate(' + x + 'px,' + y + 'px) scale(' + s + ')';
  }}
  function einpassen() {{
    const b = huelle.clientWidth, h = huelle.clientHeight;
    s = Math.min((b - 80) / bild.naturalWidth, (h - 140) / bild.naturalHeight);
    x = (b - bild.naturalWidth * s) / 2;
    y = (h - bild.naturalHeight * s) / 2 - 20;
    malen();
  }}
  function oeffnen(quelle, beschriftung) {{
    bild.onload = einpassen;
    bild.src = quelle;
    titel.textContent = beschriftung;
    huelle.classList.add('offen');
  }}
  function schliessen() {{ huelle.classList.remove('offen'); bild.removeAttribute('src'); }}

  document.querySelectorAll('figure img').forEach(function (i) {{
    i.addEventListener('click', function () {{
      const t = i.closest('figure').querySelector('figcaption');
      oeffnen(i.src, t ? t.textContent : '');
    }});
  }});
  huelle.addEventListener('click', function (e) {{ if (e.target === huelle) schliessen(); }});
  document.addEventListener('keydown', function (e) {{
    if (e.key === 'Escape') schliessen();
    if (!huelle.classList.contains('offen')) return;
    if (e.key === '+' || e.key === '=') {{ s *= 1.2; malen(); }}
    if (e.key === '-') {{ s /= 1.2; malen(); }}
  }});
  huelle.addEventListener('wheel', function (e) {{
    e.preventDefault();
    const faktor = e.deltaY < 0 ? 1.15 : 1 / 1.15;
    x = e.clientX - (e.clientX - x) * faktor;
    y = e.clientY - (e.clientY - y) * faktor;
    s *= faktor;
    malen();
  }}, {{ passive: false }});
  huelle.addEventListener('mousedown', function (e) {{
    zieht = true; lx = e.clientX; ly = e.clientY; huelle.style.cursor = 'grabbing';
  }});
  window.addEventListener('mousemove', function (e) {{
    if (!zieht) return;
    x += e.clientX - lx; y += e.clientY - ly; lx = e.clientX; ly = e.clientY; malen();
  }});
  window.addEventListener('mouseup', function () {{ zieht = false; huelle.style.cursor = 'grab'; }});
  document.getElementById('zp').onclick = function () {{ s *= 1.25; malen(); }};
  document.getElementById('zr').onclick = function () {{ s /= 1.25; malen(); }};
  document.getElementById('z1').onclick = function () {{ s = 1; malen(); }};
  document.getElementById('zen').onclick = einpassen;
  document.getElementById('zx').onclick = schliessen;
}})();
</script>
</body>
</html>
"""

AUSGABE.write_text(html, encoding="utf-8")
groesse = AUSGABE.stat().st_size / 1024 / 1024
print(f"{AUSGABE} geschrieben: {groesse:.2f} MB, {len(html)} Zeichen, "
      f"{anzahl} Module + {len(plan)} Übersichten")
