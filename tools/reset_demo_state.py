"""Put the demo back to its opening state.

Beat 3 only works if Rowan's GitHub switch starts OFF - the whole point is pressing it on
camera and watching the fetch happen. Testing the consent flow leaves it ON, and then the
findings panel is already full and the reveal cannot be performed. This resets it.

It edits the stored state directly rather than going through the app, because revoking
through the app calls forget() and deletes the cached GitHub lookup - and that cache is what
makes the reveal instant and safe to do with no network.

    uv run python tools/reset_demo_state.py
"""
from __future__ import annotations

import json
from pathlib import Path

from fit_happens.store import Run

SLUG, CID = "demo", "rowan-feltz-6cb5cd"


def main() -> None:
    consent = Path(f"data/runs/{SLUG}/consent/{CID}.json")
    if not consent.exists():
        print(f"no consent record at {consent} - nothing to reset")
        return

    d = json.loads(consent.read_text())
    d["grants"]["github"] = False
    d["history"] = [h for h in d.get("history", []) if h.get("scope") != "github"]
    consent.write_text(json.dumps(d, indent=2))

    run = Run(SLUG)
    c = run.candidate(CID)
    if c:
        c.verifications = []
        c.consent_grants = dict(d["grants"])
        c.consent_summary = "The CV you sent us"
        run.save_candidate(c)

    print("Demo reset. Rowan's GitHub switch is OFF and the findings panel is empty,")
    print("so beat 3 can be performed live. The cached lookup is untouched, so pressing")
    print("'Share this' fills the panel instantly and works with no network.")


if __name__ == "__main__":
    main()
