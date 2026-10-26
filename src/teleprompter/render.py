"""Teleprompter frame renderer.

Shared by the live preview and the exporter, so what you see is what you get.
All geometry is in output-video pixels; the caller's QPainter may be scaled.

Layout model
------------
* The current lyric sits on a fixed anchor line, rendered at ``Fc`` px.
* Lines above/below are stacked outward at ``Fo = Fc * size_ratio``; each
  lyric keeps its own height, so a lyric wrapped onto two rows (tight
  ``wrap_spacing``) simply takes more room.
* Wrapping is decided once at the large size, and a lyric is drawn by
  uniformly scaling its glyph paths - so it keeps the same shape while it
  scrolls into the centre.
* Opacity falls off linearly from ``near_opacity`` (neighbours) to
  ``far_opacity`` (outermost visible line).
"""
from __future__ import annotations
from teleprompter.i18n import tr, render_arg

import bisect
import math
from dataclasses import dataclass
from itertools import combinations
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt, QTextBoundaryFinder
from PySide6.QtGui import (QBrush, QColor, QFont, QFontMetricsF, QImage, QLinearGradient,
                           QPainter, QPainterPath, QPen)

from .lyrics import Entry, LyricLine, MergeOptions, build_entries, char_units
from .style import Style

REF = 256.0              # glyph paths are built at this pixel size, then scaled
ROW_EM = 1.0             # height of one text row, in em
HOLD_AFTER_LINE = 1.0    # interlude: wait this long after a line ends before moving on
UPCOMING_FADE = 0.20     # interlude: fade-in when the waiting line becomes current
PART_FADE = 0.12         # merged line: cross-fade between its parts
EDGE_FADE = 0.075        # fraction of height faded out at top and bottom

DEMO_LINES = [
    tr('提词器预览示例'), tr('这一行是正在演唱的歌词'), tr('上下行字号略小、透明度递减'),
    tr('当一句歌词太长超出屏幕宽度时会自动折成两行显示并且行距更紧凑'),
    tr('加载音频和歌词后即可预览真实效果'), tr('提词器预览'), "♪", tr('啦啦啦'), tr('再见'),
]


def demo_lines() -> list[LyricLine]:
    return [LyricLine(1.0 + i * 2.5, 1.0 + i * 2.5 + 2.2, render_arg(t)) for i, t in enumerate(DEMO_LINES)]


def _ease(x: float) -> float:
    # ease-in-out cubic
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    return 4 * x * x * x if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def _lerp(a: float, b: float, f: float) -> float:
    return a + (b - a) * f


def _qcolor(hexstr: str, fallback: str = "#FFFFFF") -> QColor:
    c = QColor(hexstr)
    return c if c.isValid() else QColor(fallback)


def make_font(family: str, style_name: str, pixel_size: int, letter_spacing_px: float = 0.0) -> QFont:
    f = QFont(family)
    if style_name:
        f.setStyleName(style_name)
    f.setPixelSize(max(1, int(pixel_size)))
    f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    f.setKerning(True)
    if letter_spacing_px:
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, letter_spacing_px)
    return f


@dataclass
class EntryGeo:
    part_paths: list            # QPainterPath per part (one for a normal lyric)
    sep_path: Optional[QPainterPath]
    rows: int
    height_em: float            # block height in em (at REF size, before fit)
    fit: float                  # extra down-scale so the widest row fits
    width_ref: float            # widest row, REF px (after fit not applied)


@dataclass
class Item:
    j: int
    y: float
    size: float
    alpha: float
    cmix: float          # 0 = normal colour, 1 = current-line colour
    centre: float        # 1 at centre, 0 one line away or more
    part_w: Optional[tuple]


class Renderer:
    def __init__(self, style: Style, lines: Optional[list[LyricLine]] = None):
        self.style = style
        self.lines = list(lines) if lines else []
        self.W = int(style.width)
        self.H = int(style.height)
        self._geo: dict[int, EntryGeo] = {}
        self._layout_cache: dict[int, dict] = {}
        self._setup_font()
        self._setup_sizes()
        self.entries: list[Entry] = build_entries(
            self.lines,
            MergeOptions(style.merge_short, style.merge_max_units, style.merge_max_gap, style.merge_max_parts),
            self._fits_one_row)
        self._build_timeline()

    # ------------------------------------------------------------ font/metrics
    def _setup_font(self):
        s = self.style
        self.ls_px = s.letter_spacing / 100.0 * REF
        self.font = make_font(s.font_family, s.font_style, int(REF), self.ls_px)
        self.fm = QFontMetricsF(self.font)
        ref = QPainterPath()
        ref.addText(0, 0, make_font(s.font_family, s.font_style, int(REF)), tr('国H字'))
        r = ref.boundingRect()
        self.ink_centre = (r.top() + r.bottom()) / 2 if r.height() > 0 else -0.35 * REF
        self.sep_text = s.separator_text()

    def text_width(self, text: str) -> float:
        """Advance width at REF px (letter spacing included, trailing gap removed)."""
        if not text:
            return 0.0
        return self.fm.horizontalAdvance(text) - self.ls_px

    def _setup_sizes(self):
        s = self.style
        W, H = self.W, self.H
        self.above, self.below = s.above_below()
        r = max(0.1, min(1.0, s.size_ratio))
        ls = max(0.0, s.line_spacing)
        a, b = self.above, self.below

        def stack_factor() -> float:  # total height / Fc for single-row lines
            f = ROW_EM + (a + b) * r * ROW_EM
            f += ls * (1 + r) / 2 * (min(a, 1) + min(b, 1))
            f += ls * r * (max(a - 1, 0) + max(b - 1, 0))
            return f

        usable_h = H * (1 - 2 * s.margin_y / 100.0)
        mx = W * s.margin_x / 100.0
        self.wrap_w = max(10.0, W - 2 * mx)
        if s.auto_size:
            fc = usable_h / stack_factor()
            # do not let "fill the height" blow typical lines past the width
            # (portrait screens): the median lyric must still fit on one row
            rows = [r for ln in self.lines for r in ln.text.split("\n") if r.strip()]
            if len(rows) >= 3:
                ems = sorted(self.text_width(r) / REF for r in rows)
                median = ems[len(ems) // 2]
                if median > 0:
                    fc = min(fc, self.wrap_w / median)
            self.Fc = max(8.0, fc)
        else:
            self.Fc = float(max(8, s.font_size))
        self.Fo = self.Fc * r
        total = self.Fc * stack_factor()
        above_h = a * self.Fo * ROW_EM
        if a >= 1:
            above_h += ls * (self.Fc + self.Fo) / 2 + (a - 1) * ls * self.Fo
        self.anchor_y = (H - total) / 2 + above_h + self.Fc * ROW_EM / 2
        self.anchor_x = {"left": mx, "right": W - mx}.get(s.align, W / 2)
        self.max_w_ref = self.wrap_w * REF / self.Fc
        # room kept above a line that is waiting for its cue (countdown dots)
        self.wait_gap = max(0.0, 0.5 * self.Fc - ls * (self.Fc + self.Fo) / 2)

    def _fits_one_row(self, texts: list[str]) -> bool:
        return self.text_width(self.sep_text.join(texts)) <= self.max_w_ref

    # ---------------------------------------------------------------- wrapping
    @staticmethod
    def _break_points(text: str) -> list[int]:
        """Allowed line-break positions (python indices), excluding 0 and len."""
        u16_to_py = {}
        u = 0
        for i, ch in enumerate(text):
            u16_to_py[u] = i
            u += 2 if ord(ch) > 0xFFFF else 1
        u16_to_py[u] = len(text)
        bf = QTextBoundaryFinder(QTextBoundaryFinder.BoundaryType.Line, text)
        out = []
        pos = bf.toNextBoundary()
        while pos != -1:
            py = u16_to_py.get(pos)
            if py is not None and 0 < py < len(text):
                out.append(py)
            pos = bf.toNextBoundary()
        return out

    @staticmethod
    def _natural(text: str, pos: int) -> bool:
        prev = text[pos - 1]
        return prev.isspace() or text[pos].isspace() or prev in "，。、！？,.!?;；:：)）」』】~～…—-"

    def _wrap(self, text: str) -> tuple[list[str], float]:
        """Split ``text`` into balanced rows. Returns (rows, widest_row_ref_px)."""
        text = " ".join(text.split())
        w = self.text_width(text)
        if w <= self.max_w_ref or self.style.max_rows <= 1:
            return [text], w
        cands = self._break_points(text)
        if not cands:
            return [text], w
        if len(cands) > 80:  # very long text: thin out candidates
            step = len(cands) / 80
            cands = [cands[int(i * step)] for i in range(80)]
        best_overall = None   # most balanced split seen (fallback when nothing fits)
        for k in range(2, max(2, self.style.max_rows) + 1):
            best_fit = None
            for cut in combinations(cands, k - 1):
                bounds = (0,) + cut + (len(text),)
                rows = [text[bounds[i]:bounds[i + 1]].strip() for i in range(k)]
                if any(not r for r in rows):
                    continue
                widest = max(self.text_width(r) for r in rows)
                unnatural = sum(0 if self._natural(text, c) else 1 for c in cut)
                # breaking at a space / punctuation reads far better in CJK lyrics
                cost = widest * (1 + 0.2 * unnatural)
                if widest <= self.max_w_ref and (best_fit is None or cost < best_fit[0]):
                    best_fit = (cost, rows, widest)
                if best_overall is None or widest < best_overall[2]:
                    best_overall = (cost, rows, widest)
            if best_fit is not None:
                return best_fit[1], best_fit[2]
            if k >= 3 and len(cands) > 40:
                break
        if best_overall is None:
            return [text], w
        return best_overall[1], best_overall[2]

    # -------------------------------------------------------------- geometry
    def geo(self, j: int) -> EntryGeo:
        g = self._geo.get(j)
        if g is None:
            g = self._build_geo(self.entries[j])
            self._geo[j] = g
        return g

    def _row_x(self, w: float) -> float:
        al = self.style.align
        return 0.0 if al == "left" else (-w if al == "right" else -w / 2)

    def _build_geo(self, e: Entry) -> EntryGeo:
        ws = max(0.0, self.style.wrap_spacing)
        font = self.font
        if e.merged:
            texts = [" ".join(p.text.split()) for p in e.parts]
            widths = [self.text_width(t) for t in texts]
            sep_w = self.fm.horizontalAdvance(self.sep_text)
            adv = [self.fm.horizontalAdvance(t) for t in texts]
            total = sum(adv) + sep_w * (len(texts) - 1) - self.ls_px
            hb = ROW_EM * REF
            base = -self.ink_centre
            x = self._row_x(total)
            paths, sep = [], QPainterPath()
            for i, t in enumerate(texts):
                p = QPainterPath()
                p.addText(x, base, font, t)
                paths.append(p)
                x += adv[i]
                if i < len(texts) - 1:
                    sep.addText(x, base, font, self.sep_text)
                    x += sep_w
            fit = min(1.0, self.max_w_ref / total) if total > 0 else 1.0
            return EntryGeo(paths, sep, 1, hb / REF, fit, max(total, max(widths, default=0)))

        rows: list[str] = []
        widest = 0.0
        for src in e.parts[0].text.split("\n"):
            r, wmax = self._wrap(src)
            rows.extend(r)
            widest = max(widest, wmax)
        n = max(1, len(rows))
        hb = n * ROW_EM * REF + (n - 1) * ws * REF
        path = QPainterPath()
        for i, row in enumerate(rows):
            yc = -hb / 2 + (i + 0.5) * ROW_EM * REF + i * ws * REF
            path.addText(self._row_x(self.text_width(row)), yc - self.ink_centre, font, row)
        fit = min(1.0, self.max_w_ref / widest) if widest > 0 else 1.0
        return EntryGeo([path], None, n, hb / REF, fit, widest)

    def block_h(self, j: int, size: float) -> float:
        g = self.geo(j)
        return g.height_em * size * g.fit

    # ---------------------------------------------------------------- timeline
    def _build_timeline(self):
        s = self.style
        E = self.entries
        n = len(E)
        off, lead = s.time_offset, s.lead_time
        self.start = [e.start + off for e in E]
        self.act = [t - lead for t in self.start]
        self.part_act = [[p.start + off - lead for p in e.parts] for e in E]
        self.upcoming = [False] * n
        arrive = [0.0] * n
        if n:
            arrive[0] = -math.inf
            self.upcoming[0] = bool(s.countdown)
        for i in range(1, n):
            prev = E[i - 1]
            last = prev.parts[-1]
            if prev.end is not None:
                end_prev = prev.end + off
            else:
                end_prev = last.start + off + min(6.0, max(1.0, char_units(last.text) * 0.38))
            end_prev = min(end_prev, self.start[i])
            if s.countdown and self.start[i] - end_prev >= s.countdown_gap:
                arrive[i] = max(end_prev + HOLD_AFTER_LINE, self.act[i - 1] + 0.05)
                self.upcoming[i] = arrive[i] < self.act[i]
                if not self.upcoming[i]:
                    arrive[i] = self.act[i]
            else:
                arrive[i] = self.act[i]
        for i in range(1, n):  # keep monotonic
            if arrive[i] < arrive[i - 1]:
                arrive[i] = arrive[i - 1]
        D = s.anim_duration if s.animate else 0.0
        self.trans = []
        for i in range(1, n):
            nxt = arrive[i + 1] if i + 1 < n else math.inf
            self.trans.append((arrive[i], max(0.0, min(D, nxt - arrive[i])), i - 1, i))
        self.trans_t0 = [x[0] for x in self.trans]
        self.arrive = arrive

    def position(self, t: float) -> float:
        k = bisect.bisect_right(self.trans_t0, t) - 1
        if k < 0:
            return 0.0
        t0, dur, a, b = self.trans[k]
        if dur <= 0 or t >= t0 + dur:
            return float(b)
        return a + (b - a) * _ease((t - t0) / dur)

    def current_index(self, t: float) -> int:
        """Index of the entry being sung (or the next one during an intro)."""
        if not self.entries:
            return -1
        return max(0, bisect.bisect_right(self.act, t) - 1)

    def _activeness(self, j: int, t: float) -> float:
        if not self.style.countdown:
            return 1.0
        if t < self.act[j]:
            return 0.0
        if self.upcoming[j]:
            return min(1.0, (t - self.act[j]) / UPCOMING_FADE) if self.style.animate else 1.0
        return 1.0

    def _part_weights(self, j: int, t: float) -> Optional[tuple]:
        acts = self.part_act[j]
        if len(acts) < 2:
            return None
        if t < acts[0]:
            return tuple(1.0 for _ in acts)
        F = PART_FADE if self.style.animate else 0.0
        out = []
        for k, a in enumerate(acts):
            nxt = acts[k + 1] if k + 1 < len(acts) else math.inf
            if F > 0:
                rise = min(1.0, max(0.0, (t - a) / F))
                fall = min(1.0, max(0.0, (t - nxt) / F))
            else:
                rise = 1.0 if t >= a else 0.0
                fall = 1.0 if t >= nxt else 0.0
            out.append(rise * (1 - fall))
        return tuple(out)

    def countdown_at(self, t: float, p: float) -> int:
        s = self.style
        if not s.countdown or not self.entries:
            return 0
        c = int(round(p))
        if abs(p - c) > 1e-6 or not (0 <= c < len(self.entries)) or not self.upcoming[c]:
            return 0
        remain = self.start[c] - t
        if remain <= 0 or remain > s.countdown_secs:
            return 0
        return int(math.ceil(remain - 1e-9))

    # ------------------------------------------------------------------ layout
    def _side_alpha(self, k: int, K: int) -> float:
        s = self.style
        if k > K:
            return 0.0
        if K <= 1:
            return s.near_opacity
        return _lerp(s.near_opacity, s.far_opacity, (k - 1) / (K - 1))

    def _layout(self, c: int) -> dict:
        cached = self._layout_cache.get(c)
        if cached is not None:
            return cached
        s = self.style
        n = len(self.entries)
        res = {}
        ls = max(0.0, s.line_spacing)
        hc = self.block_h(c, self.Fc)
        res[c] = (self.anchor_y, self.Fc, 1.0, 1.0)
        # upward
        edge = self.anchor_y - hc / 2
        prev = self.Fc
        for k in range(1, self.above + 3):
            j = c - k
            if j < 0:
                break
            h = self.block_h(j, self.Fo)
            edge -= ls * (prev + self.Fo) / 2
            res[j] = (edge - h / 2, self.Fo, self._side_alpha(k, self.above) * s.past_opacity, 0.0)
            edge -= h
            prev = self.Fo
        # downward
        edge = self.anchor_y + hc / 2
        prev = self.Fc
        for k in range(1, self.below + 3):
            j = c + k
            if j >= n:
                break
            h = self.block_h(j, self.Fo)
            edge += ls * (prev + self.Fo) / 2
            res[j] = (edge + h / 2, self.Fo, self._side_alpha(k, self.below), 0.0)
            edge += h
            prev = self.Fo
        if len(self._layout_cache) > 64:
            self._layout_cache.clear()
        self._layout_cache[c] = res
        return res

    def _with_wait_gap(self, L: dict, c: int, t: float) -> dict:
        """While line ``c`` waits for its cue, push the lines above up a little
        so the countdown dots get a clean band of their own."""
        if not (self.style.countdown and self.upcoming[c]) or self.wait_gap <= 0:
            return L
        extra = self.wait_gap * (1.0 - self._activeness(c, t))
        if extra <= 0:
            return L
        return {j: ((v[0] - extra, v[1], v[2], v[3]) if j < c else v) for j, v in L.items()}

    def items(self, t: float) -> tuple[list[Item], float, int]:
        """Draw list for time t, plus the scroll position and countdown value."""
        if not self.entries:
            return [], 0.0, 0
        p = min(max(self.position(t), 0.0), len(self.entries) - 1)
        c0 = int(math.floor(p))
        f = p - c0
        L0 = self._with_wait_gap(self._layout(c0), c0, t)
        if f > 1e-9 and c0 + 1 < len(self.entries):
            L1 = self._with_wait_gap(self._layout(c0 + 1), c0 + 1, t)
            keys = set(L0) | set(L1)
            merged = {}
            for j in keys:
                a = L0.get(j)
                b = L1.get(j)
                if a is None:
                    a = (b[0], b[1], 0.0, b[3])
                if b is None:
                    b = (a[0], a[1], 0.0, a[3])
                merged[j] = tuple(_lerp(a[i], b[i], f) for i in range(4))
        else:
            merged = L0
        u = self.style.upcoming_opacity
        out = []
        for j, (y, size, alpha, cmix) in merged.items():
            if alpha <= 0.002:
                continue
            centre = max(0.0, 1.0 - abs(j - p))
            if centre > 0:
                act = self._activeness(j, t)
                alpha *= 1.0 - centre * (1.0 - act) * (1.0 - u)
            pw = self._part_weights(j, t) if centre > 0 else None
            out.append(Item(j=j, y=y, size=size, alpha=alpha, cmix=cmix, centre=centre, part_w=pw))
        out.sort(key=lambda it: it.alpha)
        return out, p, self.countdown_at(t, p)

    def state_key(self, t: float) -> tuple:
        items, p, cd = self.items(t)
        return (round(p, 4), cd, tuple(
            (it.j, round(it.alpha, 3), None if it.part_w is None else tuple(round(w, 3) for w in it.part_w))
            for it in items))

    # ---------------------------------------------------------------- painting
    def paint(self, painter: QPainter, t: float, draw_bg: bool = True) -> None:
        s = self.style
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        bg = _qcolor(s.bg_color, "#000000")
        if draw_bg:
            painter.fillRect(QRectF(0, 0, self.W, self.H), bg)
        items, p, cd = self.items(t)
        normal = _qcolor(s.text_color)
        cur = _qcolor(s.current_color)
        for it in items:
            self._draw_item(painter, it, normal, cur)
        if cd > 0:
            self._draw_countdown(painter, p, cd, cur)
        if s.edge_fade:
            self._draw_edge_fade(painter, bg)

    def _draw_item(self, painter: QPainter, it: Item, normal: QColor, cur: QColor) -> None:
        s = self.style
        g = self.geo(it.j)
        sc = it.size / REF * g.fit
        col = QColor(
            round(_lerp(normal.red(), cur.red(), it.cmix)),
            round(_lerp(normal.green(), cur.green(), it.cmix)),
            round(_lerp(normal.blue(), cur.blue(), it.cmix)))
        painter.save()
        painter.translate(self.anchor_x, it.y)
        painter.scale(sc, sc)
        outline = s.outline > 0
        ocol = _qcolor(s.outline_color, "#000000")
        for k, path in enumerate(g.part_paths):
            a = it.alpha
            if it.part_w is not None:
                w = it.part_w[k] if k < len(it.part_w) else 1.0
                a *= _lerp(1.0, s.part_dim + (1 - s.part_dim) * w, it.centre)
            self._fill(painter, path, col, a, outline, ocol)
        if g.sep_path is not None and not g.sep_path.isEmpty():
            self._fill(painter, g.sep_path, col, it.alpha * 0.5, outline, ocol)
        painter.restore()

    def _fill(self, painter: QPainter, path: QPainterPath, col: QColor, alpha: float,
              outline: bool, ocol: QColor) -> None:
        if alpha <= 0.002:
            return
        if outline:
            # stroke only outside the glyphs so the outline never overlaps the fill
            # (keeps semi-transparent lines clean)
            width = self.style.outline / 100.0 * REF * 2
            outside = QPainterPath()
            outside.addRect(path.boundingRect().adjusted(-width * 2, -width * 2, width * 2, width * 2))
            outside.addPath(path)
            outside.setFillRule(Qt.FillRule.OddEvenFill)
            oc = QColor(ocol)
            oc.setAlphaF(min(1.0, alpha))
            painter.save()
            painter.setClipPath(outside, Qt.ClipOperation.IntersectClip)
            pen = QPen(oc, width)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.strokePath(path, pen)
            painter.restore()
        c = QColor(col)
        c.setAlphaF(min(1.0, alpha))
        painter.fillPath(path, QBrush(c))

    def _draw_countdown(self, painter: QPainter, p: float, n: int, col: QColor) -> None:
        s = self.style
        c = int(round(p))
        hc = self.block_h(c, self.Fc)
        band = max(0.0, s.line_spacing) * (self.Fc + self.Fo) / 2 + self.wait_gap
        r = max(2.0, min(0.085 * self.Fc, band * 0.3))
        y = self.anchor_y - hc / 2 - band / 2
        step = 0.36 * self.Fc
        n = min(n, s.countdown_secs)
        total = (n - 1) * step
        al = s.align
        x0 = self.anchor_x - total / 2 if al == "center" else (self.anchor_x if al == "left" else self.anchor_x - total)
        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(col))
        for k in range(n):
            painter.drawEllipse(QPointF(x0 + k * step, y), r, r)
        painter.restore()

    def _draw_edge_fade(self, painter: QPainter, bg: QColor) -> None:
        band = self.H * EDGE_FADE
        solid = QColor(bg)
        clear = QColor(bg)
        clear.setAlpha(0)
        g1 = QLinearGradient(0, 0, 0, band)
        g1.setColorAt(0, solid)
        g1.setColorAt(1, clear)
        painter.fillRect(QRectF(0, 0, self.W, band), QBrush(g1))
        g2 = QLinearGradient(0, self.H - band, 0, self.H)
        g2.setColorAt(0, clear)
        g2.setColorAt(1, solid)
        painter.fillRect(QRectF(0, self.H - band, self.W, band), QBrush(g2))

    def render_image(self, t: float, image: Optional[QImage] = None) -> QImage:
        if image is None or image.width() != self.W or image.height() != self.H:
            image = QImage(self.W, self.H, QImage.Format.Format_RGB32)
        painter = QPainter(image)
        self.paint(painter, t)
        painter.end()
        return image
