#!/usr/bin/env node
/**
 * Generates voice samples of the own moderation voice "YOUR-VOICE".
 *
 * Call:
 *   node tools/stimmproben.mjs              # speak all samples anew
 *   EIGENE_STIMME=http://192.168.178.116:10205 node tools/stimmproben.mjs
 *   node tools/stimmproben.mjs --check      # only measure, write nothing
 *
 * The speech service (`sprechdienst`, LXC 111, port 10205) converts edge-tts
 * (`de-DE-AmalaNeural`, +40 %) via RVC to the model `<your-model>` — the same chain
 * as in the station. The sentences here are **spoken especially for the site**;
 * the raw material and the model are not published (see document
 * `VOICE.md`, section 14).
 *
 * Result: `public/radio/downloads/deine-stimme/<file>.mp3` — 22 050 Hz mono,
 * brought to −16 LUFS (the same level for all samples), ~80 kbit/s.
 * The files **must be committed** (the server does not speak by itself).
 *
 * Tool ffmpeg: `$FFMPEG`, otherwise ~/Applications/ffmpeg-7.0.2-amd64-static/ffmpeg,
 * otherwise `ffmpeg` from the PATH (as in tools/optimize-assets.mjs).
 */
import { spawnSync } from 'node:child_process'
import { existsSync, mkdirSync, rmSync, statSync, writeFileSync } from 'node:fs'
import { homedir } from 'node:os'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const HIER = dirname(fileURLToPath(import.meta.url))
const WURZEL = join(HIER, '..')
const ZIEL = join(WURZEL, 'public', 'radio', 'downloads', 'deine-stimme')
const SERVICE = process.env.EIGENE_STIMME || 'http://192.168.178.116:10205'
const NUR_PRUEFEN = process.argv.includes('--check')

// ── Tool: ffmpeg / ffprobe ──────────────────────────────────────────────
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

// ── The sentences (change here → follow up in src/data/radio/hoerproben.ts) ──
const PROBEN = [
  {
    file: 'deine-stimme-begruessung',
    title: 'Greeting',
    text:
      'Welcome to Deadline Beats. This is YOUR-VOICE speaking. It’s getting late, the server is running warm and '
      + 'the queue is empty – so we make ourselves comfortable and listen to music from our own archive.',
  },
  {
    file: 'deine-stimme-wunsch',
    title: 'Request announcement',
    text:
      'The request is on its way: I’m pushing the title directly into the interruption queue, so it '
      + 'starts immediately and not only after the current show. Enjoy it.',
  },
  {
    file: 'deine-stimme-ueberblick',
    title: 'Overview',
    text:
      'Brief overview for you: a new driver for the graphics card, a security update for the '
      + 'router and a look at the weather for the night. Everything else you’ll hear in the show.',
  },
  {
    file: 'deine-stimme-ansage',
    title: 'Announcement',
    text:
      'Small reminder: The broadcaster runs around the clock, the wishes are accepted by the bot, and I '
      + 'read the announcements for them. Until next time.',
  },
]

// ── Ask the service ─────────────────────────────────────────────────────────
async function say(text, zielWav) {
  const answer = await fetch(`${SERVICE}/tts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
    signal: AbortSignal.timeout(180_000),
  })
  if (!answer.ok) throw new Error(`Speech service answered HTTP ${answer.status}`)
  const data = Buffer.from(await answer.arrayBuffer())
  if (data.length < 4096) throw new Error(`Answer too small (${data.length} B) – no WAV?`)
  writeFileSync(zielWav, data)
  return data.length
}

function messwert(file, entry) {
  const wert = spawnSync(FFPROBE, ['-v', 'error', '-show_entries', entry, '-of', 'csv=p=0', file], {
    encoding: 'utf8',
  })
  return (wert.stdout || '').trim()
}

async function main() {
  console.log(`Speech service: ${SERVICE}`)
  try {
    const state = await fetch(`${SERVICE}/health`, { signal: AbortSignal.timeout(10_000) })
    console.log(`Service:        ${state.ok ? '✓ reachable' : `✗ HTTP ${state.status}`}`)
    if (!state.ok) return 1
  } catch (error) {
    console.error(`✗ Service not reachable: ${error.message}`)
    console.error('  The service runs in container 111 "rvc" (sprechdienst.service, port 10205).')
    return 1
  }

  if (!NUR_PRUEFEN) mkdirSync(ZIEL, { recursive: true })
  const arbeit = join(WURZEL, 'node_modules', '.cache')
  if (!NUR_PRUEFEN) mkdirSync(arbeit, { recursive: true })

  let total = 0
  for (const probe of PROBEN) {
    const zielMp3 = join(ZIEL, `${probe.file}.mp3`)
    if (NUR_PRUEFEN) {
      if (!existsSync(zielMp3)) {
        console.log(`✗ ${probe.file}.mp3 missing`)
        return 1
      }
      const groesse = statSync(zielMp3).size
      total += groesse
      console.log(`✓ ${probe.file}.mp3  ${messwert(zielMp3, 'format=duration').slice(0, 5)} s  `
        + `${Math.round(groesse / 1024)} KB`)
      continue
    }

    const raw = join(arbeit, `deine-stimme-${probe.file}.wav`)
    process.stdout.write(`… speaking ${probe.title} … `)
    await say(probe.text, raw)

    const error = spawnSync(FFMPEG, [
      '-y', '-v', 'error',
      '-i', raw,
      '-af', 'loudnorm=I=-16:TP=-1.5:LRA=11',
      '-ac', '1', '-ar', '22050',
      '-c:a', 'libmp3lame', '-b:a', '80k', '-write_id3v2', '1',
      '-metadata', `title=YOUR-VOICE – ${probe.title} (sample)`,
      '-metadata', 'artist=Deadline Beats',
      '-metadata', 'album=AI-Radio-Moderator-Bot',
      '-metadata', 'comment=AI voice, RVC model <your-model>',
      zielMp3,
    ], { encoding: 'utf8' })
    rmSync(raw, { force: true })
    if (error.status !== 0) {
      console.error(`\n✗ ffmpeg failed:\n${error.stderr}`)
      return 1
    }

    // The ID3 header is included in the file size, making the file slightly larger than the audio content.
    const groesse = statSync(zielMp3).size
    total += groesse
    const duration = messwert(zielMp3, 'format=duration').slice(0, 5)
    console.log(`✓ ${duration} s  ${Math.round(groesse / 1024)} KB  → ${probe.file}.mp3`)
  }

  console.log(`\n${NUR_PRUEFEN ? 'Existing' : 'Created'}: ${PROBEN.length} samples, `
    + `${Math.round(total / 1024)} KB in ${ZIEL.replace(WURZEL + '/', '')}`)
  if (!NUR_PRUEFEN) {
    console.log('Verify by listening: ffplay <file> — and then `npm run type-check`.')
    console.log('Texts and display names are also kept in src/data/radio/hoerproben.ts.')
  }
  return 0
}

process.exit(await main())
