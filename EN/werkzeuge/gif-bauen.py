#!/usr/bin/env python3
"""gif-build.py - builds a GIF from an image sequence.

Call:
  python3 gif-build.py <bildordner> <target.gif> [--breite 1200] [--rate 8]
 [--start 5] [--end 30] [--speed 1.0] [--colors 128]
 [--schleife 0] [--probe]

The image sequence comes from gif-recording.js (the actual time interval between images is also in recording.json).
actual time spacing of the frames). Without --rate it is read from there.
"""
import argparse
import json
import os
import re
import sys
from PIL import Image, ImageChops


def bilder_lesen(folder):
    dateien = [d for d in os.listdir(folder) if re.fullmatch(r"bild-\d+\.(png|jpg)", d)]
    dateien.sort()
    return dateien


def beschnitt(images, report, args):
    """Crop to the canvas. The screen stream provides the entire page;
 the area is stated in the capture report (size) - converted for reduced stream."""
    m = (report or {}).get('masse')
    if not m or not m.get('b'):
        return [im.crop((args.left, args.above, im.width - args.right, im.height - args.below)) for im in images]
    f = str((report or {}).get('fenster') or '').lower().split('x')
    fb, fh = (int(f[0]), int(f[1])) if len(f) == 2 else (images[0].width, images[0].height)
    # The screen stream can reduce the page; the factor is the same in both axes.
    kb = kh = min(images[0].width / fb, images[0].height / fh)
    if args.inhalt and (report or {}).get('inhalt') and (report or {}).get('inhalt', {}).get('x1', 0) > 0:
        # Tight crop around the actual node rectangles (measured in the browser)
        i = report['inhalt']
        x0, y0, x1, y1 = i['x0'] * kb, i['y0'] * kh, i['x1'] * kb, i['y1'] * kh
        margin = (x1 - x0) * args.inhalt_rand / 100.0
        rand_y = (y1 - y0) * args.inhalt_rand / 100.0
        left = int(max(0, x0 - margin)) + args.left
        above = int(max(0, y0 - rand_y)) + args.above
        right = int(max(0, images[0].width - x1 - margin)) - args.right
        below = int(max(0, images[0].height - y1 - rand_y)) - args.below
        print(f"Content crop (node rectangles): left {left}, top {above}, right {right}, bottom {below}"
              f"(Content {int(x1 - x0)}x{int(y1 - y0)} pixels, border {args.inhalt_rand}%)")
    elif args.inhalt and (report or {}).get('area') and (report or {}).get('scale'):
        # Tight crop: only the flow itself (otherwise n8n leaves a lot of empty space).
        fl, s = report['area'], report['scale']
        x0 = (m['x'] + fl['x0'] * s + m['tx']) * kb
        y0 = (m['y'] + fl['y0'] * s + m['ty']) * kh
        x1 = (m['x'] + fl['x1'] * s + m['tx']) * kb
        y1 = (m['y'] + fl['y1'] * s + m['ty']) * kh
        margin = (x1 - x0) * args.inhalt_rand / 100.0
        rand_y = (y1 - y0) * args.inhalt_rand / 100.0
        left = int(max(0, x0 - margin)) + args.left
        above = int(max(0, y0 - rand_y)) + args.above
        right = int(max(0, images[0].width - x1 - margin)) - args.right
        below = int(max(0, images[0].height - y1 - rand_y)) - args.below
        print(f"Content crop: left {left}, top {above}, right {right}, bottom {below}"
              f"(Processing {int(x1 - x0)}x{int(y1 - y0)} points, border {args.inhalt_rand}%)")
    else:
        left = round(m['x'] * kb) + args.left
        above = round(m['y'] * kh) + args.above
        right = images[0].width - round((m['x'] + m['b']) * kb) - args.right
        below = images[0].height - round((m['y'] + m['h']) * kh) - args.below
        print(f"Crop: left {left}, top {above}, right {right}, bottom {below} (Conversion {kb:.3f}/{kh:.3f})")
    return [im.crop((left, above, im.width - right, im.height - below)) for im in images]


def palette_bauen(images, farben):
    """A common color table from multiple images - prevents flickering."""
    proben = images[:: max(1, len(images) // 12)][:12]
    height = max(1, proben[0].height // 4)
    blatt = Image.new("RGB", (max(1, proben[0].width // 4) * len(proben), height))
    for i, b in enumerate(proben):
        blatt.paste(b.resize((max(1, b.width // 4), height), Image.LANCZOS), (i * max(1, b.width // 4), 0))
    return blatt.quantize(colors=farben, method=Image.MEDIANCUT)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("target")
    ap.add_argument("--breite", type=int, default=1200, help="Target width in points (0 = original)")
    ap.add_argument("--rate", type=float, default=0, help="Images per second (0 = from recording.json)")
    ap.add_argument("--time", type=float, default=0, help="Image time in seconds (0 = from recording.json)")
    ap.add_argument("--start", type=float, default=0, help="start in seconds (recording time)")
    ap.add_argument("--end", type=float, default=0, help="End in seconds (recording time)")
    ap.add_argument("--speed", type=float, default=1.0, help=">1 = shorter/faster")
    ap.add_argument("--colors", type=int, default=128)
    ap.add_argument("--schleife", type=int, default=0, help="0 = endless")
    ap.add_argument("--probe", action="store_true", help="calculate only, do not write")
    ap.add_argument("--above", type=int, default=0, help="crop this many points from the top")
    ap.add_argument("--right", type=int, default=0, help="crop this many points from the right")
    ap.add_argument("--below", type=int, default=0, help="crop this many points from the bottom")
    ap.add_argument("--left", type=int, default=0, help="trim this many points from the left")
    ap.add_argument("--each", type=int, default=1, help="use every n-th image only")
    ap.add_argument("--zeitgleich", action="store_true", help="original image duration instead of fixed image duration")
    ap.add_argument("--luecke-max", type=int, default=0, help="cut long pauses (ms) to this value")
    ap.add_argument("--mitlaufen", type=int, default=0, help="camera follows movement; value = sensitivity (e.g. 12)")
    ap.add_argument("--fenster", default="1400x800", help="crop size for tracking (b x h)")
    ap.add_argument("--glaetten", type=float, default=0.6, help="seconds for smoothing the camera movement")
    ap.add_argument("--abschnitte", default="", help="time window like 6,3:11,6;15,28:15,65 (seconds)")
    ap.add_argument("--content", action="store_true", help="cut tightly to the action (without empty borders)")
    ap.add_argument("--content-margin", type=float, default=2.0, help="border when cropping content in percent")
    ap.add_argument("--frames", type=int, default=0, help="frame thickness in points (0 = none)")
    ap.add_argument("--frames-farbe", default="c9ced6", help="frame color as hex value")
    ap.add_argument("--title", default="", help="caption as bar above the image (e.g. “Radio-Agent · test run”)")
    ap.add_argument("--title-height", type=int, default=30, help="height of caption bar in points")
    ap.add_argument("--title-hintergrund", default="f2f4f7", help="background color of the bar")
    ap.add_argument("--title-schrift", default="333b47", help="Text color of the label")
    args = ap.parse_args()

    bericht_pfad = os.path.join(args.folder, "recording.json")
    zeiten, rate, report = [], args.rate, {}
    if os.path.exists(bericht_pfad):
        with open(bericht_pfad, encoding="utf-8") as f:
            report = json.load(f)
        zeiten = [b["t"] / 1000.0 for b in report.get("images", [])]
        if not rate and len(zeiten) > 2:
            abst = [zeiten[i + 1] - zeiten[i] for i in range(len(zeiten) - 1)]
            abst.sort()
            rate = 1.0 / abst[len(abst) // 2]
    if not rate:
        rate = args.time or 8.0
    rate = rate * args.speed

    names = bilder_lesen(args.folder)
    if not names:
        sys.exit("No images found in" + args.folder)
    if len(zeiten) != len(names):
        zeiten = [i / rate for i in range(len(names))]

    paare = []
    for i, name in enumerate(names):
        t = zeiten[i]
        if t < args.start:
            continue
        if args.end and t > args.end:
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
        print('Time window:', ', '.join(f'{a:.1f}-{b:.1f}s' for a, b in fenster))
    if not paare:
        sys.exit("No image in the selected time window")
    paare = paare[:: max(1, args.each)]
    print(f"{len(paare)} of {len(names)} images, tick {rate:.2f} images/s")

    images, dauern = [], []
    raw = []
    for i, (name, t) in enumerate(paare):
        im = Image.open(os.path.join(args.folder, name)).convert("RGB")
        raw.append(im)
        if args.zeitgleich and i + 1 < len(paare):
            d = (paare[i + 1][1] - t) / args.speed
            dauer_i = int(max(30, min(1000, d * 1000)))
            if args.luecke_max:
                dauer_i = min(dauer_i, args.luecke_max)
            dauern.append(dauer_i)
        else:
            dauern.append(max(20, round(1000.0 / rate)))

    if args.mitlaufen:
        fb, fh = [int(x) for x in args.fenster.lower().split("x")]
        raw = beschnitt(raw, report, args)
        focus = []
        before = None
        for im in raw:
            grau = im.convert("L")
            kasten = None
            if before is not None:
                d = ImageChops.difference(grau, before)
                kasten = d.point(lambda v: 255 if v > args.mitlaufen else 0).getbbox()
            focus.append(kasten)
            before = grau
        # Fill gaps (last known location), smooth midpoints
        last = (raw[0].width / 2, raw[0].height / 2)
        mittel = []
        for k in focus:
            if k:
                last = ((k[0] + k[2]) / 2, (k[1] + k[3]) / 2)
            mittel.append(last)
        fenster_bilder = max(1, int(args.glaetten * rate))
        geglaettet = []
        for i in range(len(mittel)):
            a = max(0, i - fenster_bilder)
            b = min(len(mittel), i + fenster_bilder + 1)
            xs = [mittel[j][0] for j in range(a, b)]
            ys = [mittel[j][1] for j in range(a, b)]
            geglaettet.append((sum(xs) / len(xs), sum(ys) / len(ys)))
        for im, (mx, my) in zip(raw, geglaettet):
            left = int(max(0, min(im.width - fb, mx - fb / 2)))
            above = int(max(0, min(im.height - fh, my - fh / 2)))
            im2 = im.crop((left, above, left + fb, above + fh))
            if args.breite and im2.width != args.breite:
                im2 = im2.resize((args.breite, round(im2.height * args.breite / im2.width)), Image.LANCZOS)
            images.append(im2)
    else:
        raw = beschnitt(raw, report, args)
        for im in raw:
            if args.breite and im.width != args.breite:
                im = im.resize((args.breite, round(im.height * args.breite / im.width)), Image.LANCZOS)
            images.append(im)

    pal = palette_bauen(images, args.colors)
    images = [b.quantize(palette=pal, dither=Image.FLOYDSTEINBERG) for b in images]

    if args.frames:
        from PIL import ImageDraw
        farbe = tuple(int(args.rahmen_farbe[i:i + 2], 16) for i in (0, 2, 4))
        for b in images:
            d = ImageDraw.Draw(b)
            for k in range(args.frames):
                d.rectangle([k, k, b.width - 1 - k, b.height - 1 - k], outline=farbe)

    if args.title:
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
        for b in images:
            blatt = Image.new("RGB", (b.width, b.height + args.titel_hoehe), hg)
            blatt.paste(b, (0, args.titel_hoehe))
            d = ImageDraw.Draw(blatt)
            d.line([(0, args.titel_hoehe - 1), (b.width, args.titel_hoehe - 1)], fill=trenn, width=1)
            d.text((12, args.titel_hoehe / 2), args.title, font=schrift, fill=fs, anchor="lm")
            mit_leiste.append(blatt)
        images = mit_leiste

    duration = max(20, round(1000.0 / rate))
    if args.probe:
        print("Test:" + str(len(images)) + " Images, total time" + str(sum(dauern) / 1000) + " s," + str(images[0].size))
        return
    images[0].save(args.target, save_all=True, append_images=images[1:], duration=dauern,
                   loop=args.schleife, optimize=True, disposal=2)
    groesse = os.path.getsize(args.target) / 1e6
    print(f"Written: {args.target} {groesse:.2f} MB {images[0].size[0]}x{images[0].size[1]}"
          f"{len(images)} images Runtime {sum(dauern) / 1000:.1f} s")


if __name__ == "__main__":
    main()
