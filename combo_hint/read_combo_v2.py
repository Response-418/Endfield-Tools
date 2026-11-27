"""Combo-bar reading ported from the LATEST EndHud (EndHud-main, 2026-11-08).

Differences vs read_combo.py (which ports EndHud-0.1.0):

1. Locate(): the game re-lays out its HUD at each resolution instead of scaling the
   4K coordinates. At native 1920x1080 the bar sits on rows 987-989 while the
   scaled 4K position gives 988-990. We search dy in [-2, +1] and pick the rows
   whose columns vary least top-to-bottom (a bar column is one colour; scenery
   isn't), with a small cost for moving away from the scaled position.

2. MinFillLevel: the fill's median column must be >= 125, else it is scenery
   seen through a dark overlay, not a real bar.

3. StandsOut(): an EMPTY (dark) track must be darker than the rows above or
   below it, else a flat dark backdrop is mistaken for a cooling bar at 0%.

Everything else (ready threshold, panel marks) matches the original.

Only depends on Pillow. No EndHud source is copied verbatim; this is a
behaviour port for the RotPilot integration probe.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from PIL import Image

REF_W, REF_H = 3840, 2160
SLOT_COUNT = 4
SLOT_PITCH = 233.67

# 4K reference rectangles, anchored to the bottom-left corner.
COMBO_BAR = (85, 1978, 166, 4)
PANEL_MARK_LEFT = (68, 1988, 11, 9)
PANEL_MARK_RIGHT = (257, 1988, 11, 9)
REF_COMBO_BAR_HEIGHT = 4

# Latest ComboBar.cs constants.
TRACK_MAX_BRIGHTNESS = 80
MAX_TRACK_UNEVENNESS = 9
MIN_TRACK_COLUMNS = 8
FILL_EDGE_COLUMNS = 4
END_CAP_COLUMNS = 3
MIN_FILL_LEVEL = 125
TRACK_CONTRAST = 8
MIN_BAR_COVERAGE = 0.9
MIN_FILL_FROM_LEFT = 0.9
MAX_SHIFT_UP = 2
MAX_SHIFT_DOWN = 1
SHIFT_COST = 3


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    w: int
    h: int

    @property
    def right(self) -> int:
        return self.x + self.w

    @property
    def bottom(self) -> int:
        return self.y + self.h

    @property
    def empty(self) -> bool:
        return self.w <= 0 or self.h <= 0

    def clamped(self, width: int, height: int) -> "Rect":
        x0 = max(0, min(self.x, width))
        y0 = max(0, min(self.y, height))
        return Rect(x0, y0, max(0, min(self.right, width) - x0),
                    max(0, min(self.bottom, height) - y0))

    def offset(self, dx: int, dy: int) -> "Rect":
        return Rect(self.x + dx, self.y + dy, self.w, self.h)


def ui_scale(w: int, h: int) -> float:
    return min(w / REF_W, h / REF_H)


def bottom_left(rect: tuple[int, int, int, int], w: int, h: int) -> Rect:
    x, y, rw, rh = rect
    s = ui_scale(w, h)
    return Rect(round(x * s), h - round((REF_H - y) * s),
                max(1, round(rw * s)), max(1, round(rh * s)))


def for_slot(rect: tuple[int, int, int, int], slot: int) -> tuple[int, int, int, int]:
    x, y, rw, rh = rect
    return (round(x + slot * SLOT_PITCH), y, rw, rh)


def column_avg(px, x: int, r: Rect) -> tuple[int, int, int]:
    sr = sg = sb = 0
    for y in range(r.y, r.bottom):
        cr, cg, cb = px[x, y][:3]
        sr += cr
        sg += cg
        sb += cb
    return sr // r.h, sg // r.h, sb // r.h


def vertical_change(px, r: Rect) -> float:
    """Mean per-column max channel swing between the top and bottom row."""
    total = 0.0
    for x in range(r.x, r.right):
        lo = [255, 255, 255]
        hi = [0, 0, 0]
        for y in range(r.y, r.bottom):
            c = px[x, y][:3]
            for k in range(3):
                lo[k] = min(lo[k], c[k])
                hi[k] = max(hi[k], c[k])
        total += max(hi[k] - lo[k] for k in range(3))
    return total / r.w if r.w else 0.0


def locate(px, size: tuple[int, int], bar: Rect) -> Rect:
    """Shift the sample rows to where the bar actually is (latest EndHud Locate)."""
    rows = max(2, bar.h)
    best_shift, best_cost = 0, float("inf")
    for dy in range(-MAX_SHIFT_UP, MAX_SHIFT_DOWN + 1):
        r = Rect(bar.x, bar.y + dy, bar.w, rows).clamped(*size)
        if r.h < rows or r.w == 0:
            continue
        cost = vertical_change(px, r) + abs(dy) * SHIFT_COST
        if cost < best_cost:
            best_shift, best_cost = dy, cost
    return bar.offset(0, best_shift)


def brightness(px, size: tuple[int, int], x0: int, x1: int, y0: int, y1: int) -> float:
    """Mean brightest channel over a row band, clamped to the frame."""
    y0 = max(0, y0)
    y1 = min(size[1], y1)
    if y0 >= y1:
        return 0.0
    total, n = 0, 0
    for y in range(y0, y1):
        for x in range(max(0, x0), min(size[0], x1)):
            total += max(px[x, y][:3])
            n += 1
    return total / n if n else 0.0


def stands_out(px, size: tuple[int, int], r: Rect, scale: float) -> bool:
    """An empty track must be darker than the rows above or below it."""
    track = brightness(px, size, r.x, r.right, r.y, r.bottom)
    above0 = r.y - round(8 * scale)
    above1 = max(above0 + 1, r.y - round(4 * scale) + 1)
    below0 = r.bottom + round(2 * scale)
    below1 = max(below0 + 1, r.bottom + round(4 * scale) + 1)
    above = brightness(px, size, r.x, r.right, above0, above1)
    below = brightness(px, size, r.x, r.right, below0, below1)
    return above - track >= TRACK_CONTRAST or below - track >= TRACK_CONTRAST


def measure_combo(px, size: tuple[int, int], rect: Rect) -> dict | None:
    """Latest-EndHud combo reading; None when no bar is drawn at that spot."""
    r = locate(px, size, rect).clamped(*size)
    if r.empty:
        return None

    is_fill = [False] * r.w
    fill = 0
    fill_brightness = 0
    fill_levels: list[int] = []
    track: list[tuple[int, int]] = []

    for i in range(r.w):
        red, green, blue = column_avg(px, r.x + i, r)
        lo, hi = min(red, green, blue), max(red, green, blue)
        if lo >= 110 and hi - lo <= 50:
            is_fill[i] = True
            fill += 1
            fill_brightness += lo
            fill_levels.append(lo)
        elif hi < TRACK_MAX_BRIGHTNESS:
            track.append((i, hi))

    if fill + len(track) < r.w * MIN_BAR_COVERAGE:
        return None
    if fill and sum(is_fill[:fill]) < fill * MIN_FILL_FROM_LEFT:
        return None

    flat = [b for i, b in track
            if fill + FILL_EDGE_COLUMNS <= i < r.w - END_CAP_COLUMNS]
    if len(flat) >= MIN_TRACK_COLUMNS:
        mean = sum(flat) / len(flat)
        stddev = math.sqrt(sum((v - mean) ** 2 for v in flat) / len(flat))
        if stddev > MAX_TRACK_UNEVENNESS:
            return None

    # New in latest: reject a dim fill (bar seen through a dark overlay).
    if fill > 0:
        median_level = sorted(fill_levels)[fill // 2]
        if median_level < MIN_FILL_LEVEL:
            return None
    # New in latest: an empty dark track must stand out from adjacent rows.
    scale = rect.h / REF_COMBO_BAR_HEIGHT
    if fill == 0 and not stands_out(px, size, r, scale):
        return None

    progress = min(1.0, fill / r.w)
    white = fill > 0 and fill_brightness / fill >= 215
    ready = progress >= 0.99 or (progress >= 0.97 and white)
    return {"progress": progress, "ready": ready, "fill": fill, "width": r.w,
            "shift": r.y - rect.y}


def count_panel_marks(px, size: tuple[int, int]) -> int:
    found = 0
    for slot in range(SLOT_COUNT):
        for ref in (PANEL_MARK_LEFT, PANEL_MARK_RIGHT):
            r = bottom_left(for_slot(ref, slot), *size).clamped(*size)
            if r.empty:
                continue
            white = 0
            for y in range(r.y, r.bottom):
                for x in range(r.x, r.right):
                    cr, cg, cb = px[x, y][:3]
                    lo, hi = min(cr, cg, cb), max(cr, cg, cb)
                    if lo >= 120 and hi - lo <= 50:
                        white += 1
            factor = max(r.w, 1) * max(r.h, 1) / 99.0
            if 4 * factor <= white <= 30 * factor:
                found += 1
    return found


def analyse_image(image: Image.Image) -> dict:
    image = image.convert("RGB")
    size = image.size
    px = image.load()
    marks = count_panel_marks(px, size)
    slots = [measure_combo(px, size, bottom_left(for_slot(COMBO_BAR, s), *size))
             for s in range(SLOT_COUNT)]
    return {"size": size, "marks": marks, "slots": slots}


if __name__ == "__main__":
    import glob
    import sys

    for path in sys.argv[1:] or sorted(glob.glob("battle-events-fix/*.png")):
        im = Image.open(path).convert("RGB")
        res = analyse_image(im)
        slots = [f"{s['progress']:.0%}{'R' if s['ready'] else ''}"
                 if s else "-" for s in res["slots"]]
        print(f"{path}  marks={res['marks']}/8  combo={slots}")
