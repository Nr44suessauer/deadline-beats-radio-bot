# Music archive cleaned up (2026-09-20)

Clean-up of the AzuraCast archive on the data server (LXC 106, station
"Deadline Beats", 56,635 titles on `/mnt/Content/Music`).

## Results in numbers

| What | before | after |
|---|---|---|
| titles in the library | 56,635 | 56,635 (unchanged) |
| live/bootleg titles in the main collection | 7,906 | 0 (they are in `_Archiv/Live/`) |
| folders directly under `Music/` | 133 | 126 |
| files in `unsorted/` | 9,791 | 0 (folder removed) |
| titles with track number in the title | 1,088 | 625 (441 cleaned automatically) |
| titles with a numeric artist ("01") | 344 | 0 |
| artists with "feat." | 1,628 | 1 |
| titles in the bot catalog | 56,635 | 48,729 |
| playlist assignments | 168 | 168 (unchanged) |

## What was done

1. **Live/bootleg archive separated.** 42 pure live/bootleg collection folders
   (e.g. `Nirvana …/Other/Concerts`, `…/Live`, `…/03 - Live & Bootleg`) now lie
   under **`_Archiv/Live/<old structure>`**. Official live albums
   ("KISS – Alive II") deliberately stay in the main collection.
2. **Duplicate artist folders merged.** The `<artist> - Discography …`
   folders (21 from `unsorted/` as well as `Led.Zeppelin.1969-2018`,
   `HammerFall - Diskografie …`, `Good Charlotte - Discography …`) now lie
   as **`<artist>/Diskografie/`** next to the artist. `unsorted/` is thereby empty.
3. **Tags cleaned** (database only, no files were touched):
   - 441 titles without a leading track number ("01 - My Crown" → "My Crown")
   - 344 artists that were only a number, emptied
   - 1,635 "feat." artists separated: artist = main artist,
     title gets `(feat. …)` appended
4. **The bot suggests nothing from the archive.** In the n8n tool
   "Tool - Search title" (node `Prepare hits`) and in the catalog service
   (module `catalog.py`) paths containing `_Archiv/` and `moderation/`
   are skipped.

## Important lesson: move folders only through the interface

AzuraCast matches media **by path** (`App\Sync\Task\CheckMediaTask`:
`md5($path)`; if the path is missing, the record is deleted and created anew).
Moving on the disk therefore costs the media identifier, `unique_id`,
playlist assignments and custom fields.

The right way is the batch action:

```
PUT /api/station/1/files/batch
{"do":"move","currentDirectory":"<alt>","directory":"<neu>","dirs":[...],"files":[...]}
```

It rewrites the path in the database — everything is preserved.
For files: `newPath = directory + "/" + basename(old)`, for folders the
prefix `currentDirectory` is replaced by `directory`. Non-media files
(readme, promo URLs) are unknown to AzuraCast and have to be taken along on the
disk with `mv`.

Equally important: `song_id` and `text` are computed from artist/album/title
(`App\Entity\Traits\HasSongFields::updateMetaFields`,
`Song::getSongHash`). Anyone who changes titles in the database has to recompute
both — `05-tags-korrigieren.php` does exactly that.

## Deliberately NOT done

- **Genre not rewritten.** The 288 spellings ("Rock | Hard Rock | …")
  look untidy, but the catalog service catches this itself: for mood requests it
  discards titles with more than four genre words and computes a "purity".
  Rewriting 56,000 genres would have meant a lot of risk for little gain.
- **Missing artists (556) not guessed.** Deriving one from the path
  would be wrong in many cases (e.g. Marilyn Manson lies under
  `The Prodigy/Diskografie/Keith Flint (The Prodigy)/! Keith Flint Related/…`).
  A wrong artist harms the artist search more than an empty one.
- **Tags not written into the files.** The catalog service and the bot
  read through the AzuraCast interface, not from the files. The
  database corrections take effect immediately. (If a file is read in again
  later, its file tags apply again.)
- **Track numbers separated by a plain space** ("01 Bury Me a G") were left alone:
  indistinguishable from real titles ("10 Light Years Away",
  "48 Hours", "99 Luftballons").

## Tools (runnable in this order)

| Script | Task |
|---|---|
| `01-sicherung.sh` | database dump + path/assignment lists to `/root/azuracast-aufraeumen-<stamp>/` |
| `02-live-kandidaten.sh` | determines pure live/bootleg collection folders |
| `03-live-verschieben.sh [echt]` | moves them to `_Archiv/Live/` (dry run without `echt`) |
| `04-dubletten-zusammenlegen.sh [echt]` | puts discography folders next to the artist (`<artist>/Diskografie/`) |
| `05-tags-korrigieren.php` | tag corrections in the container (`DRY=1 php …` for a dry run) |
| `06-bot-filter.py` | inserts the archive filter into an n8n workflow |
| `07-bot-filter-einspielen.sh <datei> <ablauf>` | imports the patched workflow into n8n |
| `08-katalog-einspielen.sh` | rebuilds the catalog service and creates the catalog |
| `09-suchknoten-test.sh` | checks the search node with real data (without n8n) |

The backup lies on the data server under
`/root/azuracast-aufraeumen-20260920-103645/` (database dump 11 MB compressed,
`medien-id-pfad.tsv`, `playlist-zuordnungen.tsv`, `live-verschieben.tsv`,
`dubletten-zusammenlegen.tsv`).

Way back: moves can be undone with the same script
(swap `currentDirectory`/`directory`), tag changes via the
database dump.
