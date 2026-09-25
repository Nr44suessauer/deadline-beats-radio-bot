#!/usr/bin/env node
// gif-aufnahme.js - nimmt den laufenden n8n-Ablauf als Bildfolge auf.
//
// Aufruf (Beispiel):
//   node gif-aufnahme.js aufnehmen --ablauf RadioAgentBot --ziel /tmp/gif/bilder \
//        --massstab 0.2 --dauer 45 --vorlauf 6 --befehl "spiele nirvana lithium"
//
// Weitere Modi:
//   node gif-aufnahme.js anmelden      sichtbares Fenster zum einmaligen Anmelden
//   node gif-aufnahme.js pruefen       Sitzung pruefen und Aufnahmeflaeche messen
//   node gif-aufnahme.js messen        nur vorbereiten + ein Probe-Bild ablegen
//
// Es werden keine Fremdpakete gebraucht: Browser-Protokoll (CDP) ueber die in
// Node eingebaute WebSocket-Schnittstelle.

const { spawn } = require('child_process');
const fs = require('fs');
const os = require('os');
const pfad = require('path');

const BRAVE = '/snap/bin/brave';
const VORGABE = {
  basis: 'https://DEIN-N8N-HOST',
  profil: pfad.join(os.homedir(), 'gif-aufnahme-profil-brave'),
  port: 9333,
  fenster: '2400x1400',
  takt: 8,            // Bilder je Sekunde (nur bei --aufnahmeart bilder)
  dauer: 45,          // Aufnahmedauer in Sekunden
  vorlauf: 6,         // Sekunden bis zum Auslösen des Testlaufs
  massstab: 0,        // 0 = einpassen
  rand: 0.06,         // Rand beim Einpassen
  wegweiser: null,    // JSON mit Kamerafahrten
  sichtbar: false,
  aufnahmeart: 'video',   // video = Bildschirmstrom (flüssig), bilder = Einzelbilder
  ausloesung: 'oberflaeche',  // oberflaeche = im Editor starten (nur so wird animiert), webbhook
  horchen: 3,         // Sekunden, die der Editor auf die Testadresse horcht
  guete: 88,          // JPEG-Güte des Bildschirmstroms
  schluesselDatei: '<dokuordner>/NACHBAU/zugangsdaten/bot-test-schluessel.txt',
  ablaufDatei: '<dokuordner>/NACHBAU/ablaeufe-laufend',
};

// Nur was in der Zeichenflaeche liegt und stoert. Die Zoomknoepfe werden erst
// NACH dem Einstellen ausgeblendet (sonst klickt man ins Leere - genau dieser
// Fehler hat den ersten Versuch gekostet).
const AUSBLENDEN = `
  [data-test-id="canvas-node-toolbar"], [data-test-id="canvas-handle-plus-wrapper"],
  [data-test-id="execute-node-button"], [data-test-id="canvas-node-input-handle"],
  [class*="executionButtons"] { display: none !important; }
`;

const AUSBLENDEN_SPAET = `
  [data-test-id="canvas-controls"], [data-test-id="canvas-minimap"],
  [class*="vue-flow__controls"], [data-test-id="zoom-to-fit"],
  [data-test-id="node-creator-plus-button"], [data-test-id="command-bar-button"],
  [data-test-id="add-sticky-button"], [data-test-id="toggle-focus-panel-button"]
    { display: none !important; }
`;

const warte = (ms) => new Promise(r => setTimeout(r, ms));

function argWerte() {
  const w = { modus: 'aufnehmen' };
  const rest = process.argv.slice(2);
  if (rest[0] && !rest[0].startsWith('--')) w.modus = rest.shift();
  for (let i = 0; i < rest.length; i++) {
    const a = rest[i];
    if (!a.startsWith('--')) continue;
    const name = a.slice(2);
    const wert = (rest[i + 1] && !rest[i + 1].startsWith('--')) ? rest[++i] : true;
    w[name.replace(/-([a-z])/g, (m, c) => c.toUpperCase())] = wert;
  }
  return { ...VORGABE, ...w };
}

async function holeJson(adresse, versuche = 60) {
  for (let i = 0; i < versuche; i++) {
    try { const a = await fetch(adresse); if (a.ok) return await a.json(); } catch (e) {}
    await warte(250);
  }
  throw new Error('Browser antwortet nicht: ' + adresse);
}

class CDP {
  constructor(url) { this.url = url; this.nr = 0; this.offen = new Map(); this.horcher = new Map(); }
  verbinden() {
    return new Promise((gut, boese) => {
      this.ws = new WebSocket(this.url);
      this.ws.onopen = () => gut();
      this.ws.onerror = () => boese(new Error('WebSocket-Fehler'));
      this.ws.onmessage = (e) => {
        const d = JSON.parse(e.data);
        if (d.id && this.offen.has(d.id)) {
          const p = this.offen.get(d.id); this.offen.delete(d.id);
          d.error ? p.boese(new Error(JSON.stringify(d.error))) : p.gut(d.result);
        } else if (d.method && this.horcher.has(d.method)) {
          this.horcher.get(d.method).forEach(f => { try { f(d.params); } catch (err) {} });
        }
      };
    });
  }
  auf(ereignis, f) {
    if (!this.horcher.has(ereignis)) this.horcher.set(ereignis, []);
    this.horcher.get(ereignis).push(f);
  }
  ohneWarten(methode, params = {}) {
    this.ws.send(JSON.stringify({ id: ++this.nr, method: methode, params }));
  }
  senden(methode, params = {}) {
    const id = ++this.nr;
    return new Promise((gut, boese) => {
      this.offen.set(id, { gut, boese });
      this.ws.send(JSON.stringify({ id, method: methode, params }));
      setTimeout(() => { if (this.offen.has(id)) { this.offen.delete(id); boese(new Error('Zeitablauf ' + methode)); } }, 60000);
    });
  }
  async js(ausdruck) {
    const r = await this.senden('Runtime.evaluate', { expression: ausdruck, returnByValue: true, awaitPromise: true });
    if (r.exceptionDetails) throw new Error('JS-Fehler: ' + JSON.stringify(r.exceptionDetails).slice(0, 300));
    return r.result ? r.result.value : undefined;
  }
  async maus(art, x, y, zusatz = {}) {
    await this.senden('Input.dispatchMouseEvent', { type: art, x, y, button: 'none', ...zusatz });
  }
  async rad(x, y, deltaX, deltaY, modifiers = 0) {
    await this.senden('Input.dispatchMouseEvent', { type: 'mouseWheel', x, y, deltaX, deltaY, button: 'none', modifiers });
  }
  async cssRegel(auswahl, text) {
    return await this.js(`(() => { let s = document.getElementById('gif-ausblenden');
      if (!s) { s = document.createElement('style'); s.id = 'gif-ausblenden'; document.head.appendChild(s); s.textContent = ''; }
      s.textContent = s.textContent.replace(${JSON.stringify('/*SPAET*/')}, '') + ${JSON.stringify(text)};
      return 'ok'; })()`);
  }
  async stileSetzen(text) {
    return await this.js(`(() => { let s = document.getElementById('gif-ausblenden');
      if (!s) { s = document.createElement('style'); s.id = 'gif-ausblenden'; document.head.appendChild(s); }
      s.textContent = ${JSON.stringify(text)}; return 'ok'; })()`);
  }
  async klick(x, y) {
    await this.senden('Input.dispatchMouseEvent', { type: 'mousePressed', x, y, button: 'left', clickCount: 1 });
    await this.senden('Input.dispatchMouseEvent', { type: 'mouseReleased', x, y, button: 'left', clickCount: 1 });
  }
  async bild(datei, ausschnitt) {
    const p = { format: 'png', captureBeyondViewport: false };
    if (ausschnitt) p.clip = { x: ausschnitt.x, y: ausschnitt.y, width: ausschnitt.b, height: ausschnitt.h, scale: 1 };
    const b = await this.senden('Page.captureScreenshot', p);
    fs.writeFileSync(datei, Buffer.from(b.data, 'base64'));
    return datei;
  }
}

// ---------------------------------------------------------------- Ablauf kenntlich machen

function ablaufLesen(ordner, name) {
  const datei = pfad.join(ordner, name + '.json');
  if (!fs.existsSync(datei)) throw new Error('Ablaufdatei fehlt: ' + datei);
  const j = JSON.parse(fs.readFileSync(datei, 'utf8'));
  const ablauf = Array.isArray(j) ? j[0] : j;
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const k of ablauf.nodes || []) {
    const p = k.position || [0, 0];
    const pa = k.parameters || {};
    const b = Number(pa.width) || 200, h = Number(pa.height) || 150;
    x0 = Math.min(x0, p[0]); y0 = Math.min(y0, p[1]);
    x1 = Math.max(x1, p[0] + b); y1 = Math.max(y1, p[1] + h);
  }
  return { ablauf, flaeche: { x0, y0, x1, y1 } };
}

function knotenPunkt(ablauf, name) {
  const k = (ablauf.nodes || []).find(n => n.name === name);
  if (!k) return null;
  return { x: k.position[0] + 100, y: k.position[1] + 75 };
}

// ---------------------------------------------------------------- Zeichenflaeche

class Flaeche {
  constructor(cdp) { this.cdp = cdp; }

  async masse() {
    const t = await this.cdp.js(`(() => {
      const e = document.querySelector('[data-test-id="canvas"]');
      if (!e) return 'null';
      const r = e.getBoundingClientRect();
      // Die Verschiebung sitzt auf .vue-flow__transformationpane (nicht auf .vue-flow__viewport).
      // Bewusst ohne Regex gelesen - im Template-Text verschluckt JavaScript sonst Backslashes.
      const vp = document.querySelector('.vue-flow__transformationpane') || document.querySelector('.vue-flow__viewport');
      let s = 1, tx = 0, ty = 0;
      if (vp) {
        const cs = getComputedStyle(vp).transform || '';
        if (cs.indexOf('matrix(') === 0) {
          const z = cs.slice(7, -1).split(',').map(Number);
          if (z.length === 6 && isFinite(z[0])) { s = z[0]; tx = z[4]; ty = z[5]; }
        }
      }
      return JSON.stringify({ x: r.x, y: r.y, b: r.width, h: r.height, s: s, tx: tx, ty: ty });
    })()`);
    if (t === 'null' || t === undefined) return null;
    return JSON.parse(t);
  }

  async knotenZahl() {
    return await this.cdp.js(`document.querySelectorAll('.vue-flow__node, [data-test-id="canvas-node"]').length`);
  }

  async stillstand(warten = true) {
    let vorher = null;
    for (let i = 0; i < 40; i++) {
      const m = await this.masse();
      if (m && vorher && Math.abs(m.tx - vorher.tx) < 0.5 && Math.abs(m.ty - vorher.ty) < 0.5 && Math.abs(m.s - vorher.s) < 0.002) {
        if (!warten) return m;
        await warte(700);
        const m2 = await this.masse();
        if (m2 && Math.abs(m2.tx - m.tx) < 0.5 && Math.abs(m2.ty - m.ty) < 0.5) return m2;
      }
      vorher = m;
      await warte(120);
    }
    return await this.masse();
  }

  async knopfKlick(name) {
    const r = await this.cdp.js(`(() => { const e = document.querySelector('[data-test-id="${name}"]');
      if (!e) return 'null'; const b = e.getBoundingClientRect();
      return JSON.stringify({ x: b.x + b.width / 2, y: b.y + b.height / 2 }); })()`);
    if (r === 'null' || r === undefined) throw new Error('Bedienelement fehlt: ' + name);
    const p = JSON.parse(r);
    await this.cdp.maus('mouseMoved', p.x, p.y);
    await this.cdp.klick(p.x, p.y);
    return p;
  }

  // Gemessen am 2026-09-22: Mausrad verschiebt NUR (Strg ändert nichts),
  // der Maßstab geht ausschließlich über die Knöpfe (×1,2 bzw. ÷1,2 je Klick).
  // Genauer als ein halber Knopfschritt geht es nicht - sonst pendelt es.
  async massstabSetzen(ziel) {
    let richtungen = [];
    for (let i = 0; i < 30; i++) {
      const m = await this.masse();
      if (!m) break;
      const ver = ziel / m.s;
      if (Math.abs(Math.log(ver)) < 0.09) return m.s;
      const richtung = ver > 1 ? 'rein' : 'raus';
      if (richtungen.length >= 2 && richtung !== richtungen[richtungen.length - 1]
          && richtung === richtungen[richtungen.length - 2]) return m.s;
      richtungen.push(richtung);
      await this.knopfKlick(richtung === 'rein' ? 'zoom-in-button' : 'zoom-out-button');
      await warte(180);
    }
    return (await this.masse()).s;
  }

  async eichen(mx, my) {
    const vor = await this.masse();
    await this.cdp.rad(mx, my, 100, 0);
    await warte(400);
    const nachX = await this.masse();
    await this.cdp.rad(mx, my, 0, 100);
    await warte(400);
    const nachY = await this.masse();
    this.kx = (nachX.tx - vor.tx) / 100;
    this.ky = (nachY.ty - nachX.ty) / 100;
    if (!isFinite(this.kx) || Math.abs(this.kx) < 1e-4) this.kx = -0.5;
    if (!isFinite(this.ky) || Math.abs(this.ky) < 1e-4) this.ky = -0.5;
    return { kx: this.kx, ky: this.ky };
  }

  async fahreZu(tx, ty, zielS, mitten) {
    if (zielS && Math.abs(Math.log((await this.masse()).s / zielS)) > 0.09) await this.massstabSetzen(zielS);
    for (let i = 0; i < 6; i++) {
      const m = await this.masse();
      const dx = tx - m.tx, dy = ty - m.ty;
      if (Math.abs(dx) < 3 && Math.abs(dy) < 3) break;
      await this.cdp.rad(mitten.x, mitten.y, dx / this.kx, dy / this.ky);
      await warte(420);
    }
    await warte(150);
    return await this.masse();
  }
}

// ---------------------------------------------------------------- Aufnahme

(async () => {
  const w = argWerte();
  const { ablauf, flaeche } = ablaufLesen(w.ablaufDatei, w.ablauf);
  const schluessel = fs.readFileSync(w.schluesselDatei, 'utf8').trim();
  const webbhook = `${w.basis}/webhook/DEIN-WEBHOOK-PFAD?schluessel=${encodeURIComponent(schluessel)}`;

  fs.mkdirSync(w.profil, { recursive: true });
  const ziel = w.ziel || '/tmp/gif-aufnahme/bilder';
  fs.mkdirSync(ziel, { recursive: true });

  const aufruf = [
    '--remote-debugging-port=' + w.port,
    '--user-data-dir=' + w.profil,
    '--no-first-run', '--no-default-browser-check',
    '--disable-features=Translate',
    '--window-size=' + w.fenster,
    'about:blank',
  ];
  if (!w.sichtbar) aufruf.unshift('--headless=new');
  const kind = spawn(BRAVE, aufruf, { detached: true, stdio: ['ignore', 'ignore', 'ignore'] });

  let cdp = null;
  const bericht = { ablauf: w.ablauf, begonnen: new Date().toISOString(), fenster: w.fenster,
    masse: null, massstab: null, flaeche: flaeche, bilder: [], kamera: [], eichung: null };
  try {
    const ziele = await holeJson(`http://127.0.0.1:${w.port}/json/list`);
    const seite = ziele.find(z => z.type === 'page');
    cdp = new CDP(seite.webSocketDebuggerUrl);
    await cdp.verbinden();
    await cdp.senden('Page.enable');
    await cdp.senden('Runtime.enable');
    await cdp.senden('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-color-scheme', value: 'light' }] });
    const [fzB, fzH] = String(w.fenster).split('x').map(Number);
    await cdp.senden('Emulation.setDeviceMetricsOverride', { width: fzB, height: fzH, deviceScaleFactor: Number(w.schaerfe || 1), mobile: false });

    const adresse = `${w.basis}/workflow/${ablauf.id || w.ablauf}`;
    await cdp.senden('Page.navigate', { url: adresse });
    let ok = false;
    for (let i = 0; i < 60; i++) {
      await warte(500);
      const n = await flaecheZahl(cdp);
      const pfadJetzt = await cdp.js('location.pathname');
      if (String(pfadJetzt).includes('/signin')) throw new Error('Nicht angemeldet (Anmeldeseite) — bitte erst "anmelden" ausführen.');
      if (n >= 3) { ok = true; break; }
    }
    if (!ok) throw new Error('Zeichenfläche wurde nicht sichtbar');
    console.log('Ablauf geladen:', adresse);

    await cdp.maus('mouseMoved', 5, 800);
    await warte(600);

    const fl = new Flaeche(cdp);
    const m0 = await fl.masse();
    bericht.masse = m0;
    fl.bildAusschnitt = { x: m0.x, y: m0.y, b: m0.b, h: m0.h };   // nur die Zeichenfläche aufnehmen
    console.log(`Fläche ${m0.b}x${m0.h} ab (${m0.x},${m0.y}), Maßstab ${m0.s}`);

    // Zielmaßstab: einpassen oder vorgegeben
    const bw = flaeche.x1 - flaeche.x0, bh = flaeche.y1 - flaeche.y0;
    const einpass = Math.min((m0.b * (1 - 2 * w.rand)) / bw, (m0.h * (1 - 2 * w.rand)) / bh);
    console.log(`Ablauf ${bw.toFixed(0)}x${bh.toFixed(0)} Einheiten, rechnerisches Einpassmaß ${einpass.toFixed(3)}`);

    const mitten = { x: m0.x + m0.b / 2, y: m0.y + m0.h / 2 };
    await fl.knopfKlick('zoom-to-fit');
    await warte(700);
    let zielS;
    if (Number(w.massstab) > 0) {
      zielS = Number(w.massstab);
      console.log(`Maßstab vorgegeben ${zielS.toFixed(3)} (Einpass wäre ${einpass.toFixed(3)})`);
      await fl.massstabSetzen(zielS);
      zielS = (await fl.masse()).s;
    } else {
      zielS = (await fl.masse()).s;   // n8n passt selbst ein - alles bleibt sichtbar
      console.log(`Einpassmaßstab von n8n: ${zielS.toFixed(4)}`);
    }
    bericht.massstab = zielS;
    bericht.eichung = await fl.eichen(mitten.x, mitten.y);
    console.log('Verschiebemaß:', JSON.stringify(bericht.eichung));

    // Mittelpunkt des sichtbaren Bereichs auf die Mitte des Ablaufs legen
    const cx = (flaeche.x0 + flaeche.x1) / 2, cy = (flaeche.y0 + flaeche.y1) / 2;
    const zielTx = mitten.x - m0.x - cx * zielS;
    const zielTy = mitten.y - m0.y - cy * zielS;
    const stand = await fl.fahreZu(zielTx, zielTy, zielS, mitten);
    console.log(`Kamera steht: Maßstab ${stand.s.toFixed(3)}, tx ${stand.tx.toFixed(0)}, ty ${stand.ty.toFixed(0)}`);

    // Auslösung: nur ein Lauf aus der Oberfläche wird gezeichnet (am 2026-09-22 gemessen:
    // ein Lauf über die Produktivadresse ändert das Bild überhaupt nicht).
    let webhookKnoten = (ablauf.nodes || []).find(k => /webhook|formTrigger/i.test(k.type) && k.parameters && k.parameters.path);
    if (!webhookKnoten) webhookKnoten = (ablauf.nodes || []).find(k => /webhook/i.test(k.type));
    const testPfad = webhookKnoten && webhookKnoten.parameters && webhookKnoten.parameters.path;
    let ausloeseAdresse = webbhook;
    if (String(w.ausloesung) === 'oberflaeche') {
      if (!webhookKnoten || !testPfad) throw new Error('Kein Webhook-Knoten im Ablauf gefunden');
      ausloeseAdresse = `${w.basis}/webhook-test/${testPfad}?schluessel=${encodeURIComponent(schluessel)}`;
      const kp = knotenPunkt(ablauf, webhookKnoten.name) || { x: cx, y: cy };
      await fl.fahreZu(mitten.x - m0.x - kp.x * zielS, mitten.y - m0.y - kp.y * zielS, zielS, mitten);
      await warte(400);
      const rk = await cdp.js(`(() => { const n = [...document.querySelectorAll('.vue-flow__node')]
        .find(e => (e.innerText || '').indexOf(${JSON.stringify(webhookKnoten.name)}) >= 0);
        if (!n) return 'null'; const r = n.getBoundingClientRect();
        return JSON.stringify({ x: r.x + r.width / 2, y: r.y + r.height / 2 }); })()`);
      if (rk !== 'null' && rk !== undefined) {
        const q = JSON.parse(rk);
        await cdp.maus('mouseMoved', q.x, q.y);
        await warte(500);
      }
      await fl.knopfKlick('execute-workflow-button-' + webhookKnoten.name);
      await warte(600);
      const horcht = await cdp.js(`(document.body.innerText.match(/Waiting|listening|wartet/gi) || []).length`);
      console.log(`Editor auf Auslösung gestellt (${webhookKnoten.name}, horcht: ${horcht ? 'ja' : 'nicht erkannt'})`);
      bericht.ausloesung = { art: 'oberflaeche', knoten: webhookKnoten.name, adresse: ausloeseAdresse };
    } else {
      bericht.ausloesung = { art: 'webbhook', adresse: ausloeseAdresse };
    }
    await fl.fahreZu(zielTx, zielTy, zielS, mitten);
    bericht.endstand = await fl.masse();   // endgültige Lage (für den Inhaltsbeschnitt)
    bericht.masse = bericht.endstand;
    // Echte Inhaltsgrenze: Vereinigung aller gezeichneten Knotenrechtecke (genauer als gerechnet)
    bericht.inhalt = JSON.parse(await cdp.js(`(() => {
      let x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9;
      document.querySelectorAll('.vue-flow__node').forEach(e => {
        const b = e.getBoundingClientRect();
        if (!b.width) return;
        x0 = Math.min(x0, b.x); y0 = Math.min(y0, b.y);
        x1 = Math.max(x1, b.right); y1 = Math.max(y1, b.bottom);
      });
      return JSON.stringify({ x0: x0, y0: y0, x1: x1, y1: y1 });
    })()`) || null);
    if (bericht.inhalt && isFinite(bericht.inhalt.x0)) {
      const i = bericht.inhalt;
      console.log(`Inhalt laut Rechtecken: ${Math.round(i.x1 - i.x0)}x${Math.round(i.y1 - i.y0)} Punkte ab ${Math.round(i.x0)},${Math.round(i.y0)}`);
    }

    // Bedienelemente erst jetzt ausblenden (vorher werden sie zum Zoomen gebraucht)
    await cdp.stileSetzen(AUSBLENDEN + AUSBLENDEN_SPAET);
    await cdp.maus('mouseMoved', 5, 800);
    await warte(500);
    const kontrolle = await cdp.js(`(() => {
      const namen = ['canvas-controls', 'canvas-minimap', 'zoom-to-fit', 'logs-panel'];
      const aus = namen.map(n => { const e = document.querySelector('[data-test-id="' + n + '"]');
        return n + '=' + (e ? getComputedStyle(e).display : 'fehlt'); });
      aus.push('vue-flow__controls=' + document.querySelectorAll('.vue-flow__controls').length + ' Stück');
      aus.push('Stilblock=' + (document.getElementById('gif-ausblenden') ? 'da' : 'fehlt'));
      return aus.join(', ');
    })()`);
    console.log('Ausblenden:', kontrolle);

    if (w.modus === 'messen') {
      await fl.stillstand();
      await cdp.bild(pfad.join(ziel, 'probe.png'), fl.bildAusschnitt);
      console.log('Probe-Bild:', pfad.join(ziel, 'probe.png'));
    } else {
      // ---- Aufnahme (Video = Bildschirmstrom, sonst Einzelbilder)
      const weg = w.wegweiser ? JSON.parse(fs.readFileSync(w.wegweiser, 'utf8')) : [];
      const t0 = Date.now();
      const ende = t0 + Number(w.dauer) * 1000;
      let nr = 0, ausgelöst = false, naechsterWeg = 0, takt = 1000 / Number(w.takt);
      if (w.aufnahmeart === 'bilder') {
        cdp.auf('Page.screencastFrame', () => {});   // nicht nötig, Platzhalter
      } else {
        cdp.auf('Page.screencastFrame', (p) => {
          const name = `bild-${String(++nr).padStart(5, '0')}.jpg`;
          fs.writeFileSync(pfad.join(ziel, name), Buffer.from(p.data, 'base64'));
          bericht.bilder.push({ datei: name, t: Date.now() - t0 });
          cdp.ohneWarten('Page.screencastFrameAck', { sessionId: p.sessionId });
        });
        await cdp.senden('Page.startScreencast', { format: 'jpeg', quality: Number(w.guete),
          maxWidth: fzB, maxHeight: fzH, everyNthFrame: 1 });
      }
      console.log(`Aufnahme läuft (${w.aufnahmeart}): ${w.dauer} s, Auslösung nach ${w.vorlauf} s`);
      let naechsteBildzeit = 0;
      while (Date.now() < ende) {
        const lauf = Date.now() - t0;
        if (!ausgelöst && lauf >= Number(w.vorlauf) * 1000) {
          ausgelöst = true;
          const t = await fetch(ausloeseAdresse, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: { message_id: 1, chat: { id: 1, type: 'private' },
              from: { id: 1, first_name: 'Test' }, text: String(w.befehl || '/hilfe') } }),
          });
          bericht.ausloesung.zeit = lauf; bericht.ausloesung.status = t.status;
          bericht.ausloesung.befehl = w.befehl;
          console.log(`  Ausgelöst nach ${(lauf / 1000).toFixed(1)} s → HTTP ${t.status}`);
        }
        if (weg.length && naechsterWeg < weg.length && lauf >= weg[naechsterWeg].ab) {
          const s = weg[naechsterWeg++];
          const p = s.knoten ? knotenPunkt(ablauf, s.knoten) : { x: s.x, y: s.y };
          if (p) {
            const ms = s.massstab || zielS;
            await fl.fahreZu(mitten.x - m0.x - p.x * ms, mitten.y - m0.y - p.y * ms, ms, mitten);
            bericht.kamera.push({ ab: lauf, knoten: s.knoten || null, massstab: ms });
          }
        }
        if (w.aufnahmeart !== 'bilder' && lauf < naechsteBildzeit) { await warte(50); continue; }
        if (w.aufnahmeart === 'bilder') {
          const name = `bild-${String(++nr).padStart(5, '0')}.png`;
          await cdp.bild(pfad.join(ziel, name), fl.bildAusschnitt);
          bericht.bilder.push({ datei: name, t: Date.now() - t0 });
          naechsteBildzeit = Date.now() - t0 + takt;
        }
        await warte(50);
      }
      if (w.aufnahmeart !== 'bilder') await cdp.senden('Page.stopScreencast');
      console.log(`Fertig: ${bericht.bilder.length} Bilder in ${ziel}`);
    }
  } catch (e) {
    bericht.fehler = e.message;
    console.log('FEHLER:', e.message);
  } finally {
    bericht.beendet = new Date().toISOString();
    fs.writeFileSync(pfad.join(ziel, 'aufnahme.json'), JSON.stringify(bericht, null, 1));
    console.log('Bericht:', pfad.join(ziel, 'aufnahme.json'));
    try { cdp && cdp.ws.close(); } catch (e) {}
    try { process.kill(-kind.pid); } catch (e) { try { kind.kill(); } catch (e2) {} }
    try { require('child_process').execSync('pkill -9 -f "user-data-dir=' + w.profil + '"', { stdio: 'ignore' }); } catch (e) {}
    try { fs.rmSync(pfad.join(w.profil, 'SingletonLock'), { force: true }); } catch (e) {}
    await warte(1200);
  }
})();

async function flaecheZahl(cdp) {
  try { return await cdp.js(`document.querySelectorAll('.vue-flow__node, [data-test-id="canvas-node"]').length`); }
  catch (e) { return 0; }
}
