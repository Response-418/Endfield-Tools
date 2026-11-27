"""Combo-ready hint controller driven by RotPilot's Overlay Tk loop.

Sampling is cheap (one GDI grab + ~4 pixel scans per 0.5 s) and runs on the Tk
thread, so no second root/window and no cross-thread Tk calls are introduced.
Any failure degrades silently to "no hint" and never touches RotPilot's input.
"""
from __future__ import annotations

import time

from PIL import ImageGrab

from . import capture
from .banner import BannerStack
from .combo_state import ComboHints, PartyTracker
from .read_combo_live import LiveReader


class ComboHint:
    def __init__(self, root, team: list[str], cfg: dict,
                 game_hwnd_getter, save_pos, log=print) -> None:
        self.root = root
        self.game_hwnd_getter = game_hwnd_getter
        self.save_pos = save_pos
        self.log = log
        self.enabled = bool(cfg.get("comboHintOn", 1))
        self.interval = max(0.15, min(3.0, float(cfg.get("comboHintInterval", 0.5) or 0.5)))
        self.mode = cfg.get("comboHintMode", "WhenReady")
        if self.mode not in ("WhenReady", "WhileReady"):
            self.mode = "WhenReady"
        self.show_for = max(0.5, float(cfg.get("comboHintShowFor", 3.0) or 3.0))
        try:
            scale = max(0.6, min(2.5, float(cfg.get("comboHintScale", 1.0) or 1.0)))
        except (TypeError, ValueError):
            scale = 1.0

        self.reader = LiveReader()
        self.tracker = PartyTracker()
        self.hints = ComboHints(mode=self.mode, show_for=self.show_for)
        self.banner = BannerStack(root, team, (120, 300), scale=scale,
                                  on_move=self._banner_moved)
        self._rx, self._ry = cfg.get("comboHintX"), cfg.get("comboHintY")
        self._placed = False
        self._last = 0.0
        self._was_fg = True
        self._errors = 0
        # 每槽位连携 CD 快照，供主界面 CD 栏轮询读取：
        # [{"ready": bool, "p": float} | None] * 4，顺序对应 cfg["team"]。
        self.cd = [None] * 4
        self.cd_ts = 0.0

        # Place the (empty) banner immediately so it never flashes at 0,0.
        try:
            hwnd = game_hwnd_getter()
            client = capture.client_rect(hwnd) if hwnd else (0, 0, 1920, 1080)
            self.banner.set_client(client)
            self.banner.restore(self._rx, self._ry, self._default_xy(client))
            self._placed = True
        except Exception:
            pass

    def _default_xy(self, client) -> tuple[int, int]:
        left, top, right, bottom = client
        return (left + 120, top + int((bottom - top) * 0.28))

    def _banner_moved(self, rx: float, ry: float) -> None:
        self._rx, self._ry = rx, ry
        try:
            self.save_pos(rx, ry)
        except Exception as exc:  # noqa: BLE001 - hint must never break RotPilot
            self.log(f"combo hint: save pos failed: {exc}")

    def tick(self) -> None:
        """Called from Overlay._tick() on the Tk thread every ~30 ms."""
        if not self.enabled:
            return
        now = time.monotonic()
        if now - self._last < self.interval:
            return
        self._last = now
        try:
            hwnd = self.game_hwnd_getter()
            if not hwnd or not capture.is_foreground(hwnd):
                if self._was_fg:
                    self.log("combo hint: game not foreground - sampling paused")
                    self._was_fg = False
                return
            if not self._was_fg:
                self.log("combo hint: game focused - sampling resumed")
                self._was_fg = True

            client = capture.client_rect(hwnd)
            if not self._placed:
                self.banner.set_client(client)
                self.banner.restore(self._rx, self._ry, self._default_xy(client))
                self._placed = True
            else:
                self.banner.set_client(client)

            frame = ImageGrab.grab(bbox=client, all_screens=True).convert("RGB")
            state = self.reader.read(frame)
            state["t"] = now
            tracked = self.tracker.track(state)
            show = self.hints.update(tracked, time.monotonic())
            self.banner.sync(show)
            # 更新 CD 快照：combo=None 表示该槽位当前读不到条（脱战/无效）。
            cd = []
            for sl in tracked["slots"]:
                c = sl.get("combo")
                if c is None:
                    cd.append(None)
                else:
                    try:
                        cd.append({"ready": bool(c.get("ready")),
                                   "p": round(float(c.get("p", 0.0)), 4)})
                    except (TypeError, ValueError):
                        cd.append(None)
            self.cd = cd[:4]
            self.cd_ts = now
        except Exception as exc:  # noqa: BLE001 - hint must never break RotPilot
            self._errors += 1
            if self._errors <= 3:
                self.log(f"combo hint error {type(exc).__name__}: {exc}")

    def close(self) -> None:
        self.enabled = False
        self.banner.close()
