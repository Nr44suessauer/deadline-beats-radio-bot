#!/usr/bin/env node
/**
 * Hörproben der eigenen Moderationsstimme „DEINE-STIMME“ erzeugen.
 *
 * Aufruf:
 *   node tools/stimmproben.mjs            # alle Proben neu sprechen
 *   EIGENE_STIMME=http://192.168.178.116:10205 node tools/stimmproben.mjs
 *   node tools/stimmproben.mjs --pruefen  # nur messen, nichts schreiben
 *
 * Der Sprechdienst (`sprechdienst`, LXC 111, Port 10205) wandelt edge-tts
 * (`de-DE-AmalaNeural`, +40 %) per RVC auf das Modell `<dein-modell>` um — dieselbe Kette
 * wie im Sender. Die Sätze hier sind **eigens für die Seite gesprochen**; das
 * Rohmaterial und das Modell werden nicht veröffentlicht (siehe Dokument
 * `STIMME.md`, Abschnitt 14).
 *
 * Ergebnis: `public/radio/downloads/deine-stimme/<datei>.mp3` — 22 050 Hz mono,
 * auf −16 LUFS gebracht (derselbe Pegel für alle Proben), ~80 kbit/s.
 * Die Dateien **müssen committet werden** (der Server spricht nicht selbst).
 *
 * Werkzeug ffmpeg: `$FFMPEG`, sonst ~/Applications/ffmpeg-7.0.2-amd64-static/ffmpeg,
 * sonst `ffmpeg` aus dem PATH (wie in tools/optimize-assets.mjs).
 */
import { spawnSync } from 'node:child_process'
import { existsSync, mkdirSync, rmSync, statSync, writeFileSync } from 'node:fs'
import { homedir } from 'node:os'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const HIER = dirname(fileURLToPath(import.meta.url))
const WURZEL = join(HIER, '..')
const ZIEL = join(WURZEL, 'public', 'radio', 'downloads', 'deine-stimme')
const DIENST = process.env.EIGENE_STIMME || 'http://192.168.178.116:10205'
const NUR_PRUEFEN = process.argv.includes('--pruefen')

// ── Werkzeug: ffmpeg / ffprobe ──────────────────────────────────────────────
function findTool(name) {
  if (process.env.FFMPEG) {
    if (name === 'ffmpeg') return process.env.FFMPEG
    const daneben = join(dirname(process.env.FFMPEG), name)
    if (existsSync(daneben)) return daneben
  }
  const statisch = join(homedir(), 'Applications', 'ffmpeg-7.0.2-amd64-static')
  const kandidat = join(statisch, name)
  if (existsSync(kandidat)) return kandidat
  return name
}
const FFMPEG = findTool('ffmpeg')
const FFPROBE = findTool('ffprobe')

// ── Die Sätze (hier ändern → Datei in src/data/radio/hoerproben.ts nachziehen) ──
const PROBEN = [
  {
    datei: 'deine-stimme-begruessung',
    titel: 'Begrüßung',
    text:
      'Willkommen bei Deadline Beats. Hier spricht DEINE-STIMME. Es ist spät geworden, der Server läuft warm und '
      + 'die Warteschlange ist leer – also machen wir es uns bequem und hören Musik aus dem eigenen Archiv.',
  },
  {
    datei: 'deine-stimme-wunsch',
    titel: 'Wunsch ansagen',
    text:
      'Der Wunsch ist unterwegs: Ich schiebe den Titel direkt in die Unterbrecher-Warteschlange, damit er '
      + 'sofort läuft und nicht erst nach der aktuellen Nummer. Viel Spaß damit.',
  },
  {
    datei: 'deine-stimme-ueberblick',
    titel: 'Überblick',
    text:
      'Kurzer Überblick für euch: ein neuer Treiber für die Grafikkarte, ein Sicherheits-Update für den '
      + 'Router und ein Blick auf das Wetter für die Nacht. Alles Weitere hört ihr in der Sendung.',
  },
  {
    datei: 'deine-stimme-ansage',
    titel: 'Ansage',
    text:
      'Kleine Erinnerung: Der Sender läuft rund um die Uhr, die Wünsche nimmt der Bot entgegen, und ich '
      + 'lese die Ansagen dazu vor. Bis gleich.',
  },
]

// ── Dienst fragen ───────────────────────────────────────────────────────────
async function sprich(text, zielWav) {
  const antwort = await fetch(`${DIENST}/tts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
    signal: AbortSignal.timeout(180_000),
  })
  if (!antwort.ok) throw new Error(`Sprechdienst antwortete HTTP ${antwort.status}`)
  const daten = Buffer.from(await antwort.arrayBuffer())
  if (daten.length < 4096) throw new Error(`Antwort zu klein (${daten.length} B) – kein WAV?`)
  writeFileSync(zielWav, daten)
  return daten.length
}

function messwert(datei, eintrag) {
  const wert = spawnSync(FFPROBE, ['-v', 'error', '-show_entries', eintrag, '-of', 'csv=p=0', datei], {
    encoding: 'utf8',
  })
  return (wert.stdout || '').trim()
}

async function main() {
  console.log(`Sprechdienst: ${DIENST}`)
  try {
    const zustand = await fetch(`${DIENST}/health`, { signal: AbortSignal.timeout(10_000) })
    console.log(`Dienst:       ${zustand.ok ? '✓ erreichbar' : `✗ HTTP ${zustand.status}`}`)
    if (!zustand.ok) return 1
  } catch (fehler) {
    console.error(`✗ Dienst nicht erreichbar: ${fehler.message}`)
    console.error('  Der Dienst läuft im Container 111 „rvc“ (sprechdienst.service, Port 10205).')
    return 1
  }

  if (!NUR_PRUEFEN) mkdirSync(ZIEL, { recursive: true })
  const arbeit = join(WURZEL, 'node_modules', '.cache')
  if (!NUR_PRUEFEN) mkdirSync(arbeit, { recursive: true })

  let gesamt = 0
  for (const probe of PROBEN) {
    const zielMp3 = join(ZIEL, `${probe.datei}.mp3`)
    if (NUR_PRUEFEN) {
      if (!existsSync(zielMp3)) {
        console.log(`✗ ${probe.datei}.mp3 fehlt`)
        return 1
      }
      const groesse = statSync(zielMp3).size
      gesamt += groesse
      console.log(`✓ ${probe.datei}.mp3  ${messwert(zielMp3, 'format=duration').slice(0, 5)} s  `
        + `${Math.round(groesse / 1024)} KB`)
      continue
    }

    const roh = join(arbeit, `deine-stimme-${probe.datei}.wav`)
    process.stdout.write(`… ${probe.titel} sprechen … `)
    await sprich(probe.text, roh)

    const fehler = spawnSync(FFMPEG, [
      '-y', '-v', 'error',
      '-i', roh,
      '-af', 'loudnorm=I=-16:TP=-1.5:LRA=11',
      '-ac', '1', '-ar', '22050',
      '-c:a', 'libmp3lame', '-b:a', '80k', '-write_id3v2', '1',
      '-metadata', `title=DEINE-STIMME – ${probe.titel} (Hörprobe)`,
      '-metadata', 'artist=Deadline Beats',
      '-metadata', 'album=KI-Radio-Moderator-Bot',
      '-metadata', 'comment=KI-Stimme, RVC-Modell <dein-modell>',
      zielMp3,
    ], { encoding: 'utf8' })
    rmSync(roh, { force: true })
    if (fehler.status !== 0) {
      console.error(`\n✗ ffmpeg scheiterte:\n${fehler.stderr}`)
      return 1
    }

    // ID3-Kopf mitgerechnet ist die Datei etwas größer als der Ton.
    const groesse = statSync(zielMp3).size
    gesamt += groesse
    const dauer = messwert(zielMp3, 'format=duration').slice(0, 5)
    console.log(`✓ ${dauer} s  ${Math.round(groesse / 1024)} KB  → ${probe.datei}.mp3`)
  }

  console.log(`\n${NUR_PRUEFEN ? 'Bestand' : 'Erzeugt'}: ${PROBEN.length} Proben, `
    + `${Math.round(gesamt / 1024)} KB in ${ZIEL.replace(WURZEL + '/', '')}`)
  if (!NUR_PRUEFEN) {
    console.log('Zum Prüfen anhören: ffplay <datei> — und danach `npm run type-check`.')
    console.log('Texte und Anzeigenamen stehen auch in src/data/radio/hoerproben.ts.')
  }
  return 0
}

process.exit(await main())
