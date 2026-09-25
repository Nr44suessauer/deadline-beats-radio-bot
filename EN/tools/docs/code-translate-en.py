#!/usr/bin/env python3
"""Translates the German texts in the code into English (branch `en`).

**Only** comments, documentation blocks and German texts
inside strings are translated. Code, identifiers, paths and keys stay
untouched — this is checked after every write:

  1. Syntax:  `py_compile` (.py), `bash -n` (.sh), `node --check` (.js)
  2. Skeleton: the token sequence of the code (comments away, texts as «S»)
              must be identical before and after
  3. Placeholders: `{…}`, `%s`, `\\n`, `$VAR` in texts must be preserved

Output is written to `EN/<path>` — the same place as for the
translated documents. A cache (`uebersetzungen-code-en.json`)
prevents duplicate requests; the language model runs locally (Ollama).

Call:
  python3 tools/code-translate-en.py --all            # all files
  python3 tools/code-translate-en.py <file> [file …]
  python3 tools/code-translate-en.py --all --check  # check only
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tokenize
import urllib.request
from io import StringIO
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent.parent.parent
ADRESS = "http://192.168.178.187:11434"
MODELL = "qwen3-coder:30b"
SPEICHER = PROJEKT / "werkzeuge" / "doku" / "uebersetzungen-code-en.json"
# Literal replacements for interface tokens (switches, paths, environment names):
# they sometimes stand bare in scripts (without quotes) and are
# therefore applied to every generated file at the end.
ROHTAUSCH_DATEI = PROJEKT / "werkzeuge" / "doku" / "rohtausch.json"
ENDUNGEN = (".py", ".sh", ".js", ".service", ".vorlage", ".yml")
UEBERSPRINGEN = {"EN", "DocOfficial", ".git", "__pycache__", "node_modules", "ANHANG"}

# Words by which German text is recognized
DEUTSCH = re.compile(
    r"[äöüßÄÖÜ]|\b(the|die|das|und|not|is|are|are|result|war|eine|einen|einem|dem|den|für|über|out|mit|bei|"
    r"after|when|then|still|only|also|but|or|must|may|can|expected|läuft|liegt|applies|kommt|goes|is's|file|files|"
    r"value|Values|Werten|Name|names|count|error|path|paths|Service|Dienste|Titel|Titelwunsch|Stunde|hours|Minute|minutes|"
    r"Command|Commands|area|source|sources|Sender|Sendung|voice|Stimmen|message|news|Schlüssel|password|"
    r"Anzeige|Answer|question|Fragen|Search|suchen|play|play|wünscht|Wish|Wünsche|Moderation|Announcement|Announcements|News|"
    r"News|check|check|Prüflauf|setting|settings|playlist|Playlists|Titelnummer|line|lines|"
    r"section|sections|example|examples|Original|Betreiber|chapter|Anleitung|Hinweis|Hinweise|result|results|"
    r"table|column|columns|folder|Filename|Umgebung|Access|Zugangsdaten|Identifier|Kanal|Format|Grösse|Größe|Länge|duration)\b"
)
TRENNER = "@@@"
STAPEL = 15          # Fragments per request to the language model (keep it small:
                     # large batches can blow the time limit)
# Fragments that are not translated: paths, addresses, commands, placeholders
# (Addresses and paths only if the fragment is NOTHING else — otherwise
# the text next to them, e.g. in `// comment` lines, would be lost)
NICHT_UEBERSETZEN = re.compile(r"^\S*://\S*$|^\s*[/~.$]\S*$|^\s*[A-Za-z0-9_.-]+$|^\s*(sudo|curl|ssh|bash|python3?|docker|pct|systemctl|git|nano)\b")

# Command lines in documentation texts: “python3 x.py …   description” — the
# description part is text and gets translated, the command itself not.
BEFEHL_TEXT = re.compile(
    r"^\s*(?:[A-Z][A-Z0-9_]*=\S+\s+)*"
    r"(python3?|docker|pct|systemctl|curl|bash|sh|git|nano)\b")


def befehlsrest(zeile: str) -> tuple[int, int] | None:
    """Position of the description behind a command line (otherwise None)."""
    if not BEFEHL_TEXT.match(zeile):
        return None
    hits = list(re.finditer(r"\s{2,}", zeile))
    if not hits:
        return None
    from_ = hits[-1].end()
    rest = zeile[from_:]
    if not rest.strip() or DEUTSCH.search(rest) is None:
        return None
    return from_, len(zeile)


def dreifach(zeile: str) -> int | None:
    """Index of the three quotation marks that delimit a text block.

    Occurrences inside strings (three characters as text) and in comments
    do not count — otherwise code lines would flip the block state.
    Mid-line block starts (assignment plus the three characters),
    however, count as delimiters.
    """
    pos = zeile.find('"""')
    while pos != -1:
        if pos > 0 and zeile[pos - 1] in "\"'":
            pass                                  # stands inside a string
        else:
            km = kommentar_position(zeile)
            if km is None or pos < km:
                return pos
        pos = zeile.find('"""', pos + 3)
    return None


# ── Language model ──────────────────────────────────────────────────────────
def schuetzen(text: str) -> tuple[str, list[str]]:
    """Replaces placeholders with substitute digits the model does not touch."""
    werte: list[str] = []

    def ersatz(m: re.Match[str]) -> str:
        werte.append(m.group(0))
        return f"«{len(werte) - 1}»"

    return PLATZHALTER.sub(ersatz, text), werte


def freigeben(text: str, werte: list[str]) -> str:
    for i, wert in enumerate(werte):
        text = text.replace(f"«{i}»", wert)
    return text


def uebersetze_stuecke(stuecke: list[str], kontext: str) -> list[str]:
    """Translates a list of text fragments (same order, same count).

    The language model receives the fragments separated by `@@@` and must return
    them exactly the same way. Every answer is checked: no numbering, no
    line breaks (the fragments are line snippets), the count must match.
    """
    if not stuecke:
        return []
    geschuetzt: list[str] = []
    werte_liste: list[list[str]] = []
    for stueck in stuecke:
        geschuetztes, werte = schuetzen(stueck)
        geschuetzt.append(geschuetztes)
        werte_liste.append(werte)
    job = (
        "Translate the following German text fragments of a software project into English.\n"
        "Rules:\n"
        f"- The fragments are separated by a line containing only {TRENNER}.\n"
        f"- Answer with the {len(stuecke)} translated fragments in the same order, also "
        f"separated by a line containing only {TRENNER}. Nothing else — no numbering, no "
        "comments, no explanations.\n"
        "- Keep the meaning; do not shorten. Keep code identifiers, paths, URLs, options "
        "and placeholders ({…}, %s, $VAR, \\n, \\t) exactly as they are.\n"
        "- If a fragment is already English, return it unchanged.\n"
        f"- Context: {kontext}\n\n"
    )
    job += f"\n{TRENNER}\n".join(geschuetzt)
    data = json.dumps({"model": MODELL, "prompt": job, "stream": False,
                        "options": {"temperature": 0.1}}).encode()
    request = urllib.request.Request(f"{ADRESS}/api/generate", data=data,
                                    headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=300) as answer:
        text = json.loads(answer.read().decode()).get("response", "")

    teile = [t.strip() for t in text.split(TRENNER)]
    # Some models still number: remove leading "[3]" etc.
    teile = [re.sub(r"^\[\d+\]\s*", "", t) for t in teile]
    if len(stuecke) == 1:
        # One fragment: no separation needed (the model likes to add it).
        # Multi-line answers are decoration — the fragments are always
        # line snippets: discard separators, echoes and announcements.
        zeilen_antwort = [z.strip() for z in text.splitlines()
                          if z.strip() and z.strip() != TRENNER]
        zeilen_antwort = [z for z in zeilen_antwort if z != stuecke[0].strip()]
        if len(zeilen_antwort) > 1 and zeilen_antwort[0].endswith(":"):
            zeilen_antwort = zeilen_antwort[1:]
        teile = [zeilen_antwort[0] if zeilen_antwort else ""]
    if len(teile) != len(stuecke):
        raise RuntimeError(f"Answer splits into {len(teile)} instead of {len(stuecke)} parts")
    teile = [freigeben(t, w) for t, w in zip(teile, werte_liste)]
    for alt, new in zip(stuecke, teile):
        if not new:
            raise RuntimeError(f"empty translation for {alt[:40]!r}")
        if "\n" in new:
            raise RuntimeError(f"translation with line break: {new[:60]!r}")
    return teile


NICHT_UEBERSETZT: list[str] = []


def uebersetze_einzeln(stuecke: list[str], kontext: str) -> list[str]:
    """Fallback: translate each fragment on its own (when the batch answer falls apart).

    If a fragment stays stubborn (timeout, empty answer), it is
    taken over UNCHANGED and remembered — better than a full abort; the
    list appears at the end of the report and is done by hand.
    """
    result: list[str] = []
    for stueck in stuecke:
        try:
            result += uebersetze_stuecke([stueck], kontext)
        except Exception:                               # noqa: BLE001
            result.append(stueck)
            NICHT_UEBERSETZT.append(stueck)
    return result


def speicher() -> dict[str, str]:
    if SPEICHER.exists():
        return json.loads(SPEICHER.read_text(encoding="utf-8"))
    return {}


def rohtausch() -> list[tuple[re.Pattern[str], str]]:
    """Literal replacements with word boundaries (identifier-safe).

    `CATALOG_URL` becomes `CATALOG_URL`, but `DRYRUN` is not
    touched by `DRY` — the boundaries depend on whether the word
    begins/ends with a word character.
    """
    raw: dict[str, str] = {}
    if ROHTAUSCH_DATEI.exists():
        raw = json.loads(ROHTAUSCH_DATEI.read_text(encoding="utf-8"))
    muster: list[tuple[re.Pattern[str], str]] = []
    for alt, wert in raw.items():
        left = r"(?<![A-Za-z0-9_])" if re.match(r"\w", alt) else ""
        right = r"(?![A-Za-z0-9_])" if re.search(r"\w$", alt) else ""
        muster.append((re.compile(left + re.escape(alt) + right), wert))
    return muster


def cache_schluessel(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:24]


def uebersetzung(stueck: str, speicher_datei: dict[str, str]) -> str:
    """Translation for a fragment: full text, otherwise the single word without edge spaces."""
    u = speicher_datei.get(cache_schluessel(stueck))
    if u is not None:
        return u
    core = stueck.strip()
    if core != stueck:
        u = speicher_datei.get(cache_schluessel(core))
        if u is not None:
            vorn = stueck[:len(stueck) - len(stueck.lstrip())]
            hinten = stueck[len(stueck.rstrip()):]
            return vorn + u + hinten
    return stueck


# ── Splitting and assembling ────────────────────────────────────────────
def ist_deutsche_datei(text: str) -> bool:
    """Rough detection: does the file contain German text at all?"""
    if re.search(r"[äöüßÄÖÜ]", text):
        return True
    return len(DEUTSCH.findall(text)) >= 3


def stelle_stuecke(lines: list[str], endung: str,
                   speicher_datei: dict[str, str] | None = None
                   ) -> list[tuple[int, int, int, str]]:
    """Where is translatable text? Returns: (line number, from, to, quote).

    `from_`/`to` are character positions within the line (to = exclusive);
    `Anführung` is `"` or `'` when the fragment sits in a string
    (no same quotes may come in there), otherwise "".
    """
    stellen: list[tuple[int, int, int, str]] = []

    def passt(text: str) -> bool:
        # Without letters there is nothing to translate (‘‘, $2, 2026-09-22 …) —
        # such snippets are code or number material and stay untouched.
        core = text.strip()
        if not core or re.search(r"[A-Za-z]", core) is None:
            return False
        # single words (without spaces/period) count as text only
        # when a translation is stored in the cache — that way
        # code identifiers stay protected, while words such as “play” or
        # “--dry-run” become translatable.
        if re.fullmatch(r"[A-Za-z0-9_.\-äöüßÄÖÜ]+", core):
            return (speicher_datei is not None
                    and cache_schluessel(core) in speicher_datei)
        return not NICHT_UEBERSETZEN.search(text)

    def nimm_doku(nr: int, zeile: str, from_: int, to: int) -> None:
        if passt(zeile[from_:to]):
            stellen.append((nr, from_, to, ""))
            return
        rest = befehlsrest(zeile)
        if rest is not None:
            stellen.append((nr, rest[0], rest[1], ""))
    im_text = False          # inside a text block
    for nr, zeile in enumerate(lines):
        streifen = zeile.strip()
        if endung == ".py":
            if im_text:
                ende = dreifach(zeile)
                if ende is None:
                    nimm_doku(nr, zeile, 0, len(zeile))
                    continue
                nimm_doku(nr, zeile, 0, ende)
                im_text = False
                continue
            start = dreifach(zeile)
            if start is not None:
                rest = zeile[start + 3:]
                if '"""' in rest:                      # single-line text
                    nimm_doku(nr, zeile, start + 3, start + 3 + rest.rfind('"""'))
                else:
                    im_text = True
                    nimm_doku(nr, zeile, start + 3, len(zeile))
                continue
        if streifen.startswith("#"):
            marke = zeile.index("#") + 1
            if passt(zeile[marke:]):
                stellen.append((nr, marke, len(zeile), ""))
            continue
        # Comment at the end of the line (not inside quotes)
        position = kommentar_position(zeile)
        if position is not None and passt(zeile[position + 1:]):
            stellen.append((nr, position + 1, len(zeile), ""))
        # String in the line (display texts)
        for from_, to, anfuehrung in zeichenketten(zeile):
            if position is not None and from_ > position:      # is inside the comment
                continue
            if passt(zeile[from_:to]):
                stellen.append((nr, from_, to, anfuehrung))
    return stellen


def zeichenketten(zeile: str) -> list[tuple[int, int, str]]:
    """All complete strings of a line: (from, to, quote).

    Walks character by character so quotes are paired correctly
    (a pattern would be off on lines with several strings).
    """
    stellen: list[tuple[int, int, str]] = []
    i = 0
    while i < len(zeile):
        z = zeile[i]
        if z in "\"'":
            j = i + 1
            while j < len(zeile):
                if zeile[j] == "\\":
                    j += 2
                    continue
                if zeile[j] == z:
                    break
                j += 1
            if j < len(zeile):
                stellen.append((i + 1, j, z))
                i = j + 1
                continue
        i += 1
    return stellen


def kommentar_position(zeile: str) -> int | None:
    """Index of the `#` that starts a comment (not inside quotes)."""
    in_einfach = in_doppelt = False
    for i, z in enumerate(zeile):
        if z == "'" and not in_doppelt:
            in_einfach = not in_einfach
        elif z == '"' and not in_einfach:
            in_doppelt = not in_doppelt
        elif z == "#" and not in_einfach and not in_doppelt:
            return i
    return None


def typografisch(text: str, anfuehrung: str, ist_bytes: bool = False) -> str:
    """Convert straight quotes — skip placeholders like {k['name']}.

    The delimiter of the position is ALWAYS converted: an apostrophe in
    "What's" would otherwise break the string. Other straight characters only
    in flowing text (with spaces) — in code pieces like b'name="' the
    conversion would be wrong.
    """
    fliess = not ist_bytes and (anfuehrung == "" or " " in text)

    def wandle(teil: str) -> str:
        if anfuehrung in ("'", ""):
            teil = re.sub(r"(?<!\\)'([^']*)'", "\u2018\\1\u2019", teil)
            teil = re.sub(r"(?<!\\)'", "\u2019", teil)
        if anfuehrung in ('"', ""):
            teil = re.sub(r"(?<!\\)\"([^\"]*)\"", "\u201c\\1\u201d", teil)
            teil = re.sub(r'(?<!\\)"', "\u201c", teil)
        if fliess and anfuehrung == '"':
            teil = re.sub(r"(?<!\\)'([^']*)'", "\u2018\\1\u2019", teil)
            teil = re.sub(r"(?<!\\)'", "\u2019", teil)
        return teil

    teile = []
    last = 0
    for m in PLATZHALTER.finditer(text):
        teile.append(wandle(text[last:m.start()]))
        teile.append(m.group(0))
        last = m.end()
    teile.append(wandle(text[last:]))
    return "".join(teile)


def setze_zusammen(lines: list[str], stellen: list[tuple[int, int, int, str]],
                   uebersetzt: list[str], endung: str = "") -> list[str]:
    # IMPORTANT: replace RIGHT to LEFT per line — otherwise the positions
    # of the other spots in the same line shift as soon as a
    # translation is longer or shorter than the original.
    new = list(lines)
    nach_zeile: dict[int, list[tuple[int, int, str, str]]] = {}
    for (nr, from_, to, anfuehrung), ersatz in zip(stellen, uebersetzt):
        nach_zeile.setdefault(nr, []).append((from_, to, anfuehrung, ersatz))
    for nr, list in nach_zeile.items():
        zeile = new[nr]
        for from_, to, anfuehrung, ersatz in sorted(list, key=lambda s: s[0], reverse=True):
            alt = zeile[from_:to]
            # Keep the leading space (the comment marker separates otherwise)
            if alt.startswith(" ") and not ersatz.startswith(" "):
                ersatz = " " + ersatz
            # Straight quotes of the translation into typographic
            # convert (details in `typografisch`): straight characters can
            # break strings — an apostrophe in "What's new" terminates
            # e.g. a plain shell section. If the fragment was
            # taken over unchanged, it stays as it is — it then comes
            # one to one from the checked source. In Python documentation lines
            # (text blocks, no quote context) do NOT convert:
            # expressions like {tabelle([("…", "…")])} often stand there, whose
            # straight characters are CODE.
            if (ersatz.strip() and ersatz.strip() != alt.strip()
                    and not (endung == ".py" and anfuehrung == "")):
                ist_bytes = (from_ > 0 and zeile[from_ - 1] in "bB"
                             and (from_ < 2 or not zeile[from_ - 2].isalnum()))
                ersatz = typografisch(ersatz, anfuehrung, ist_bytes)
            zeile = zeile[:from_] + ersatz + zeile[to:]
        new[nr] = zeile
    return new


# ── Checks ─────────────────────────────────────────────────────────────────
# Command switches (--once, --dry-run …) ARE deliberately translated
# (--once, --dry-run) — they are not placeholders and therefore no longer
# appear in the pattern list. All other placeholders stay protected.
PLATZHALTER = re.compile(r"\{[^}]*\}|%[sdf%]|\$[A-Za-z_][A-Za-z0-9_]*|\\[nt]")


def platzhalter(text: str) -> list[str]:
    # Expressions in curly braces with double quotation marks
    # (templates like {bild_html("…", "…")}) are NOT compared — there the
    # the inner text may be translated. Likewise expressions WITH spaces
    # (such as `{ /* comment */ }` in JavaScript snippets): there is text,
    # not a placeholder.
    return sorted(p for p in PLATZHALTER.findall(text)
                  if not (p.startswith("{") and '"' in p)
                  and not (p.startswith("{") and " " in p))


TEXT_TOKENS = {tokenize.STRING}
FSTRING_MIDDLE = getattr(tokenize, "FSTRING_MIDDLE", None)
if FSTRING_MIDDLE is not None:
    # From Python 3.12, the texts in f-strings are separate tokens — without a mask
    # the skeleton check would take every translated f-string for code.
    TEXT_TOKENS.add(FSTRING_MIDDLE)


def geruest_python(source: str) -> str | None:
    """Token skeleton: comments removed, texts as «S» — code stays recognizable."""
    try:
        teile = []
        for tok in tokenize.generate_tokens(StringIO(source).readline):
            if tok.type == tokenize.COMMENT:
                continue
            if tok.type == FSTRING_MIDDLE:
                # Do NOT compare texts in f-strings: word order
                # shifts them when translating (German "… out {x} heraus",
                # English "… from {x}"). The {…} fields themselves are secured by the
                # placeholder check.
                continue
            if tok.type in TEXT_TOKENS:
                teile.append("«S»")
            else:
                teile.append(tok.string)
        return " ".join(teile)
    except tokenize.TokenError:
        return None


def _maskiere(zeile: str) -> str:
    """Replace strings in a line with S — character by character.

    Important: `'"'` (a quote mark as text) must not upset the count
    — hence ONE pass with a matching counterpart instead of two
    Ersetzungsläufe.
    """
    result = []
    i = 0
    while i < len(zeile):
        z = zeile[i]
        if z in "'\"":
            j = zeile.find(z, i + 1)
            if j != -1:
                result.append(z + "S" + z)
                i = j + 1
                continue
        result.append(z)
        i += 1
    return "".join(result)


def geruest_schlicht(source: str, endung: str) -> str:
    """For shell/JS: comment lines away, string contents replaced."""
    heiler = re.compile(r"#[^\n]*") if endung != ".js" else re.compile(r"//[^\n]*")
    teile = []
    for zeile in source.splitlines():
        # First mask the string contents, THEN remove comments:
        # otherwise the `#` in `${#VAR}` cuts into the text. Typographic
        # characters count as straight only AFTER masking — a ’ inside
        # a string must not disturb the masking, a ’ in free
        # text should match the ’… of the translation though.
        without = _maskiere(zeile)
        without = heiler.sub("#K" if endung != ".js" else "//K", without)
        without = (without.replace("\u2019", "'").replace("\u2018", "'")
                    .replace("\u201c", '"').replace("\u201d", '"'))
        teile.append(without.strip())
    return "\n".join(teile)


def syntax_okatei(path: Path) -> tuple[bool, str]:
    endung = path.suffix
    if endung == ".py":
        command = [sys.executable, "-m", "py_compile", str(path)]
    elif endung == ".sh":
        command = ["bash", "-n", str(path)]
    elif endung == ".js":
        command = ["node", "--check", str(path)]
    else:
        return True, ""
    result = subprocess.run(command, capture_output=True, text=True)
    return result.returncode == 0, (result.stderr or result.stdout).strip()[:300]


# ── Flow ───────────────────────────────────────────────────────────────────
def dateien(wurzel: Path) -> list[Path]:
    all: list[Path] = []
    for p in sorted(wurzel.rglob("*")):
        if not p.is_file() or p.suffix not in ENDUNGEN:
            continue
        rel = p.relative_to(wurzel)
        if any(teil in UEBERSPRINGEN for teil in rel.parts):
            continue
        if any(teil.startswith(".") for teil in rel.parts):
            continue
        all.append(p)
    return all


def uebersetze_datei(path: Path, speicher_datei: dict[str, str], nur_pruefen: bool,
                     ohne_modell: bool = False) -> str:
    rel = path.relative_to(PROJEKT)
    target = PROJEKT / "EN" / rel
    lines = path.read_text(encoding="utf-8").splitlines()
    if not ist_deutsche_datei("\n".join(lines)):
        return f"– {rel}: no German text"
    stellen = stelle_stuecke(lines, path.suffix, speicher_datei)
    if not stellen:
        return f"– {rel}: no German text"

    stuecke = [lines[nr][from_:to] for nr, from_, to, _ in stellen]
    missing = [s for s in stuecke
               if cache_schluessel(s) not in speicher_datei
               and cache_schluessel(s.strip()) not in speicher_datei]
    if missing and ohne_modell and not nur_pruefen:
        return f"◐ {rel}: {len(missing)} of {len(stellen)} spots still missing"
    if missing and not nur_pruefen:
        new: list[str] = []
        for beginning in range(0, len(missing), STAPEL):
            portion = missing[beginning:beginning + STAPEL]
            try:
                new += uebersetze_stuecke(portion, f"{rel}")
            except Exception:                           # noqa: BLE001
                try:
                    new += uebersetze_einzeln(portion, f"{rel}")
                except Exception as error:             # noqa: BLE001
                    return f"✗ {rel}: {error}"
        for alt, new in zip(missing, new):
            speicher_datei[cache_schluessel(alt)] = new

    uebersetzt = [uebersetzung(s, speicher_datei) for s in stuecke]

    # The cache may contain old, broken pieces: check and fetch anew.
    kaputt = [s for s, u in zip(stuecke, uebersetzt) if "\n" in u or not u.strip()]
    if kaputt and ohne_modell and not nur_pruefen:
        # Without model only discard — the spot stays German, that is safe.
        for alt in kaputt:
            speicher_datei.pop(cache_schluessel(alt), None)
        uebersetzt = [uebersetzung(s, speicher_datei) for s in stuecke]
    if kaputt and not nur_pruefen and not ohne_modell:
        for alt in kaputt:
            speicher_datei.pop(cache_schluessel(alt), None)
        new = []
        for beginning in range(0, len(kaputt), STAPEL):
            portion = kaputt[beginning:beginning + STAPEL]
            try:
                new += uebersetze_stuecke(portion, rel)
            except Exception:                           # noqa: BLE001
                new += uebersetze_einzeln(portion, rel)
        for alt, new in zip(kaputt, new):
            speicher_datei[cache_schluessel(alt)] = new
        uebersetzt = [uebersetzung(s, speicher_datei) for s in stuecke]

    # Placeholders must be preserved. Old cache entries may have
    # changed them → discard the entry and translate again (with protection).
    kaputt_p = [s for s, u in zip(stuecke, uebersetzt)
                if platzhalter(s) and platzhalter(s) != platzhalter(u)]
    if kaputt_p and ohne_modell and not nur_pruefen:
        for alt in kaputt_p:
            speicher_datei.pop(cache_schluessel(alt), None)
        uebersetzt = [uebersetzung(s, speicher_datei) for s in stuecke]
    if kaputt_p and not nur_pruefen and not ohne_modell:
        for alt in kaputt_p:
            speicher_datei.pop(cache_schluessel(alt), None)
        for beginning in range(0, len(kaputt_p), STAPEL):
            portion = kaputt_p[beginning:beginning + STAPEL]
            try:
                new = uebersetze_stuecke(portion, rel)
            except Exception:                           # noqa: BLE001
                try:
                    new = uebersetze_einzeln(portion, rel)
                except Exception as error:             # noqa: BLE001
                    target.unlink(missing_ok=True)
                    return f"✗ {rel}: {error}"
            for alt, new in zip(portion, new):
                speicher_datei[cache_schluessel(alt)] = new
        uebersetzt = [uebersetzung(s, speicher_datei) for s in stuecke]
    for alt, new in zip(stuecke, uebersetzt):
        if platzhalter(alt) and platzhalter(alt) != platzhalter(new):
            target.unlink(missing_ok=True)
            return f"✗ {rel}: placeholders changed in {alt[:40]!r}"

    def geruest_gleich(source: str, result: str) -> bool:
        if path.suffix == ".py":
            before, nachher = geruest_python(source), geruest_python(result)
            return before is not None and nachher is not None and before == nachher
        return geruest_schlicht(source, path.suffix) == geruest_schlicht(result, path.suffix)

    def platzhalter_gleich(uebersetzt_liste: list[str]) -> bool:
        for alt, new in zip(stuecke, uebersetzt_liste):
            if platzhalter(alt) and platzhalter(alt) != platzhalter(new):
                return False
        return True

    neu_zeilen = setze_zusammen(lines, stellen, uebersetzt, path.suffix)
    quelle_neu = "\n".join(neu_zeilen) + "\n"

    # Compare both sides WITH a trailing newline — otherwise
    # the NEWLINE token differs and every .py file fails.
    if (not geruest_gleich("\n".join(lines) + "\n", quelle_neu)
            and not nur_pruefen and not ohne_modell):
        # Old cache entries may have broken up the source text
        # (quotes, curly braces) → discard, translate once fresh
        # and check again.
        for alt in stuecke:
            speicher_datei.pop(cache_schluessel(alt), None)
        frische: list[str] = []
        try:
            for beginning in range(0, len(stuecke), STAPEL):
                frische += uebersetze_stuecke(stuecke[beginning:beginning + STAPEL], rel)
        except Exception:                               # noqa: BLE001
            try:
                frische = uebersetze_einzeln(stuecke, rel)
            except Exception as error:                 # noqa: BLE001
                target.unlink(missing_ok=True)
                return f"✗ {rel}: {error}"
        if len(frische) != len(stuecke) or not platzhalter_gleich(frische):
            target.unlink(missing_ok=True)
            return f"✗ {rel}: placeholders changed (fresh translation)"
        for alt, new in zip(stuecke, frische):
            speicher_datei[cache_schluessel(alt)] = new
        uebersetzt = frische
        neu_zeilen = setze_zusammen(lines, stellen, uebersetzt, path.suffix)
        quelle_neu = "\n".join(neu_zeilen) + "\n"

    if not geruest_gleich("\n".join(lines) + "\n", quelle_neu):
        target.unlink(missing_ok=True)
        return f"✗ {rel}: code skeleton has changed"

    if nur_pruefen:
        return f"· {rel}: {len(stellen)} spots (check run)"

    target.parent.mkdir(parents=True, exist_ok=True)
    endtext = quelle_neu
    for muster, wert in rohtausch():
        endtext = muster.sub(lambda _m: wert, endtext)
    target.write_text(endtext, encoding="utf-8")
    ok, news = syntax_okatei(target)
    if not ok:
        target.unlink()
        return f"✗ {rel}: syntax error after translating — {news}"
    return f"✓ {rel}: {len(stellen)} spots translated"


def main() -> int:
    parser = argparse.ArgumentParser(description="Translate German code texts into English")
    parser.add_argument("dateien", nargs="*", type=Path)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--without-model", action="store_true",
                          help="Translate only from the cache, no model call")
    args = parser.parse_args()

    targets = dateien(PROJEKT) if args.all else [p.resolve() for p in args.dateien]
    targets.sort(key=lambda p: p.stat().st_size)   # small ones first
    if not targets:
        print(__doc__)
        return 2

    speicher_datei = speicher()
    good = bad = open = 0
    for p in targets:
        result = uebersetze_datei(p, speicher_datei, args.check, args.ohne_modell)
        print(result, flush=True)
        if result.startswith("✗"):
            bad += 1
        elif result.startswith("◐"):
            open += 1
        else:
            good += 1
        if not args.check:
            SPEICHER.write_text(json.dumps(speicher_datei, ensure_ascii=False, indent=1),
                                encoding="utf-8")
    print(f"\n{good} in order, {bad} with errors, {open} open ·"
          f"cache: {len(speicher_datei)} pieces")
    if NICHT_UEBERSETZT:
        print(f"\n{len(NICHT_UEBERSETZT)} spots stayed unchanged (model delivered nothing):")
        for stelle in NICHT_UEBERSETZT[:25]:
            print(f"  · {stelle[:90]!r}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
