# Website bridge — generating the radio docs

These two tools lived in the website project under `tools/` until 2026-09-24;
they generate the **Bot Radio** tab (`/radio`) there. In content they belong to the
bot and therefore now live here — as an **unchanged copy** of that state (the
website project no longer keeps them).

| File | Task |
| --- | --- |
| `build-radio-docs.mjs` | reads `DocOfficial/` (the release edition) and generates `src/data/radio/**` and `public/radio/**`: Markdown → HTML, Mermaid repair, media via ffmpeg, n8n templates incl. ZIP; at the end it checks against the real access values of the working folder. |
| `stimmproben.mjs` | generates the four voice samples via the speech service (`sprechdienst`, LXC 111, port 10205, environment variable `EIGENE_STIMME`), normalises them to −16 LUFS and stores the MP3s under `public/radio/downloads/deine-stimme/`. |

**To run them, both must be copied to `DeadlineDrivenWebsite/tools/`** — they derive
the project folder (the output target) from their own path (`import.meta.url`).

```sh
cd <projektordner>/DeadlineDrivenWebsite
cp ../Ai_Radio_Moderator_Bot/tools/website-bruecke/*.mjs tools/
node tools/build-radio-docs.mjs --check   # only the secret cross-check
node tools/build-radio-docs.mjs           # regenerate content + media
node tools/stimmproben.mjs --check        # only measure the samples
```

Notes on the source, targets and publication: `README.md` in the website project,
section "Radio-Dokumentation".
