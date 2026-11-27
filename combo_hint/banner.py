"""Combo-ready banner: transparent Tk Toplevel, latest-EndHud look, draggable.

Created as a Toplevel of RotPilot's existing Tk root (never a second Tk root).
Position is persisted through a callback into RotPilot's own config.json.
"""
from __future__ import annotations

import time
import tkinter as tk

TRANSPARENT = "#010203"      # colour keyed out by Windows; never drawn
ACCENT = "#e6c229"
TEXT = "#ffffff"
SHADOW = "#05080b"
BANNER_W = 340
BANNER_H = 84
GAP = 6
SLIDE_MS = 320
SLIDE_PX = 160
FLARE_MS = 600
EDGE_W = 6
FLARE_W = 18
SKEW = 0.2126                # tan(12deg), same slant as the latest banner


class BannerStack:
    def __init__(self, root: tk.Tk, team: list[str], xy: tuple[int, int],
                 scale: float = 1.0, on_move=None) -> None:
        self.root = root
        self.team = team
        self.scale = scale
        self.w = max(1, round(BANNER_W * scale))
        self.h = max(1, round(BANNER_H * scale))
        self.on_move = on_move          # called with (rx, ry) relative to game client
        self.client = None              # set by controller before first read
        self.closed = False
        self._after_ids: set[int] = set()
        self.host = tk.Toplevel(root)
        self.host.overrideredirect(True)
        self.host.attributes("-topmost", True)
        try:
            self.host.attributes("-transparentcolor", TRANSPARENT)
        except tk.TclError:
            self.host.attributes("-alpha", 0.9)
        self.host.configure(bg=TRANSPARENT)
        self.host.geometry(f"+{xy[0]}+{xy[1]}")
        self.banners: dict[int, dict] = {}
        self._dx = self._dy = 0
        self._bind_drag(self.host)

    def name(self, slot: int) -> str:
        return (self.team[slot - 1] if 0 <= slot - 1 < len(self.team) else "") \
            or f"slot{slot}"

    def set_client(self, client: tuple[int, int, int, int]) -> None:
        self.client = client

    def restore(self, rx, ry, default: tuple[int, int]) -> None:
        """Place the banner from saved ratios, or a screen-relative default."""
        try:
            if self.client and rx is not None and ry is not None:
                left, top, right, bottom = self.client
                x = round(left + float(rx) * (right - left))
                y = round(top + float(ry) * (bottom - top))
            else:
                x, y = default
            x = max(0, min(x, self.root.winfo_screenwidth() - self.w))
            y = max(0, min(y, self.root.winfo_screenheight() - self.h))
            self.host.geometry(f"+{x}+{y}")
        except (ValueError, TypeError, tk.TclError):
            self.host.geometry(f"+{default[0]}+{default[1]}")

    # --- drag: same interaction as RotPilot's floating bar ---
    def _bind_drag(self, widget: tk.Misc) -> None:
        try:
            widget.bind("<Button-1>", self._drag_start)
            widget.bind("<B1-Motion>", self._drag_move)
            widget.bind("<ButtonRelease-1>", self._drag_release)
            for child in widget.winfo_children():
                self._bind_drag(child)
        except tk.TclError:
            pass

    def _drag_start(self, event: tk.Event) -> None:
        self._dx = event.x_root - self.host.winfo_x()
        self._dy = event.y_root - self.host.winfo_y()

    def _drag_move(self, event: tk.Event) -> None:
        self.host.geometry(f"+{event.x_root - self._dx}+{event.y_root - self._dy}")

    def _drag_release(self, event: tk.Event) -> None:
        if self.on_move is None or self.client is None:
            return
        try:
            left, top, right, bottom = self.client
            rx = (self.host.winfo_x() - left) / max(1, right - left)
            ry = (self.host.winfo_y() - top) / max(1, bottom - top)
            self.on_move(rx, ry)
        except (ValueError, tk.TclError):
            pass

    # --- hint rendering ---
    def sync(self, wanted: list[int]) -> None:
        if self.closed:
            return
        for slot in list(self.banners):
            if slot not in wanted:
                self._slide_out(slot)
        for slot in wanted:
            if slot not in self.banners:
                self._slide_in(slot)
        self._restack()

    def _make(self, slot: int) -> dict:
        w, h, s = self.w, self.h, self.scale
        holder = tk.Frame(self.host, bg=TRANSPARENT, width=w, height=h + GAP)
        holder.pack_propagate(False)
        canvas = tk.Canvas(holder, width=w, height=h + GAP, bg=TRANSPARENT,
                           highlightthickness=0, bd=0)
        canvas.pack(fill="both", expand=True)
        dx = round(h * SKEW / 2)
        x0 = dx + 4
        left = x0 + EDGE_W + round(14 * s)
        name_size = max(12, round(18 * s))
        cap_size = max(9, round(12 * s))
        ny, cy = round(h * 0.38), round(h * 0.72)

        def draw(edge_w: int) -> None:
            canvas.delete("all")
            canvas.create_polygon(
                x0 + dx, 0, x0 + dx + edge_w, 0,
                x0 - dx + edge_w, h, x0 - dx, h,
                fill=ACCENT, tags="edge")
            for off in (1, 0):
                canvas.create_text(left + off, ny + off, anchor="w",
                                   text=self.name(slot),
                                   fill=SHADOW if off else TEXT,
                                   font=("Microsoft YaHei UI", name_size, "bold"))
                canvas.create_text(left + off, cy + off, anchor="w",
                                   text="连携就绪",
                                   fill=SHADOW if off else ACCENT,
                                   font=("Microsoft YaHei UI", cap_size))

        draw(EDGE_W)
        self._bind_drag(holder)
        self._bind_drag(canvas)
        return {"holder": holder, "draw": draw}

    def _after(self, cb) -> None:
        """Track every pending animation callback so close() can cancel it.

        A pending `after` script that fires after the Toplevel/root is destroyed
        can make Tcl panic (Tcl_AsyncDelete) instead of raising a clean
        TclError.  Never leave one behind.
        """
        if self.closed:
            return
        box = []

        def wrapped():
            if box:
                self._after_ids.discard(box[0])
            cb()

        try:
            aid = self.root.after(16, wrapped)
        except tk.TclError:
            return
        box.append(aid)
        self._after_ids.add(aid)

    def _slide_in(self, slot: int) -> None:
        item = self._make(slot)
        self.banners[slot] = item
        try:
            item["holder"].place(x=-SLIDE_PX, width=self.w, height=self.h + GAP)
        except tk.TclError:
            self.banners.pop(slot, None)
            return
        start = time.monotonic()

        def step() -> None:
            if self.closed or slot not in self.banners or self.banners[slot] is not item:
                return
            t = time.monotonic() - start
            p = min(1.0, t * 1000 / SLIDE_MS)
            eased = 1 - (1 - p) ** 3
            try:
                item["holder"].place_configure(x=round(-SLIDE_PX * (1 - eased)))
                if t * 1000 >= SLIDE_MS / 2:
                    fp = min(1.0, (t * 1000 - SLIDE_MS / 2) / FLARE_MS)
                    fe = 1 - (1 - fp) ** 3
                    item["draw"](round(FLARE_W + (EDGE_W - FLARE_W) * fe))
                if t * 1000 < SLIDE_MS / 2 + FLARE_MS:
                    self._after(step)
                else:
                    item["draw"](EDGE_W)
            except tk.TclError:
                return

        step()

    def _slide_out(self, slot: int) -> None:
        item = self.banners.pop(slot, None)
        if item is None or self.closed:
            return
        start = time.monotonic()

        def step() -> None:
            if self.closed:
                return
            p = min(1.0, (time.monotonic() - start) * 1000 / SLIDE_MS)
            eased = p * p
            try:
                item["holder"].place_configure(x=round(-SLIDE_PX * 0.5 * eased))
            except tk.TclError:
                return
            if p < 1:
                self._after(step)
            else:
                try:
                    item["holder"].destroy()
                except tk.TclError:
                    pass
                self._restack()

        step()

    def _restack(self) -> None:
        for i, slot in enumerate(sorted(self.banners)):
            item = self.banners[slot]
            try:
                item["holder"].place_configure(y=i * (self.h + GAP))
                item["holder"].lift()
            except tk.TclError:
                pass

    def close(self) -> None:
        """Cancel animations and drop widget refs on the owning Tk thread."""
        self.closed = True
        for aid in list(self._after_ids):
            try:
                self.root.after_cancel(aid)
            except (tk.TclError, ValueError):
                pass
        self._after_ids.clear()
        for item in list(self.banners.values()):
            try:
                item["holder"].destroy()
            except tk.TclError:
                pass
            item.clear()
        self.banners.clear()
        host = self.host
        self.host = None
        if host is not None:
            try:
                host.destroy()
            except tk.TclError:
                pass
