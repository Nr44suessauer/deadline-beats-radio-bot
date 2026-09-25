#!/usr/bin/env python3
"""Builds APPENDIX/n8n-interface.html: the bot in the n8n interface.

Structure: per workflow an overview (full view) and below **one image per module**,
plus the explanation of the section and the node list. Each image can be
clicked in the document and then zoomed (mouse wheel, buttons, dragging, Esc).

The images are created with `module-images-plan.py` (plan), the capture in the
running interface (tiles) and `images-stitch.py` (assembly).

Usage: python3 tools/n8n-doku-build.py
"""
from __future__ import annotations

import base64
import datetime as dt
import json
import re
from pathlib import Path

HIER = Path(__file__).resolve().parent
ZIEL_ORDNER = HIER.parent / "ANHANG"
BILDER = ZIEL_ORDNER / "images"
MODULE = BILDER / "module"
PLAN = BILDER / "moduleplan.json"
AUSGABE = ZIEL_ORDNER / "n8n-interface.html"

BAUZEIT = dt.datetime.now().strftime("%d.%m.%Y at %H:%M")

# Explanation per module (key = name of the frame in the workflow)
TEXTE = {
    # --- Agent -----------------------------------------------------------
    "Documentation Note": "This note stands in the interface above the area: what the workflow "
                  "is, how it is changed and checked and which files describe it.",
    "Note overview": "The legend: the colours of the frames match the stages — "
                        "yellow = recognize commands, blue = plan, red = execute, "
                        "violet = check and answer, green = services and inbox.",
    "Note input": "Two inputs (Telegram and test input) run into the same "
                     "message preparation. Then <code>Access</code> checks whether the "
                     "sender is the operator; the short paths answer via "
                     "<code>Send (short message)</code> without calling the model.",
    "Note voice message": "Voice messages get their own branch at the top: fetch "
                             "the file, download it, convert it to text on the GPU "
                             "(faster-whisper) and pass the recognized text on. If "
                             "nothing can be understood, there is a short query.",
    "Note analysis": "Stage 0 and 1: first fixed rules recognize simple commands "
                     "(title request, skip, status, roundup, inbox query) — this costs "
                     "no model time. Only when nothing fits does the language model plan and "
                     "<code>Commands read</code> turns it into the command list.",
    "Note execution": "Stage 2 is a loop: every command is processed "
                         "one after another — music via the service path, control commands via fixed "
                         "addresses, everything else via the agent with its tools. "
                         "Special cases hang on their own branches: inbox, topic roundup "
                         "and the fallback path without model.",
    "Note check": "Stage 3: the result is checked (did every command deliver what "
                      "it should?), if necessary reworked (up to two rounds) and finally "
                      "the answer that appears in the chat is built.",
    "Note services": "The service paths in one area: playlists (create, fill, "
                     "start, delete) and messages (announce, discard). Both run "
                     "via the service <code>radio-tts</code>; <code>Service response</code> "
                     "collects the response.",
    "Note inbox": "The inbox: every five minutes the schedule fetches new messages and "
                      "presents them as a card with buttons. <code>Offer item</code> "
                      "notes them as offered — no second offer for the same message.",
    "Note tools": "The eight tool nodes of the agent. Each points to its own "
                       "workflow (radio, AzuraCast, messages) — this keeps the main workflow "
                       "readable and the tools are individually checkable.",
    # --- tool - Radio ------------------------------------------------
    "Note W branches": "The input of the tool: <code>Direction?</code> decides "
                       "between mood request, title search and pure status.",
    "Note W genre": "Genre requests (“something lively”, “90s”) go to the "
                        "catalog service; the suggestions come back as a selection list.",
    "Note W search": "The title search first asks the catalog service (fuzzy, "
                     "typo-tolerant) and then the full-text search of the station; "
                     "<code>Prepare hits</code> merges both lists.",
    "Note W status": "The status: current title, what is next, listener count — prepared as "
                      "a short text.",
    "Note W play": "The play path: empty the queue, then enter immediately or "
                         "enter afterwards. Exactly one path is taken, depending on the request.",
    "Note W output": "The output node: here the tool workflow ends and gives the "
                       "result back to the agent.",
    # --- tool - AzuraCast -------------------------------------------
    "Note AZ branches": "The input: look up an address, call the interface or "
                        "give an overview.",
    "Note AZ addresses": "The addresses come from the description of the station interface "
                         "(263 endpoints) — the model does not have to guess any address.",
    "Note AZ call": "The call: <code>Guard</code> protects against dangerous calls, "
                       "<code>Read only?</code> separates reading and writing, and a "
                       "dry run shows what would happen.",
    "Note AZ overview": "The overview collects attachments, status and playlists with "
                           "title count in one text.",
    # --- Tool - Messages -------------------------------------------
    "Note M branches": "The input: fetch research, speak or serve the inbox.",
    "Note M research": "The research asks the service (weather, news, feeds, "
                         "topic roundup) and stores the result as a message.",
    "Note M announcement": "Speaking: free text or a stored message — both go "
                      "via the DJ harbor into the running broadcast.",
    "Note M inbox": "The inbox: discard a message, view the spoken text or list "
                        "open messages.",
    "Note M output": "The output node of the tool.",
    # --- Archiv ----------------------------------------------------------
    "Note Inputs": "Three start paths (manually, form, webhook) run into the same "
                       "Kette.",
    "Note Context": "What is playing right now, and what happened last? That is the basis "
                     "for the moderation text.",
    "Note Text and Voice": "From the context a spoken text (model) is built, which is cleaned "
                             "and then spoken by Piper.",
    "Note Output": "Either speak live (interrupts briefly) or upload as a track.",
    "Note Tracking": "After uploading: wait, find the track in the archive, "
                            "wish and hand it over.",
    "Note Old Tools": "leftovers of the first version — not connected, only for "
                              "Erinnerung.",
}

ABLAEUFE = [
    ("RadioAgentBot", "Radio - Telegram-Agent", "in Betrieb · 81 nodes in 10 Modulen"),
    ("RadioWerkzeug", "tool - Radio", "in Betrieb · 16 nodes in 7 Modulen"),
    ("AzuraWerkzeug", "tool - AzuraCast", "in Betrieb · 16 nodes in 5 Modulen"),
    ("MeldungenWerkzeug", "Tool - Messages", "in Betrieb · 13 nodes in 6 Modulen"),
    ("bjFSfXGqpLg7AAXw", "Radio - AI-Moderator", "Archive · 19 nodes in 7 modules"),
]


def einbetten(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


def bild_html(file: str, beschriftung: str, klasse: str = "modul") -> str:
    path = MODULE / file
    if not path.exists():
        return f'<p class="missing">Image missing: {file}</p>'
    return (f'<figure class="{klasse}"><img alt="{beschriftung}" loading="lazy" '
            f'src="data:image/png;base64,{einbetten(path)}">'
            f'<figcaption>{beschriftung}</figcaption></figure>')


def tabelle(lines: list[tuple[str, str]], koepfe=("Vorgang", "Command")) -> str:
    kopf = "".join(f"<th>{k}</th>" for k in koepfe)
    inhalt = "".join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in lines)
    return f'<table><thead><tr>{kopf}</tr></thead><tbody>{inhalt}</tbody></table>'


plan = json.loads(PLAN.read_text(encoding="utf-8"))
teile: list[str] = []

teile.append(f"""
<p class="vorspann">The bot <strong>in the n8n interface</strong>: for every workflow an
overview and below <strong>one image per module</strong> with the explanation of the
section. <span class="zoomhinweis">Each image can be clicked and then zoomed
(mouse wheel, buttons, dragging) — with <kbd>Esc</kbd> it closes again.</span>
As of: {BAUZEIT}.</p>

<div class="kasten">
<h3>Where the interface lives</h3>
<ul>
  <li><strong>Adresse:</strong> <code>https://YOUR-N8N-HOST</code>
      (im Hausnetz <code>http://192.168.178.53:5678</code>)</li>
  <li><strong>Five radio workflows:</strong> agent, three tools, archive (chapter below)</li>
  <li><strong>Rule:</strong> in the interface only <em>view</em> — the plan is changed
      in <code>REBUILD/bau/agent-wf-build.py</code></li>
</ul>
</div>""")

for identifier, title, extra in ABLAEUFE:
    data = plan.get(identifier)
    if not data:
        continue
    kapitel = [f'<p class="identifier">{extra}</p>']
    kapitel.append(bild_html(data["total"]["file"],
                             "Full view: the whole workflow at a glance (click to zoom)",
                             klasse="total"))
    kapitel.append('<table class="module"><thead><tr><th>Module</th><th>Nodes</th>'
                   "</tr></thead><tbody>")
    for m in data["module"]:
        anker = re.sub(r"[^a-z0-9]+", "-", m["frames"].lower()).strip("-")
        kapitel.append(f'<tr><td><a href="#{identifier}-{anker}">{m["title"]}</a></td>'
                       f'<td>{len(m["nodes"])}</td></tr>')
    kapitel.append("</tbody></table>")
    for m in data["module"]:
        anker = re.sub(r"[^a-z0-9]+", "-", m["frames"].lower()).strip("-")
        text = TEXTE.get(m["frames"], "")
        kapitel.append(f'<h3 id="{identifier}-{anker}">{m["title"]}</h3>')
        if text:
            kapitel.append(f"<p>{text}</p>")
        kapitel.append(bild_html(m["file"], f'Module "{m["title"]}" (click to zoom)'))
        if m["nodes"]:
            kapitel.append('<p class="nodes">Contains: '
                           + ", ".join(f"<code>{k}</code>" for k in m["nodes"]) + "</p>")
    teile.append(f'<h2>{title}</h2>\n' + "\n".join(kapitel))

teile.append(f"""<h2>Notes and documentation in the interface</h2>
<p>Every workflow explains itself: <strong>frames</strong> with heading and
explanatory sentence, a <strong>note at every node</strong>, a
<strong>documentation note</strong> at the top (what the workflow is, how to change and
check it, which files describe it) and for old workflows an
<strong>old version note</strong>.</p>
{bild_html("modul-radio-telegram-agent-01.png", "The agent's documentation note")}
{bild_html("modul-radio-telegram-agent-10.png", "The legend (overview note) explains the colors of the areas")}

<h2>And what if you want to change something?</h2>
<p><strong>Do not</strong> click in the interface: layout, frames and notes
come from the build tool; a click in n8n would be gone at the next import.</p>
{tabelle([
    ("Change the workflow", "<code>agent-patch.sh --cleanup</code> → <code>agent-deploy-only.sh /tmp/radio-agent-new.json</code> → <code>docker restart n8n</code>"),
    ("Check the layout", "<code>python3 tools/anordnung-check.py REBUILD/workflows-running/*.json</code> (goal: 0 findings)"),
    ("Capture images again", "<code>module-images-plan.py</code> → capture tiles → <code>images-stitch.py</code> → <code>n8n-doku-build.py</code>"),
    ("Back up a version", "<code>bash tools/version-sichern.sh &lt;name&gt; [description.md]</code>"),
])}""")

seiten = "\n".join(teile)
count = sum(len(v["module"]) for v in plan.values())

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>The bot in the n8n interface</title>
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
  figure.total img {{ border-color: #3d4657; }}
  figcaption {{ margin-top: .45rem; font-size: .9rem; color: #9aa4b2; }}
  .zoomhinweis {{ color: #ffb08a; }}
  .identifier {{ color: #9aa4b2; font-size: .92rem; margin: .2rem 0 .6rem; }}
  .nodes {{ color: #9aa4b2; font-size: .9rem; }}
  table {{ width: 100%; border-collapse: collapse; margin: 1rem 0; font-size: .92rem; }}
  table.module {{ margin: 1rem 0 2rem; }}
  th, td {{ text-align: left; padding: .45rem .6rem; border-bottom: 1px solid #262b34;
            vertical-align: top; }}
  th {{ background: #1d2027; color: #cfd6e0; font-weight: 600; }}
  a {{ color: #7fb2ff; }}
  .kasten {{ background: #1b1f26; border: 1px solid #2c313b; border-left: 4px solid #ff7a45;
             border-radius: 8px; padding: .8rem 1.1rem; margin: 1.2rem 0; }}
  .vorspann {{ font-size: 1.05rem; }}
  .missing {{ color: #ff6b6b; }}
  footer {{ max-width: 1120px; margin: 3rem auto 0; padding: 1rem 1.5rem;
            color: #7c8798; font-size: .88rem; border-top: 1px solid #2c313b; }}
  #zoom {{ position: fixed; inset: 0; background: #0b0d11ee; display: none;
           z-index: 50; overflow: hidden; cursor: grab; }}
  #zoom.open {{ display: block; }}
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
  <h1>The bot in the n8n interface</h1>
  <p>{count} modules in 5 workflows · one image per module, clickable to zoom · {BAUZEIT}</p>
</header>
<main>
{seiten}
</main>
<footer>
  <p>Generated by <code>tools/n8n-doku-build.py</code> from the module images in
  <code>APPENDIX/images/module/</code> (plan: <code>module-images-plan.py</code>, capture in
  the running interface, assembly: <code>images-stitch.py</code>).</p>
  <p>Nothing was changed on the bot; node lists: <code>APPENDIX/LAYOUT.md</code>.</p>
</footer>

<div id="zoom"><img id="zoombild" alt=""><div id="zoomleiste">
  <span id="zoomtitel"></span>
  <button id="zr">−</button><button id="zp">+</button>
  <button id="z1">1:1</button><button id="zen">fit</button><button id="zx">close</button>
</div></div>
<script>
(function () {{
  const huelle = document.getElementById('zoom');
  const bild = document.getElementById('zoombild');
  const title = document.getElementById('zoomtitel');
  let s = 1, x = 0, y = 0, zieht = false, lx = 0, ly = 0;

  function malen() {{
    bild.style.transform = 'translate(' + x + 'px,' + y + 'px) scale(' + s + ')';
  }}
  function fit() {{
    const b = huelle.clientWidth, h = huelle.clientHeight;
    s = Math.min((b - 80) / bild.naturalWidth, (h - 140) / bild.naturalHeight);
    x = (b - bild.naturalWidth * s) / 2;
    y = (h - bild.naturalHeight * s) / 2 - 20;
    malen();
  }}
  function oeffnen(source, beschriftung) {{
    bild.onload = fit;
    bild.src = source;
    title.textContent = beschriftung;
    huelle.classList.add('open');
  }}
  function schliessen() {{ huelle.classList.remove('open'); bild.removeAttribute('src'); }}

  document.querySelectorAll('figure img').forEach(function (i) {{
    i.addEventListener('click', function () {{
      const t = i.closest('figure').querySelector('figcaption');
      oeffnen(i.src, t ? t.textContent : '');
    }});
  }});
  huelle.addEventListener('click', function (e) {{ if (e.target === huelle) schliessen(); }});
  document.addEventListener('keydown', function (e) {{
    if (e.key === 'Escape') schliessen();
    if (!huelle.classList.contains('open')) return;
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
  document.getElementById('zen').onclick = fit;
  document.getElementById('zx').onclick = schliessen;
}})();
</script>
</body>
</html>
"""

AUSGABE.write_text(html, encoding="utf-8")
groesse = AUSGABE.stat().st_size / 1024 / 1024
print(f"{AUSGABE} written: {groesse:.2f} MB, {len(html)} characters, "
      f"{count} modules + 5 overviews")
