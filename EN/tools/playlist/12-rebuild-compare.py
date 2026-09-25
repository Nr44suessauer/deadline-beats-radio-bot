#!/usr/bin/env python3
"""Compares the new build of the bot process with the running version.

Purpose: Before deployment, see what actually changes. A complete
new build (agent-deploy.sh) replaces the process - anything missing in the builder
would be gone afterwards. This script lists therefore:

 * Nodes that only exist in the running version (would be lost)
 * Nodes that only exist in the new build (new)
 * content differences per node (excluding access values and switch fields)

It writes nothing and does not abort - the evaluation remains with the human.

Call:
    python3 12-rebuild-vergleich.py <running.json> <rebuild.json>
"""
import importlib.util
import json
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]


def lade_hilfen():
    """Reuses the comparison helpers from tempo/03-tempo-patch.py."""
    path = TOOLS / "tempo" / "03-tempo-patch.py"
    spec = importlib.util.spec_from_file_location("tempo_patchen", path)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


def as_workflow(data):
    return data[0] if isinstance(data, list) else data


def main() -> int:
    hilfen = lade_hilfen()
    laufend_text = Path(sys.argv[1]).read_text(encoding="utf-8")
    gebaut_text = Path(sys.argv[2]).read_text(encoding="utf-8")

    identifier = hilfen.kennung_aus(laufend_text) or ""
    key = ""
    import re
    hits = re.search(r"[0-9a-f]{16}:[0-9a-f]{32}", laufend_text)
    if hits:
        key = hits.group(0)

    running = as_workflow(json.loads(laufend_text))
    gebaut = as_workflow(json.loads(gebaut_text))

    alt = {n["name"]: n for n in running["nodes"]}
    new = {n["name"]: n for n in gebaut["nodes"]}

    nur_laufend = sorted(set(alt) - set(new))
    nur_neu = sorted(set(new) - set(alt))

    alt_v = hilfen.vergleichsbild(running["nodes"], [identifier, key])
    neu_v = hilfen.vergleichsbild(gebaut["nodes"], ["dummy"])

    unterschiede = []
    for name in sorted(set(alt) & set(new)):
        if alt_v[name] != neu_v[name]:
            unterschiede.append(name)

    print(f"Running nodes: {len(alt)}   New build: {len(new)}")
    print(f"Only ongoing (would be removed): {nur_laufend or '(keine)'}")
    print(f"Only in new construction (new): {nur_neu or '(keine)'}")
    print(f"Content different ({len(unterschiede)}): {unterschiede or '(keine)'}")
    equal = running.get("connections") == gebaut.get("connections")
    print(f"Connections unchanged: {equal}")
    if not equal:
        old_c, new_c = running.get("connections") or {}, gebaut.get("connections") or {}
        for name in sorted(set(old_c) | set(new_c)):
            if old_c.get(name) != new_c.get(name):
                print(f" different: {name} -> {json.dumps(new_c.get(name), ensure_ascii=False)[:160]}")

    print()
    if not nur_laufend:
        print("Verdict: the new build contains everything that is currently running.")
    else:
        print("ATTENTION: the new build would lose nodes - clarify beforehand.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
