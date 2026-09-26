#!/usr/bin/env python3
"""Plays the character of the voice into the running central workflow ("Configuration").

The character file (default: charakter.md next to this output) determines HOW the figure
speaks - not what the bot does. It lands in the central workflow during building in the field
"charakter" and takes effect at runtime: the node "Plan" formulates the
SPOKEN announcements (the Telegram responses remain factual). This tool changes ONLY
this one value in the running process - without rebuilding, without restart:

 1. Read character file (lines with # at the beginning are notes and are discarded)
 2. Retrieve the running central workflow from n8n (export into the n8n container)
 3. In the node "Values" replace exactly the field "charakter"
 4. Import back, activate and verify

The target is always the workflow "Configuration" of the running central.

Call:
  python3 tools/charakter-einspielen.py            (file + import)
  python3 tools/charakter-einspielen.py --dry-run  (only show, change nothing)
  python3 tools/charakter-einspielen.py --file PATH

Notes:
* Empty character text (only #-lines) disables the role.
* Before changing, the current version is locally backed up (path is printed);
 if the import fails, the backup is automatically rolled back.
* A complete rebuild (agent-patch.sh or build.sh) reads the same file.
"""
from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
import time
from pathlib import Path

HIER = Path(__file__).resolve().parent
AUSGABE = HIER.parent                                   # the project folder
WORKFLOW = "Configuration"
AGENT = "RadioAgentBot"
KNOTEN = "Values"
PROJEKT = "YOUR-N8N-PROJECT-ID"                            # n8n project
CFG = "~/.ssh/config"
RECHNER = "ai-server"
CONTAINER = "n8n"
DATEI_STANDARD = AUSGABE / "charakter.md"
MARKE = "const KONFIG = "
SCHLUSS = ";\n\n// Derived addresses"


def ssh(command: str, eingabe: str | None = None) -> str:
    """Execute command via Proxmox access (Workstation -> ai-server -> LXC 103)."""
    run = subprocess.run(["ssh", "-F", CFG, RECHNER, command],
                          input=eingabe, capture_output=True, text=True)
    if run.returncode != 0:
        raise SystemExit("ABORT: ssh failed:\n" + (run.stderr or run.stdout).strip())
    return run.stdout


def exportieren(identifier: str, target: str) -> dict:
    """Fetch a workflow from n8n; checks that the expected identifier actually came."""
    text = ssh("pct exec 103 -- bash -lc '"
               "docker exec -u node %s n8n export:workflow --id=%s --output=%s >/dev/null 2>&1; "
               "docker exec %s cat %s'" % (CONTAINER, identifier, target, CONTAINER, target))
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        raise SystemExit("ABORT: Export of %s did not return JSON (workflow present?)." % identifier)
    workflow = data[0] if isinstance(data, list) else data
    if workflow.get("id") != identifier:
        raise SystemExit("ABORT: Export returned %s instead of %s." % (workflow.get("id"), identifier))
    return workflow


def importieren(data: dict, name: str) -> None:
    """Import workflow into n8n and activate (only central, no restart)."""
    text = json.dumps(data, ensure_ascii=False, indent=2)
    ssh("pct exec 103 -- bash -c 'cat > /tmp/%s'" % name, eingabe=text)
    output = ssh("pct exec 103 -- bash -lc '"
                  "docker cp /tmp/%s %s:/tmp/ >/dev/null && "
                  "docker exec -u node %s n8n import:workflow --input=/tmp/%s --projectId=%s && "
                  "docker exec -u node %s n8n update:workflow --id=%s --active=true | tail -1'"
                  % (name, CONTAINER, CONTAINER, name, PROJEKT, CONTAINER, WORKFLOW))
    for zeile in (output or "").strip().splitlines()[-2:]:
        print(" n8n:", zeile.strip())


def lese_charakter(path: Path) -> str:
    """Read character text from file; lines starting with # are notes."""
    if not path.exists():
        raise SystemExit("ABORT: Character file missing: %s" % path)
    lines = [z for z in path.read_text(encoding="utf-8").splitlines()
              if not z.lstrip().startswith("#")]
    return "\n".join(lines).strip()


def feld_setzen(workflow: dict, text: str) -> tuple[dict, str]:
    """In the "Values" node, replace the "charakter" field; gives (expiration, old text)."""
    nodes = [k for k in workflow.get("nodes", []) if k.get("name") == KNOTEN]
    if not nodes:
        raise SystemExit("ABORT: Node %r not found." % KNOTEN)
    js = nodes[0].get("parameters", {}).get("jsCode", "")
    if MARKE not in js or SCHLUSS not in js:
        raise SystemExit("ABORT: The node %r does not have the expected format.\n"
                         " First rebuild and deploy the bot - the running version"
                         "does not know about the field yet." % KNOTEN)
    beginning = js.index(MARKE) + len(MARKE)
    ende = js.index(SCHLUSS, beginning)
    werte = json.loads(js[beginning:ende])
    alt = str(werte.get("charakter", ""))
    werte["charakter"] = text
    nodes[0]["parameters"]["jsCode"] = (js[:beginning]
                                         + json.dumps(werte, ensure_ascii=False, indent=2)
                                         + js[ende:])
    return workflow, alt


def short(text: str, laenge: int = 90) -> str:
    text = " | ".join(z.strip() for z in text.strip().splitlines())
    return text[:laenge] + ("..." if len(text) > laenge else "")


def main() -> int:
    parser = argparse.ArgumentParser(description="Deploy character of the voice")
    parser.add_argument("--file", type=Path, default=DATEI_STANDARD,
                          help="Character file (default: %s)" % DATEI_STANDARD)
    parser.add_argument("--dry-run", action="store_true",
                          help="only show what would change (write nothing)")
    args = parser.parse_args()

    text = lese_charakter(args.file)
    print("Output   : %s" % AUSGABE)
    print("Expiration : %s (n8n)" % WORKFLOW)
    print("File     : %s" % args.file)
    print("Character: %s" % ("AUS (empty)" if not text else "%d characters" % len(text)))
    if text:
        print("           %s" % short(text))

    print("--- retrieve current version")
    workflow = exportieren(WORKFLOW, "/tmp/charakter-running.json")
    original = copy.deepcopy(workflow)                     # for backup and rollback
    workflow, alt = feld_setzen(workflow, text)
    print(" so far   : %s" % ("(empty)" if not alt.strip() else short(alt)))

    if args.dry:
        print("Dry run - nothing changed.")
        return 0

    sicherung = Path("/tmp/charakter-sicherung-%s-%s.json"
                     % (WORKFLOW, time.strftime("%Y%m%d-%H%M%S")))
    sicherung.write_text(json.dumps(original, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Backup: %s" % sicherung)

    if alt == text:
        print("Unchanged - the file is already in the central repository"
              "(no write access needed).")
    else:
        print("--- import")
        try:
            importieren(workflow, "charakter-new.json")
        except SystemExit as error:
            print(" Import failed - the backup will be restored.")
            importieren(original, "charakter-sicherung.json")
            raise error

        print("--- verify")
        frisch = exportieren(WORKFLOW, "/tmp/charakter-kontrolle.json")
        now = _gegenprobe(frisch)
        if now != text:
            print(" WARNING: The value in n8n differs (backup: %s)." % sicherung)
            return 1
        print(" Central repository holds the new character (%d characters)." % len(text))

    agent = exportieren(AGENT, "/tmp/charakter-agent.json")
    wirksam = "konfig.charakter" in json.dumps(agent, ensure_ascii=False)
    print(" Character is wired in the process: %s"
          % ("ja" if wirksam else "NO - Agent needs to be rebuilt and imported!"))
    print("\nDone." + (" The new character takes effect from now on (no restart required)."
                        if alt != text else ""))
    return 0


def _gegenprobe(workflow: dict) -> str:
    """Helping hand: read the value from the freshly fetched version (without setting it)."""
    nodes = [k for k in workflow.get("nodes", []) if k.get("name") == KNOTEN][0]
    js = nodes["parameters"]["jsCode"]
    beginning = js.index(MARKE) + len(MARKE)
    ende = js.index(SCHLUSS, beginning)
    return str(json.loads(js[beginning:ende]).get("charakter", ""))


if __name__ == "__main__":
    sys.exit(main())
