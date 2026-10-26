"""All user-adjustable settings (look, timing, encoding) in one serialisable object."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields

FPS_RATIONAL = {23.976: "24000/1001", 29.97: "30000/1001", 59.94: "60000/1001"}

SEPARATORS = {
    "／": "／",
    "/": " / ",
    "|": " | ",
    "·": " · ",
    "空格": "　",
}


@dataclass
class Style:
    # ---- canvas
    width: int = 1920
    height: int = 1080
    fps: float = 30.0
    bg_color: str = "#000000"
    text_color: str = "#FFFFFF"
    current_color: str = "#FFFFFF"
    # ---- font
    font_family: str = "Microsoft YaHei"
    font_style: str = "Bold"
    font_file: str = ""
    auto_size: bool = True
    font_size: int = 130          # centre-line pixel size when auto_size is off
    size_ratio: float = 0.72      # other lines relative to the centre line
    letter_spacing: float = 0.0   # percent of the font size
    line_spacing: float = 0.30    # gap between lyric lines, in em
    wrap_spacing: float = 0.04    # gap between the two rows of one wrapped lyric, in em
    visible_lines: int = 7
    lines_above: int = -1         # -1: centre line in the middle
    max_rows: int = 2
    margin_x: float = 4.0         # percent of width, each side
    margin_y: float = 2.0         # percent of height, each side
    align: str = "center"         # left / center / right
    # ---- opacity
    near_opacity: float = 0.72
    far_opacity: float = 0.22
    past_opacity: float = 1.0     # extra factor for lines already sung (above)
    edge_fade: bool = True
    outline: float = 0.0          # stroke width, percent of font size
    outline_color: str = "#000000"
    # ---- motion / timing
    animate: bool = True
    anim_duration: float = 0.40
    lead_time: float = 0.10       # switch to a line this many seconds before it starts
    time_offset: float = 0.0      # shift all lyrics (s); + = later
    # ---- merge short lines
    merge_short: bool = False
    merge_max_units: float = 4.0
    merge_max_gap: float = 1.5
    merge_max_parts: int = 4
    merge_separator: str = "／"
    part_dim: float = 0.55
    # ---- intro / interlude hint
    countdown: bool = True
    countdown_gap: float = 6.0
    countdown_secs: int = 3
    upcoming_opacity: float = 0.55
    # ---- lyric file handling
    join_same_time: bool = True
    # ---- encoding
    encoder: str = "libx264"
    qp: int = 22
    preset: str = "veryfast"
    keyint: float = 5.0
    audio_bitrate: int = 192      # kbps, 0 = no audio track
    container: str = "mp4"

    def separator_text(self) -> str:
        return SEPARATORS.get(self.merge_separator, self.merge_separator)

    def fps_arg(self) -> str:
        for k, v in FPS_RATIONAL.items():
            if abs(self.fps - k) < 1e-3:
                return v
        return f"{self.fps:g}"

    def above_below(self) -> tuple[int, int]:
        n = max(1, int(self.visible_lines))
        a = (n - 1) // 2 if self.lines_above < 0 else min(max(0, int(self.lines_above)), n - 1)
        return a, n - 1 - a

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Style":
        s = cls()
        for f in fields(cls):
            if f.name in d:
                try:
                    v = d[f.name]
                    t = type(getattr(s, f.name))
                    setattr(s, f.name, t(v) if t in (int, float, str, bool) else v)
                except (TypeError, ValueError):
                    pass
        return s

    def copy(self) -> "Style":
        return Style.from_dict(self.to_dict())


def load_settings(path: str) -> dict:
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def save_settings(path: str, data: dict) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
