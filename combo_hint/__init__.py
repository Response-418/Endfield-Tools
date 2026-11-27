"""Combo-ready hint feature for Endfield RotPilot.

Ported from the verified combo_hint_probe: EndHud-main's ComboBar reading + a
faithful Python port of PartyTracker / ComboHints, with a transparent draggable
Tk banner. No .NET, no ONNX, no Wiki, no extra Python packages beyond Pillow.
"""
from .controller import ComboHint

__all__ = ["ComboHint"]
