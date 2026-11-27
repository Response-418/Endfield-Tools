"""Live-reading adapter -- faithful to EndHud's PartyReader / PartyTracker semantics.

EndHud separates "exploration" from "combat, bar hidden by VFX" with ONE signal:
the OCR'd Level (PartyReader.cs 60-62). We have no OCR, but our pixel test already
distinguishes a bar from level digits, so only two adaptations are needed:

  1. EDGE_READY: GDI drops the last bar column (82/83 = 0.98795), which EndHud's
     Windows.Graphics.Capture sees as 83/83. Normalise >= 0.985 to ready.
  2. Level surrogate: set lvl=1 only when NO slot shows a bar at all (all four
     unreadable) -- that is exploration. A single unreadable slot mid-combat must
     leave lvl=None so PartyTracker carries its last combo.

No latch, no debounce, no blank counters -- combo_state.py stays an untouched
port of EndHud's PartyTracker + ComboHints and does all the state work.
"""
from __future__ import annotations

from .read_combo_v2 import analyse_image

EDGE_READY = 0.985           # GDI drops the last bar column (82/83 = 0.98795) -> full


class LiveReader:
    """Turns a frame into a PartyTracker state, EndHud-faithfully."""

    def read(self, frame) -> dict:
        res = analyse_image(frame)
        combos: list[dict | None] = []
        for reading in res["slots"]:
            if reading is None:
                combos.append(None)
            else:
                p = reading["progress"]
                ready = bool(reading["ready"]) or p >= EDGE_READY
                combos.append({"ready": ready, "p": p})

        # Only when the WHOLE panel has no bars is this exploration.
        level_visible = all(c is None for c in combos)
        # marks is the reliable panel signal (5-8 in battle, 0 in exploration).
        panel = res["marks"] >= 5

        slots = []
        for i, combo in enumerate(combos):
            slots.append({"n": i + 1, "lvl": 1 if level_visible else None,
                          "combo": combo, "dead": False, "hp": None})
        return {"panel": panel, "misses": 0, "slots": slots, "raw": res}
