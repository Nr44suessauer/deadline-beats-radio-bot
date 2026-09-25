#!/usr/bin/env node
// gif-recording.js - records the running n8n workflow as a frame sequence.
//
// Call (example):
//   node gif-recording.js record --workflow RadioAgentBot --target /tmp/gif/images \
//        --scale 0.2 --duration 45 --lead 6 --command "play nirvana lithium"
//
// Weitere Modi:
//   node gif-recording.js login      sichtbares Fenster to the einmaligen login
//   node gif-recording.js check        check the session and measure the capture area
//   node gif-recording.js measure        only vorbereiten + input test-Bild ablegen
//
// No third-party packages are needed: browser protocol (CDP) over the in
// Node eingebaute WebSocket-Schnittstelle.

const { spawn } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

const BRAVE = '/snap/bin/brave';
const VORGABE = {
  basis: 'https://YOUR-N8N-HOST',
  profil: path.join(os.homedir(), 'gif-recording-profil-brave'),
  port: 9333,
  fenster: '2400x1400',
  rate: 8,            // frames per second (only with --recordingType images)
  duration: 45,          // Aufnahmedauer in seconds
  lead: 6,         // seconds until the test run is triggered
  scale: 0,        // 0 = fit
  margin: 0.06,         // Rand with Einpassen
  waypoints: null,    // JSON with camera moves
  sichtbar: false,
  recordingType: 'video',   // video = screen stream (smooth), images = single frames
  trigger: 'oberflaeche',  // oberflaeche = im Editor starten (only so is animiert), webbhook
  wait: 3,         // seconds the editor listens on the test address
  quality: 88,          // JPEG quality of the screen stream
  schluesselDatei: '<dokuordner>/bot-test-key.txt',
  ablaufDatei: '<dokuordner>/REPLIKATION/workflows-running',
};

// Only what lies on the canvas and disturbs. The zoom buttons are only
// hidden AFTER fitting (otherwise you click into the void - exactly this
// mistake cost the first attempt).
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
  const w = { modus: 'record' };
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

async function holeJson(adresse, attempts = 60) {
  for (let i = 0; i < attempts; i++) {
    try { const a = await fetch(adresse); if (a.ok) return await a.json(); } catch (e) {}
    await warte(250);
  }
  throw new Error('Browser does not respond: ' + adresse);
}

class CDP {
  constructor(url) { this.url = url; this.nr = 0; this.open = new Map(); this.horcher = new Map(); }
  connect() {
    return new Promise((good, reject) => {
      this.ws = new WebSocket(this.url);
      this.ws.onopen = () => good();
      this.ws.onerror = () => reject(new Error('WebSocket-error'));
      this.ws.onmessage = (e) => {
        const d = JSON.parse(e.data);
        if (d.id && this.open.has(d.id)) {
          const p = this.open.get(d.id); this.open.delete(d.id);
          d.error ? p.reject(new Error(JSON.stringify(d.error))) : p.good(d.result);
        } else if (d.method && this.horcher.has(d.method)) {
          this.horcher.get(d.method).forEach(f => { try { f(d.params); } catch (err) {} });
        }
      };
    });
  }
  on(ereignis, f) {
    if (!this.horcher.has(ereignis)) this.horcher.set(ereignis, []);
    this.horcher.get(ereignis).push(f);
  }
  ohneWarten(method, params = {}) {
    this.ws.send(JSON.stringify({ id: ++this.nr, method: method, params }));
  }
  send(method, params = {}) {
    const id = ++this.nr;
    return new Promise((good, reject) => {
      this.open.set(id, { good, reject });
      this.ws.send(JSON.stringify({ id, method: method, params }));
      setTimeout(() => { if (this.open.has(id)) { this.open.delete(id); reject(new Error('Zeitablauf ' + method)); } }, 60000);
    });
  }
  async js(expression) {
    const r = await this.send('Runtime.evaluate', { expression: expression, returnByValue: true, awaitPromise: true });
    if (r.exceptionDetails) throw new Error('JS error: ' + JSON.stringify(r.exceptionDetails).slice(0, 300));
    return r.result ? r.result.value : undefined;
  }
  async mouse(type, x, y, extra = {}) {
    await this.send('Input.dispatchMouseEvent', { type: type, x, y, button: 'none', ...extra });
  }
  async rad(x, y, deltaX, deltaY, modifiers = 0) {
    await this.send('Input.dispatchMouseEvent', { type: 'mouseWheel', x, y, deltaX, deltaY, button: 'none', modifiers });
  }
  async cssRegel(selection, text) {
    return await this.js(`(() => { let s = document.getElementById('gif-hide');
      if (!s) { s = document.createElement('style'); s.id = 'gif-hide'; document.head.appendChild(s); s.textContent = ''; }
      s.textContent = s.textContent.replace(${JSON.stringify('/*SPAET*/')}, '') + ${JSON.stringify(text)};
      return 'ok'; })()`);
  }
  async stileSetzen(text) {
    return await this.js(`(() => { let s = document.getElementById('gif-hide');
      if (!s) { s = document.createElement('style'); s.id = 'gif-hide'; document.head.appendChild(s); }
      s.textContent = ${JSON.stringify(text)}; return 'ok'; })()`);
  }
  async klick(x, y) {
    await this.send('Input.dispatchMouseEvent', { type: 'mousePressed', x, y, button: 'left', clickCount: 1 });
    await this.send('Input.dispatchMouseEvent', { type: 'mouseReleased', x, y, button: 'left', clickCount: 1 });
  }
  async bild(file, crop) {
    const p = { format: 'png', captureBeyondViewport: false };
    if (crop) p.clip = { x: crop.x, y: crop.y, width: crop.b, height: crop.h, scale: 1 };
    const b = await this.send('Page.captureScreenshot', p);
    fs.writeFileSync(file, Buffer.from(b.data, 'base64'));
    return file;
  }
}

// ---------------------------------------------------------------- workflow kenntlich machen

function readWorkflow(folder, name) {
  const file = path.join(folder, name + '.json');
  if (!fs.existsSync(file)) throw new Error('Workflow file missing: ' + file);
  const j = JSON.parse(fs.readFileSync(file, 'utf8'));
  const workflow = Array.isArray(j) ? j[0] : j;
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const k of workflow.nodes || []) {
    const p = k.position || [0, 0];
    const pa = k.parameters || {};
    const b = Number(pa.width) || 200, h = Number(pa.height) || 150;
    x0 = Math.min(x0, p[0]); y0 = Math.min(y0, p[1]);
    x1 = Math.max(x1, p[0] + b); y1 = Math.max(y1, p[1] + h);
  }
  return { workflow, area: { x0, y0, x1, y1 } };
}

function knotenPunkt(workflow, name) {
  const k = (workflow.nodes || []).find(n => n.name === name);
  if (!k) return null;
  return { x: k.position[0] + 100, y: k.position[1] + 75 };
}

// ---------------------------------------------------------------- canvas

class canvas {
  constructor(cdp) { this.cdp = cdp; }

  async masse() {
    const t = await this.cdp.js(`(() => {
      const e = document.querySelector('[data-test-id="canvas"]');
      if (!e) return 'null';
      const r = e.getBoundingClientRect();
      // Die Verschiebung sitzt on .vue-flow__transformationpane (not on .vue-flow__viewport).
      // deliberately without Regex gelesen - im Template-Text swallows JavaScript otherwise Backslashes.
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
    let before = null;
    for (let i = 0; i < 40; i++) {
      const m = await this.masse();
      if (m && before && Math.abs(m.tx - before.tx) < 0.5 && Math.abs(m.ty - before.ty) < 0.5 && Math.abs(m.s - before.s) < 0.002) {
        if (!warten) return m;
        await warte(700);
        const m2 = await this.masse();
        if (m2 && Math.abs(m2.tx - m.tx) < 0.5 && Math.abs(m2.ty - m.ty) < 0.5) return m2;
      }
      before = m;
      await warte(120);
    }
    return await this.masse();
  }

  async knopfKlick(name) {
    const r = await this.cdp.js(`(() => { const e = document.querySelector('[data-test-id="${name}"]');
      if (!e) return 'null'; const b = e.getBoundingClientRect();
      return JSON.stringify({ x: b.x + b.width / 2, y: b.y + b.height / 2 }); })()`);
    if (r === 'null' || r === undefined) throw new Error('Control missing: ' + name);
    const p = JSON.parse(r);
    await this.cdp.mouse('mouseMoved', p.x, p.y);
    await this.cdp.klick(p.x, p.y);
    return p;
  }

  // Gemessen am 2026-09-22: mouse wheel pans ONLY (Ctrl changes nothing),
  // the scale only works via the buttons (×1.2 or ÷1.2 per click).
  // Genauer als input half button step goes es not - otherwise oscillates es.
  async massstabSetzen(target) {
    let richtungen = [];
    for (let i = 0; i < 30; i++) {
      const m = await this.masse();
      if (!m) break;
      const ver = target / m.s;
      if (Math.abs(Math.log(ver)) < 0.09) return m.s;
      const direction = ver > 1 ? 'in' : 'out';
      if (richtungen.length >= 2 && direction !== richtungen[richtungen.length - 1]
          && direction === richtungen[richtungen.length - 2]) return m.s;
      richtungen.push(direction);
      await this.knopfKlick(direction === 'in' ? 'zoom-in-button' : 'zoom-out-button');
      await warte(180);
    }
    return (await this.masse()).s;
  }

  async eichen(mx, my) {
    const before = await this.masse();
    await this.cdp.rad(mx, my, 100, 0);
    await warte(400);
    const nachX = await this.masse();
    await this.cdp.rad(mx, my, 0, 100);
    await warte(400);
    const nachY = await this.masse();
    this.kx = (nachX.tx - before.tx) / 100;
    this.ky = (nachY.ty - nachX.ty) / 100;
    if (!isFinite(this.kx) || Math.abs(this.kx) < 1e-4) this.kx = -0.5;
    if (!isFinite(this.ky) || Math.abs(this.ky) < 1e-4) this.ky = -0.5;
    return { kx: this.kx, ky: this.ky };
  }

  async moveTo(tx, ty, zielS, center) {
    if (zielS && Math.abs(Math.log((await this.masse()).s / zielS)) > 0.09) await this.massstabSetzen(zielS);
    for (let i = 0; i < 6; i++) {
      const m = await this.masse();
      const dx = tx - m.tx, dy = ty - m.ty;
      if (Math.abs(dx) < 3 && Math.abs(dy) < 3) break;
      await this.cdp.rad(center.x, center.y, dx / this.kx, dy / this.ky);
      await warte(420);
    }
    await warte(150);
    return await this.masse();
  }
}

// ---------------------------------------------------------------- recording

(async () => {
  const w = argWerte();
  const { workflow, area } = readWorkflow(w.ablaufDatei, w.workflow);
  const key = fs.readFileSync(w.schluesselDatei, 'utf8').trim();
  const webbhook = `${w.basis}/webhook/YOUR-WEBHOOK-PATH?key=${encodeURIComponent(key)}`;

  fs.mkdirSync(w.profil, { recursive: true });
  const target = w.target || '/tmp/gif-recording/images';
  fs.mkdirSync(target, { recursive: true });

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
  const report = { workflow: w.workflow, begonnen: new Date().toISOString(), fenster: w.fenster,
    masse: null, scale: null, area: area, images: [], camera: [], calibration: null };
  try {
    const targets = await holeJson(`http://127.0.0.1:${w.port}/json/list`);
    const seite = targets.find(z => z.type === 'page');
    cdp = new CDP(seite.webSocketDebuggerUrl);
    await cdp.connect();
    await cdp.send('Page.enable');
    await cdp.send('Runtime.enable');
    await cdp.send('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-color-scheme', value: 'light' }] });
    const [fzB, fzH] = String(w.fenster).split('x').map(Number);
    await cdp.send('Emulation.setDeviceMetricsOverride', { width: fzB, height: fzH, deviceScaleFactor: Number(w.sharpness || 1), mobile: false });

    const adresse = `${w.basis}/workflow/${workflow.id || w.workflow}`;
    await cdp.send('Page.navigate', { url: adresse });
    let ok = false;
    for (let i = 0; i < 60; i++) {
      await warte(500);
      const n = await flaecheZahl(cdp);
      const currentPath = await cdp.js('location.pathname');
      if (String(currentPath).includes('/signin')) throw new Error('Not logged in (login page) — please run "login" first.');
      if (n >= 3) { ok = true; break; }
    }
    if (!ok) throw new Error('Canvas did not become visible');
    console.log('Workflow loaded:', adresse);

    await cdp.mouse('mouseMoved', 5, 800);
    await warte(600);

    const fl = new canvas(cdp);
    const m0 = await fl.masse();
    report.masse = m0;
    fl.imageCrop = { x: m0.x, y: m0.y, b: m0.b, h: m0.h };   // record only the canvas
    console.log(`area ${m0.b}x${m0.h} ab (${m0.x},${m0.y}), Scale ${m0.s}`);

    // target scale: fit or given
    const bw = area.x1 - area.x0, bh = area.y1 - area.y0;
    const fit = Math.min((m0.b * (1 - 2 * w.margin)) / bw, (m0.h * (1 - 2 * w.margin)) / bh);
    console.log(`workflow ${bw.toFixed(0)}x${bh.toFixed(0)} units, computed fit measure ${fit.toFixed(3)}`);

    const center = { x: m0.x + m0.b / 2, y: m0.y + m0.h / 2 };
    await fl.knopfKlick('zoom-to-fit');
    await warte(700);
    let zielS;
    if (Number(w.scale) > 0) {
      zielS = Number(w.scale);
      console.log(`Scale given ${zielS.toFixed(3)} (fit would be ${fit.toFixed(3)})`);
      await fl.massstabSetzen(zielS);
      zielS = (await fl.masse()).s;
    } else {
      zielS = (await fl.masse()).s;   // n8n passt selbst input - everything bleibt sichtbar
      console.log(`fit scale from_ n8n: ${zielS.toFixed(4)}`);
    }
    report.scale = zielS;
    report.calibration = await fl.eichen(center.x, center.y);
    console.log('Drag offset:', JSON.stringify(report.calibration));

    // put the center of the visible area onto the center of the workflow
    const cx = (area.x0 + area.x1) / 2, cy = (area.y0 + area.y1) / 2;
    const zielTx = center.x - m0.x - cx * zielS;
    const zielTy = center.y - m0.y - cy * zielS;
    const stand = await fl.moveTo(zielTx, zielTy, zielS, center);
    console.log(`camera stopped: Scale ${stand.s.toFixed(3)}, tx ${stand.tx.toFixed(0)}, ty ${stand.ty.toFixed(0)}`);

    // trigger: only input Lauf out the UI is drawn (am 2026-09-22 measured:
    // a run via the production address does not change the image at all).
    let webhookNode = (workflow.nodes || []).find(k => /webhook|formTrigger/i.test(k.type) && k.parameters && k.parameters.path);
    if (!webhookNode) webhookNode = (workflow.nodes || []).find(k => /webhook/i.test(k.type));
    const testPfad = webhookNode && webhookNode.parameters && webhookNode.parameters.path;
    let ausloeseAdresse = webbhook;
    if (String(w.trigger) === 'oberflaeche') {
      if (!webhookNode || !testPfad) throw new Error('No webhook node found in the workflow');
      ausloeseAdresse = `${w.basis}/webhook-test/${testPfad}?key=${encodeURIComponent(key)}`;
      const kp = knotenPunkt(workflow, webhookNode.name) || { x: cx, y: cy };
      await fl.moveTo(center.x - m0.x - kp.x * zielS, center.y - m0.y - kp.y * zielS, zielS, center);
      await warte(400);
      const rk = await cdp.js(`(() => { const n = [...document.querySelectorAll('.vue-flow__node')]
        .find(e => (e.innerText || '').indexOf(${JSON.stringify(webhookNode.name)}) >= 0);
        if (!n) return 'null'; const r = n.getBoundingClientRect();
        return JSON.stringify({ x: r.x + r.width / 2, y: r.y + r.height / 2 }); })()`);
      if (rk !== 'null' && rk !== undefined) {
        const q = JSON.parse(rk);
        await cdp.mouse('mouseMoved', q.x, q.y);
        await warte(500);
      }
      await fl.knopfKlick('execute-workflow-button-' + webhookNode.name);
      await warte(600);
      const listens = await cdp.js(`(document.body.innerText.match(/Waiting|listening|wartet/gi) || []).length`);
      console.log(`Editor on trigger set (${webhookNode.name}, listens: ${listens ? 'ja' : 'not recognized'})`);
      report.trigger = { type: 'oberflaeche', nodes: webhookNode.name, adresse: ausloeseAdresse };
    } else {
      report.trigger = { type: 'webbhook', adresse: ausloeseAdresse };
    }
    await fl.moveTo(zielTx, zielTy, zielS, center);
    report.endstand = await fl.masse();   // final position (for the content crop)
    report.masse = report.endstand;
    // Echte Inhaltsgrenze: Vereinigung aller gezeichneten Knotenrechtecke (genauer als gerechnet)
    report.inhalt = JSON.parse(await cdp.js(`(() => {
      let x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9;
      document.querySelectorAll('.vue-flow__node').forEach(e => {
        const b = e.getBoundingClientRect();
        if (!b.width) return;
        x0 = Math.min(x0, b.x); y0 = Math.min(y0, b.y);
        x1 = Math.max(x1, b.right); y1 = Math.max(y1, b.bottom);
      });
      return JSON.stringify({ x0: x0, y0: y0, x1: x1, y1: y1 });
    })()`) || null);
    if (report.inhalt && isFinite(report.inhalt.x0)) {
      const i = report.inhalt;
      console.log(`Inhalt loud Rechtecken: ${Math.round(i.x1 - i.x0)}x${Math.round(i.y1 - i.y0)} Punkte ab ${Math.round(i.x0)},${Math.round(i.y0)}`);
    }

    // Bedienelemente first now hide (before are sie to the Zoomen gebraucht)
    await cdp.stileSetzen(AUSBLENDEN + AUSBLENDEN_SPAET);
    await cdp.mouse('mouseMoved', 5, 800);
    await warte(500);
    const kontrolle = await cdp.js(`(() => {
      const names = ['canvas-controls', 'canvas-minimap', 'zoom-to-fit', 'logs-panel'];
      const out = names.map(n => { const e = document.querySelector('[data-test-id="' + n + '"]');
        return n + '=' + (e ? getComputedStyle(e).display : 'missing'); });
      out.push('vue-flow__controls=' + document.querySelectorAll('.vue-flow__controls').length + ' pieces');
      out.push('Stilblock=' + (document.getElementById('gif-hide') ? 'da' : 'missing'));
      return out.join(', ');
    })()`);
    console.log('Hide:', kontrolle);

    if (w.modus === 'measure') {
      await fl.stillstand();
      await cdp.bild(path.join(target, 'probe.png'), fl.imageCrop);
      console.log('Sample image:', path.join(target, 'probe.png'));
    } else {
      // ---- recording (Video = screen stream, otherwise single frames)
      const weg = w.waypoints ? JSON.parse(fs.readFileSync(w.waypoints, 'utf8')) : [];
      const t0 = Date.now();
      const ende = t0 + Number(w.duration) * 1000;
      let nr = 0, triggered = false, nextPath = 0, rate = 1000 / Number(w.rate);
      if (w.recordingType === 'images') {
        cdp.on('Page.screencastFrame', () => {});   // not needed, placeholder
      } else {
        cdp.on('Page.screencastFrame', (p) => {
          const name = `bild-${String(++nr).padStart(5, '0')}.jpg`;
          fs.writeFileSync(path.join(target, name), Buffer.from(p.data, 'base64'));
          report.images.push({ file: name, t: Date.now() - t0 });
          cdp.ohneWarten('Page.screencastFrameAck', { sessionId: p.sessionId });
        });
        await cdp.send('Page.startScreencast', { format: 'jpeg', quality: Number(w.quality),
          maxWidth: fzB, maxHeight: fzH, everyNthFrame: 1 });
      }
      console.log(`recording is running (${w.recordingType}): ${w.duration} s, trigger after ${w.lead} s`);
      let naechsteBildzeit = 0;
      while (Date.now() < ende) {
        const run = Date.now() - t0;
        if (!triggered && run >= Number(w.lead) * 1000) {
          triggered = true;
          const t = await fetch(ausloeseAdresse, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: { message_id: 1, chat: { id: 1, type: 'private' },
              from: { id: 1, first_name: 'Test' }, text: String(w.command || '/help') } }),
          });
          report.trigger.time = run; report.trigger.status = t.status;
          report.trigger.command = w.command;
          console.log(`  triggered after ${(run / 1000).toFixed(1)} s → HTTP ${t.status}`);
        }
        if (weg.length && nextPath < weg.length && run >= weg[nextPath].ab) {
          const s = weg[nextPath++];
          const p = s.nodes ? knotenPunkt(workflow, s.nodes) : { x: s.x, y: s.y };
          if (p) {
            const ms = s.scale || zielS;
            await fl.moveTo(center.x - m0.x - p.x * ms, center.y - m0.y - p.y * ms, ms, center);
            report.camera.push({ ab: run, nodes: s.nodes || null, scale: ms });
          }
        }
        if (w.recordingType !== 'images' && run < naechsteBildzeit) { await warte(50); continue; }
        if (w.recordingType === 'images') {
          const name = `bild-${String(++nr).padStart(5, '0')}.png`;
          await cdp.bild(path.join(target, name), fl.imageCrop);
          report.images.push({ file: name, t: Date.now() - t0 });
          naechsteBildzeit = Date.now() - t0 + rate;
        }
        await warte(50);
      }
      if (w.recordingType !== 'images') await cdp.send('Page.stopScreencast');
      console.log(`Fertig: ${report.images.length} images in ${target}`);
    }
  } catch (e) {
    report.error = e.message;
    console.log('ERROR:', e.message);
  } finally {
    report.beendet = new Date().toISOString();
    fs.writeFileSync(path.join(target, 'recording.json'), JSON.stringify(report, null, 1));
    console.log('Report:', path.join(target, 'recording.json'));
    try { cdp && cdp.ws.close(); } catch (e) {}
    try { process.kill(-kind.pid); } catch (e) { try { kind.kill(); } catch (e2) {} }
    try { require('child_process').execSync('pkill -9 -f "user-data-dir=' + w.profil + '"', { stdio: 'ignore' }); } catch (e) {}
    try { fs.rmSync(path.join(w.profil, 'SingletonLock'), { force: true }); } catch (e) {}
    await warte(1200);
  }
})();

async function flaecheZahl(cdp) {
  try { return await cdp.js(`document.querySelectorAll('.vue-flow__node, [data-test-id="canvas-node"]').length`); }
  catch (e) { return 0; }
}
