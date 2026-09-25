#!/usr/bin/env python3
"""gif-bauen.py - baut aus einer Bildfolge ein GIF.

Aufruf:
  python3 gif-bauen.py <bildordner> <ziel.gif> [--breite 1200] [--takt 8]
                       [--von 5] [--bis 30] [--beschleunigung 1.0] [--farben 128]
                       [--schleife 0] [--probe]

Die Bildfolge kommt aus gif-aufnahme.js (dort steht in aufnahme.json auch der
tatsächliche Zeitabstand der Bilder). Ohne --takt wird er von dort gelesen.
"""
import argparse
import json
import os
import re
import sys
from PIL import Image, ImageChops


def bilder_lesen(ordner):
    dateien = [d for d in os.listdir(ordner) if re.fullmatch(r"bild-\d+\.(png|jpg)", d)]
    dateien.sort()
    return dateien


def beschnitt(bilder, bericht, args):
    """Auf die Zeichenfläche schneiden. Der Bildschirmstrom liefert die ganze Seite;
    die Fläche steht im Aufnahmebericht (masse) - bei verkleinertem Strom umgerechnet."""
    m = (bericht or {}).get('masse')
    if not m or not m.get('b'):
        return [im.crop((args.links, args.oben, im.width - args.rechts, im.height - args.unten)) for im in bilder]
    f = str((bericht or {}).get('fenster') or '').lower().split('x')
    fb, fh = (int(f[0]), int(f[1])) if len(f) == 2 else (bilder[0].width, bilder[0].height)
    # Der Bildschirmstrom kann die Seite verkleinern; der Faktor ist in beiden Achsen gleich.
    kb = kh = min(bilder[0].width / fb, bilder[0].height / fh)
    if args.inhalt and (bericht or {}).get('inhalt') and (bericht or {}).get('inhalt', {}).get('x1', 0) > 0:
        # Enger Beschnitt an den echten Knotenrechtecken (im Browser gemessen)
        i = bericht['inhalt']
        x0, y0, x1, y1 = i['x0'] * kb, i['y0'] * kh, i['x1'] * kb, i['y1'] * kh
        rand = (x1 - x0) * args.inhalt_rand / 100.0
        rand_y = (y1 - y0) * args.inhalt_rand / 100.0
        links = int(max(0, x0 - rand)) + args.links
        oben = int(max(0, y0 - rand_y)) + args.oben
        rechts = int(max(0, bilder[0].width - x1 - rand)) - args.rechts
        unten = int(max(0, bilder[0].height - y1 - rand_y)) - args.unten
        print(f"Inhaltsbeschnitt (Knotenrechtecke): links {links}, oben {oben}, rechts {rechts}, unten {unten} "
              f"(Inhalt {int(x1 - x0)}x{int(y1 - y0)} Punkte, Rand {args.inhalt_rand}%)")
    elif args.inhalt and (bericht or {}).get('flaeche') and (bericht or {}).get('massstab'):
        # Enger Beschnitt: nur der Ablauf selbst (n8n lässt sonst viel leere Fläche stehen).
        fl, s = bericht['flaeche'], bericht['massstab']
        x0 = (m['x'] + fl['x0'] * s + m['tx']) * kb
        y0 = (m['y'] + fl['y0'] * s + m['ty']) * kh
        x1 = (m['x'] + fl['x1'] * s + m['tx']) * kb
        y1 = (m['y'] + fl['y1'] * s + m['ty']) * kh
        rand = (x1 - x0) * args.inhalt_rand / 100.0
        rand_y = (y1 - y0) * args.inhalt_rand / 100.0
        links = int(max(0, x0 - rand)) + args.links
        oben = int(max(0, y0 - rand_y)) + args.oben
        rechts = int(max(0, bilder[0].width - x1 - rand)) - args.rechts
        unten = int(max(0, bilder[0].height - y1 - rand_y)) - args.unten
        print(f"Inhaltsbeschnitt: links {links}, oben {oben}, rechts {rechts}, unten {unten} "
              f"(Ablauf {int(x1 - x0)}x{int(y1 - y0)} Punkte, Rand {args.inhalt_rand}%)")
    else:
        links = round(m['x'] * kb) + args.links
        oben = round(m['y'] * kh) + args.oben
        rechts = bilder[0].width - round((m['x'] + m['b']) * kb) - args.rechts
        unten = bilder[0].height - round((m['y'] + m['h']) * kh) - args.unten
        print(f"Beschnitt: links {links}, oben {oben}, rechts {rechts}, unten {unten} (Umrechnung {kb:.3f}/{kh:.3f})")
    return [im.crop((links, oben, im.width - rechts, im.height - unten)) for im in bilder]


def palette_bauen(bilder, farben):
    """Eine gemeinsame Farbtabelle aus mehreren Bildern - verhindert Flackern."""
    proben = bilder[:: max(1, len(bilder) // 12)][:12]
    hoehe = max(1, proben[0].height // 4)
    blatt = Image.new("RGB", (max(1, proben[0].width // 4) * len(proben), hoehe))
    for i, b in enumerate(proben):
        blatt.paste(b.resize((max(1, b.width // 4), hoehe), Image.LANCZOS), (i * max(1, b.width // 4), 0))
    return blatt.quantize(colors=farben, method=Image.MEDIANCUT)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ordner")
    ap.add_argument("ziel")
    ap.add_argument("--breite", type=int, default=1200, help="Zielbreite in Punkten (0 = Original)")
    ap.add_argument("--takt", type=float, default=0, help="Bilder je Sekunde (0 = aus aufnahme.json)")
    ap.add_argument("--zeit", type=float, default=0, help="Bildzeit in Sekunden (0 = aus aufnahme.json)")
    ap.add_argument("--von", type=float, default=0, help="Anfang in Sekunden (Aufnahmezeit)")
    ap.add_argument("--bis", type=float, default=0, help="Ende in Sekunden (Aufnahmezeit)")
    ap.add_argument("--beschleunigung", type=float, default=1.0, help=">1 = kürzer/schneller")
    ap.add_argument("--farben", type=int, default=128)
    ap.add_argument("--schleife", type=int, default=0, help="0 = endlos")
    ap.add_argument("--probe", action="store_true", help="nur rechnen, nicht schreiben")
    ap.add_argument("--oben", type=int, default=0, help="so viele Punkte oben abschneiden")
    ap.add_argument("--rechts", type=int, default=0, help="so viele Punkte rechts abschneiden")
    ap.add_argument("--unten", type=int, default=0, help="so viele Punkte unten abschneiden")
    ap.add_argument("--links", type=int, default=0, help="so viele Punkte links abschneiden")
    ap.add_argument("--jedes", type=int, default=1, help="nur jedes n-te Bild verwenden")
    ap.add_argument("--zeitgleich", action="store_true", help="Originalzeit der Bilder statt fester Bilddauer")
    ap.add_argument("--luecke-max", type=int, default=0, help="lange Pausen (ms) auf diesen Wert kürzen")
    ap.add_argument("--mitlaufen", type=int, default=0, help="Kamera folgt der Bewegung; Wert = Empfindlichkeit (z. B. 12)")
    ap.add_argument("--fenster", default="1400x800", help="Ausschnittgröße für den Mitlauf (b x h)")
    ap.add_argument("--glaetten", type=float, default=0.6, help="Sekunden für die Glättung der Kamerafahrt")
    ap.add_argument("--abschnitte", default="", help="Zeitfenster wie 6,3:11,6;15,28:15,65 (Sekunden)")
    ap.add_argument("--inhalt", action="store_true", help="eng auf den Ablauf schneiden (ohne leere Ränder)")
    ap.add_argument("--inhalt-rand", type=float, default=2.0, help="Rand beim Inhaltsbeschnitt in Prozent")
    ap.add_argument("--rahmen", type=int, default=0, help="Rahmenstärke in Punkten (0 = ohne)")
    ap.add_argument("--rahmen-farbe", default="c9ced6", help="Farbe des Rahmens als Hexwert")
    ap.add_argument("--titel", default="", help="Beschriftung als Leiste über dem Bild (z. B. „Radio-Agent · Testlauf“)")
    ap.add_argument("--titel-hoehe", type=int, default=30, help="Höhe der Beschriftungsleiste in Punkten")
    ap.add_argument("--titel-hintergrund", default="f2f4f7", help="Hintergrundfarbe der Leiste")
    ap.add_argument("--titel-schrift", default="333b47", help="Schriftfarbe der Beschriftung")
    args = ap.parse_args()

    bericht_pfad = os.path.join(args.ordner, "aufnahme.json")
    zeiten, takt, bericht = [], args.takt, {}
    if os.path.exists(bericht_pfad):
        with open(bericht_pfad, encoding="utf-8") as f:
            bericht = json.load(f)
        zeiten = [b["t"] / 1000.0 for b in bericht.get("bilder", [])]
        if not takt and len(zeiten) > 2:
            abst = [zeiten[i + 1] - zeiten[i] for i in range(len(zeiten) - 1)]
            abst.sort()
            takt = 1.0 / abst[len(abst) // 2]
    if not takt:
        takt = args.zeit or 8.0
    takt = takt * args.beschleunigung

    namen = bilder_lesen(args.ordner)
    if not namen:
        sys.exit("Keine Bilder gefunden in " + args.ordner)
    if len(zeiten) != len(namen):
        zeiten = [i / takt for i in range(len(namen))]

    paare = []
    for i, name in enumerate(namen):
        t = zeiten[i]
        if t < args.von:
            continue
        if args.bis and t > args.bis:
            break
        paare.append((name, t))
    if args.abschnitte:
        fenster = []
        for stelle in args.abschnitte.replace(',', '.').split(';'):
            if ':' not in stelle:
                continue
            a, b = stelle.split(':')
            fenster.append((float(a.replace(',', '.')), float(b.replace(',', '.'))))
        paare = [(n, t) for (n, t) in paare if any(a <= t <= b for a, b in fenster)]
        print('Zeitfenster:', ', '.join(f'{a:.1f}-{b:.1f}s' for a, b in fenster))
    if not paare:
        sys.exit("Kein Bild im gewählten Zeitfenster")
    paare = paare[:: max(1, args.jedes)]
    print(f"{len(paare)} von {len(namen)} Bildern, Takt {takt:.2f} Bilder/s")

    bilder, dauern = [], []
    roh = []
    for i, (name, t) in enumerate(paare):
        im = Image.open(os.path.join(args.ordner, name)).convert("RGB")
        roh.append(im)
        if args.zeitgleich and i + 1 < len(paare):
            d = (paare[i + 1][1] - t) / args.beschleunigung
            dauer_i = int(max(30, min(1000, d * 1000)))
            if args.luecke_max:
                dauer_i = min(dauer_i, args.luecke_max)
            dauern.append(dauer_i)
        else:
            dauern.append(max(20, round(1000.0 / takt)))

    if args.mitlaufen:
        fb, fh = [int(x) for x in args.fenster.lower().split("x")]
        roh = beschnitt(roh, bericht, args)
        focus = []
        vor = None
        for im in roh:
            grau = im.convert("L")
            kasten = None
            if vor is not None:
                d = ImageChops.difference(grau, vor)
                kasten = d.point(lambda v: 255 if v > args.mitlaufen else 0).getbbox()
            focus.append(kasten)
            vor = grau
        # Lücken füllen (letzter bekannter Ort), Mittelpunkte glätten
        letzter = (roh[0].width / 2, roh[0].height / 2)
        mittel = []
        for k in focus:
            if k:
                letzter = ((k[0] + k[2]) / 2, (k[1] + k[3]) / 2)
            mittel.append(letzter)
        fenster_bilder = max(1, int(args.glaetten * takt))
        geglaettet = []
        for i in range(len(mittel)):
            a = max(0, i - fenster_bilder)
            b = min(len(mittel), i + fenster_bilder + 1)
            xs = [mittel[j][0] for j in range(a, b)]
            ys = [mittel[j][1] for j in range(a, b)]
            geglaettet.append((sum(xs) / len(xs), sum(ys) / len(ys)))
        for im, (mx, my) in zip(roh, geglaettet):
            links = int(max(0, min(im.width - fb, mx - fb / 2)))
            oben = int(max(0, min(im.height - fh, my - fh / 2)))
            im2 = im.crop((links, oben, links + fb, oben + fh))
            if args.breite and im2.width != args.breite:
                im2 = im2.resize((args.breite, round(im2.height * args.breite / im2.width)), Image.LANCZOS)
            bilder.append(im2)
    else:
        roh = beschnitt(roh, bericht, args)
        for im in roh:
            if args.breite and im.width != args.breite:
                im = im.resize((args.breite, round(im.height * args.breite / im.width)), Image.LANCZOS)
            bilder.append(im)

    pal = palette_bauen(bilder, args.farben)
    bilder = [b.quantize(palette=pal, dither=Image.FLOYDSTEINBERG) for b in bilder]

    if args.rahmen:
        from PIL import ImageDraw
        farbe = tuple(int(args.rahmen_farbe[i:i + 2], 16) for i in (0, 2, 4))
        for b in bilder:
            d = ImageDraw.Draw(b)
            for k in range(args.rahmen):
                d.rectangle([k, k, b.width - 1 - k, b.height - 1 - k], outline=farbe)

    if args.titel:
        from PIL import ImageDraw, ImageFont
        schrift = None
        for weg in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"):
            try:
                schrift = ImageFont.truetype(weg, max(11, round(args.titel_hoehe * 0.55)))
                break
            except Exception:
                continue
        if schrift is None:
            schrift = ImageFont.load_default()
        hg = tuple(int(args.titel_hintergrund[i:i + 2], 16) for i in (0, 2, 4))
        fs = tuple(int(args.titel_schrift[i:i + 2], 16) for i in (0, 2, 4))
        trenn = tuple(int(args.rahmen_farbe[i:i + 2], 16) for i in (0, 2, 4))
        mit_leiste = []
        for b in bilder:
            blatt = Image.new("RGB", (b.width, b.height + args.titel_hoehe), hg)
            blatt.paste(b, (0, args.titel_hoehe))
            d = ImageDraw.Draw(blatt)
            d.line([(0, args.titel_hoehe - 1), (b.width, args.titel_hoehe - 1)], fill=trenn, width=1)
            d.text((12, args.titel_hoehe / 2), args.titel, font=schrift, fill=fs, anchor="lm")
            mit_leiste.append(blatt)
        bilder = mit_leiste

    dauer = max(20, round(1000.0 / takt))
    if args.probe:
        print("Probe: " + str(len(bilder)) + " Bilder, Gesamtzeit " + str(sum(dauern) / 1000) + " s, " + str(bilder[0].size))
        return
    bilder[0].save(args.ziel, save_all=True, append_images=bilder[1:], duration=dauern,
                   loop=args.schleife, optimize=True, disposal=2)
    groesse = os.path.getsize(args.ziel) / 1e6
    print(f"Geschrieben: {args.ziel}  {groesse:.2f} MB  {bilder[0].size[0]}x{bilder[0].size[1]}  "
          f"{len(bilder)} Bilder  Laufzeit {sum(dauern) / 1000:.1f} s")


if __name__ == "__main__":
    main()
