"""Independent Python implementation of EndHud's combo-ready hint behaviour.

State is passed as plain dicts:
  {"t": float, "panel": bool, "misses": int,
   "slots": [{"n": 1, "lvl": int|None, "combo": {"ready": bool, "p": float}|None, "dead": bool}, ...]}
"""

from __future__ import annotations

from dataclasses import dataclass, field


MAX_READINGS_SINCE_SEEN = 1
COOLING_READINGS_NEEDED = 2
REVIVED_HP = 0.1


class PartyTracker:
    """Carries readings across unreadable frames, like EndHud's PartyTracker."""

    def __init__(self) -> None:
        self._last_visible: dict | None = None
        self._dead = [False] * 4
        self._last_slots: list[dict | None] = [None] * 4

    def track(self, state: dict) -> dict:
        if not state.get("panel", False):
            if self._last_visible is None:
                return state
            carried = dict(self._last_visible)
            carried["misses"] = carried.get("misses", 0) + 1
            return carried

        slots = [self._track_slot(s) for s in state["slots"]]
        result = dict(state)
        result["slots"] = slots
        result["misses"] = 0
        self._last_visible = result
        return result

    def _track_slot(self, slot: dict) -> dict:
        i = slot["n"] - 1
        if slot.get("dead"):
            self._dead[i] = True
            self._last_slots[i] = slot
            return slot
        if self._dead[i] and (slot.get("hp") or 0) <= REVIVED_HP:
            out = dict(slot, dead=True, hp=0, lvl=None, combo=None)
            self._last_slots[i] = out
            return out
        if self._dead[i]:
            self._dead[i] = False
            self._last_slots[i] = None

        last = self._last_slots[i]
        combo = slot.get("combo")
        if combo is None and slot.get("lvl") is None and last is not None:
            combo = last.get("combo")
        out = dict(slot)
        out["combo"] = combo
        if last is not None and out.get("hp") is None:
            out["hp"] = last.get("hp")
        self._last_slots[i] = out
        return out


@dataclass
class ComboHints:
    """Decides which slots should show a hint. `now` is seconds from a steady clock."""

    mode: str = "WhenReady"  # WhenReady | WhileReady
    show_for: float = 3.0
    _saw_cooling: list[bool] = field(default_factory=lambda: [False] * 4)
    _cooling_readings: list[int] = field(default_factory=lambda: [0] * 4)
    _ready_at: list[float | None] = field(default_factory=lambda: [None] * 4)
    _last_state: object | None = None

    def update(self, state: dict, now: float) -> list[int]:
        in_view = state.get("panel", False) and state.get("misses", 0) <= MAX_READINGS_SINCE_SEEN
        new_reading = state is not self._last_state
        self._last_state = state
        show: list[int] = []

        for slot in state["slots"]:
            i = slot["n"] - 1
            combo = state_slot_combo(slot, in_view)
            if not new_reading:
                if combo is not None and combo.get("ready") and (
                        self.mode == "WhileReady" or self._recent(i, now)):
                    show.append(slot["n"])
                continue

            if combo is None:
                # Out of combat or fallen: start over, so a combo that is simply ready when the
                # next fight starts doesn't count. A merely out-of-view panel keeps state.
                if slot.get("dead") or (in_view and slot.get("lvl") is not None):
                    self._saw_cooling[i] = False
                    self._cooling_readings[i] = 0
                    self._ready_at[i] = None
                continue

            if not combo.get("ready"):
                self._ready_at[i] = None
                self._cooling_readings[i] += 1
                if self._cooling_readings[i] >= COOLING_READINGS_NEEDED:
                    self._saw_cooling[i] = True
                continue

            self._cooling_readings[i] = 0
            if self._saw_cooling[i]:
                self._saw_cooling[i] = False
                self._ready_at[i] = now
            if self.mode == "WhileReady" or self._recent(i, now):
                show.append(slot["n"])
        return show

    def _recent(self, i: int, now: float) -> bool:
        at = self._ready_at[i]
        return at is not None and now - at < self.show_for


def state_slot_combo(slot: dict, in_view: bool) -> dict | None:
    if not in_view or slot.get("dead"):
        return None
    return slot.get("combo")


def demo() -> None:
    """Small self-check of the state machine without any GUI."""
    hints = ComboHints(show_for=3.0)
    base = lambda combo, **kw: dict(n=1, lvl=None, combo=combo, dead=False, **kw)
    cooling = {"ready": False, "p": 0.3}
    ready = {"ready": True, "p": 1.0}

    def frame(combo, t, **kw):
        return {"t": t, "panel": True, "misses": 0, "slots": [base(combo, **kw)]}, t

    s, t = frame(cooling, 0.0)
    assert hints.update(s, t) == []
    s, t = frame(cooling, 1.0)
    assert hints.update(s, t) == []  # second cooling reading arms the hint
    s, t = frame(ready, 2.0)
    assert hints.update(s, t) == [1]  # cooldown finished -> hint
    assert hints.update(s, 2.5) == [1]  # same reading, timer refresh
    assert hints.update(s, 5.5) == []  # 3 s elapsed
    print("combo_state demo: OK")


if __name__ == "__main__":
    demo()
