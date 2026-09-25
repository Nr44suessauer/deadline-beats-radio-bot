#!/usr/bin/env python3
"""Draw an n8n workflow as an image - for checking the arrangement.

Call: preview.py <workflow.json> <image.png> [scale] [x0 y0 x1 y1]

Intentionally simple: Boxes for the nodes (100x100 raster points, as in n8n),
thin lines for the connections, sticky notes as frames. With the four
numbers a group can be drawn large - then the name remains readable.

Environment variable VORSCHAU_OHNE_NAMEN=1 hides the node names; this gives
an overview image (like n8n at small zoom) for documentation.
"""
import json
import os
import sys
from PIL import Image, ImageDraw, ImageFont

QUELLE = sys.argv[1]
ZIEL = sys.argv[2]
MASZ = float(sys.argv[3]) if len(sys.argv) > 3 else 0.35
AUSSCHNITT = [float(x) for x in sys.argv[4:8]] if len(sys.argv) >= 8 else None
OHNE_NAMEN = bool(os.environ.get("VORSCHAU_OHNE_NAMEN"))

KNOTEN_B = 100          # Width of a node in the n8n grid
KNOTEN_H = 100          # height
MARGIN = 60

mit_daten = json.load(open(QUELLE, encoding="utf-8"))
wf = mit_daten[0] if isinstance(mit_daten, list) else mit_daten
nodes = wf["nodes"]

try:
    schrift_klein = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 10)
    schrift_titel = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16)
except OSError:
    schrift_klein = schrift_titel = ImageFont.load_default()

notizen = [k for k in nodes if "stickyNote" in k["type"]]
rest = [k for k in nodes if "stickyNote" not in k["type"]]

if AUSSCHNITT:
    x0, y0, x1, y1 = AUSSCHNITT
else:
    kanten = [(k["position"][0], k["position"][1],
               k["position"][0] + KNOTEN_B, k["position"][1] + KNOTEN_H) for k in rest]
    for k in notizen:
        kanten.append((k["position"][0], k["position"][1],
                       k["position"][0] + k["parameters"].get("width", 240),
                       k["position"][1] + k["parameters"].get("height", 240)))
    x0 = min(k[0] for k in kanten) - MARGIN
    y0 = min(k[1] for k in kanten) - MARGIN
    x1 = max(k[2] for k in kanten) + MARGIN
    y1 = max(k[3] for k in kanten) + MARGIN

bild = Image.new("RGB", (max(1, int((x1 - x0) * MASZ)), max(1, int((y1 - y0) * MASZ))),
                 (247, 247, 248))
stift = ImageDraw.Draw(bild, "RGBA")


def p(x, y):
    return ((x - x0) * MASZ, (y - y0) * MASZ)


def sichtbar(px, py, w, h):
    bx, by = p(px, py)
    return not (bx > bild.width or by > bild.height or bx + w < 0 or by + h < 0)


# Sticky notes first - they lie behind the nodes.
for k in notizen:
    px, py = k["position"]
    w = k["parameters"].get("width", 240) * MASZ
    h = k["parameters"].get("height", 240) * MASZ
    if not sichtbar(px, py, w, h):
        continue
    bx, by = p(px, py)
    stift.rectangle([bx, by, bx + w, by + h], fill=(255, 246, 204, 255),
                    outline=(205, 165, 45, 255))
    lines = k["parameters"].get("content", "").splitlines()
    title = lines[0].lstrip("# ").strip() if lines else k["name"]
    stift.text((bx + 10, by + 8), title, font=schrift_titel, fill=(125, 90, 10))
    # Text as in n8n wrap (the note width determines line width), otherwise
    # the image shows text that is already wrapped in n8n.
    # Space in the header area: the first node in the frame determines the boundary. Only
    # as many text lines are drawn as actually fit - otherwise
    # the image looks like text is lying on the nodes.
    inside = []
    if MASZ:
        for k2 in rest:
            mx, my = k2["position"][0] + 50, k2["position"][1] + 50
            if (px - 60 <= mx <= px + k["parameters"].get("width", 240)
                    and py - 20 <= my <= py + h / MASZ):
                inside.append(k2["position"][1])
    kopf_band = (min(inside) - py) * MASZ if inside else h / 3
    platz = max(int(kopf_band - 26), 0)
    je_zeile = max(int(w / (5.4 * MASZ)) if MASZ else 1, 20)
    umbrochen = []
    for z in lines[1:]:
        z = z.replace("* ", "- ").replace("**", "").replace("`", "")
        rest_text = z
        while len(rest_text) > je_zeile:
            schnitt = rest_text.rfind(" ", 0, je_zeile + 1)
            if schnitt <= 0:
                schnitt = je_zeile
            umbrochen.append(rest_text[:schnitt])
            rest_text = rest_text[schnitt:].lstrip()
        umbrochen.append(rest_text)
    for i, z in enumerate(umbrochen[:max(platz // 12, 0)]):
        stift.text((bx + 12, by + 30 + i * 12), z, font=schrift_klein,
                   fill=(120, 100, 40))

# Connections as thin lines from node center to node center.
stelle = {k["name"]: k["position"] for k in rest}
for source, ausgaenge in (wf.get("connections") or {}).items():
    if source not in stelle:
        continue
    for type, zweige in ausgaenge.items():
        for zweig in zweige or []:
            for target in zweig or []:
                if target.get("node") not in stelle:
                    continue
                ax, ay = p(stelle[source][0] + KNOTEN_B / 2, stelle[source][1] + KNOTEN_H / 2)
                bx, by = p(stelle[target["node"]][0] + KNOTEN_B / 2, stelle[target["node"]][1] + KNOTEN_H / 2)
                farbe = (150, 150, 160, 200) if type == "main" else (120, 150, 220, 200)
                stift.line([ax, ay, bx, by], fill=farbe, width=1)

# Nodes as boxes with label underneath.
for k in rest:
    px, py = k["position"]
    w, h = KNOTEN_B * MASZ, KNOTEN_H * MASZ
    if not sichtbar(px, py, w, h + 30):
        continue
    bx, by = p(px, py)
    margin = (140, 140, 150)
    if "toolWorkflow" in k["type"] or "agent" in k["type"]:
        margin = (120, 90, 200)
    elif k["type"].endswith("httpRequest"):
        margin = (60, 120, 200)
    elif k["type"].endswith(".code"):
        margin = (150, 120, 60)
    elif k["type"].endswith(".if"):
        margin = (200, 120, 60)
    stift.rectangle([bx, by, bx + w, by + h], fill=(255, 255, 255), outline=margin, width=2)
    if not OHNE_NAMEN:
        stift.text((bx + 3, by + 6), k["name"][:18], font=schrift_klein, fill=(40, 40, 50))
    if k.get("notesInFlow") and not OHNE_NAMEN:
        # The note is under the node in n8n, wrapped to the node width.
        notiz = (k.get("notes") or "").strip()
        zeile_max = max(int(KNOTEN_B / 7.0), 8)
        text_zeilen = []
        rest_text = notiz
        while len(rest_text) > zeile_max:
            schnitt = rest_text.rfind(" ", 0, zeile_max + 1)
            if schnitt <= 0:
                schnitt = zeile_max
            text_zeilen.append(rest_text[:schnitt])
            rest_text = rest_text[schnitt:].lstrip()
        text_zeilen.append(rest_text)
        for i, z in enumerate(text_zeilen[:6]):
            stift.text((bx, by + h + 2 + i * 10), z, font=schrift_klein,
                       fill=(125, 125, 135))

print("Nodes: %d, sticky notes: %d | Image %dx%d, crop %s"
      % (len(rest), len(notizen), bild.width, bild.height, AUSSCHNITT or "full plan"))
bild.save(ZIEL)
