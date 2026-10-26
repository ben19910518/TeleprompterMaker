"""Lyric files: reading (LRC / SRT / VTT / ASS / plain text), writing, and the
"merge very short lines" pass.

Times are seconds (float). ``LyricLine.text`` may contain ``\\n`` - that is a
multi-row lyric (e.g. original + translation sharing one timestamp) and is
shown as one block.
"""
from __future__ import annotations

import math
import os
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Callable, Optional


# ----------------------------------------------------------------- data model
@dataclass
class LyricLine:
    start: float
    end: Optional[float]
    text: str


@dataclass
class LyricDoc:
    lines: list[LyricLine]
    timed: bool
    fmt: str
    path: str = ""
    meta: dict = field(default_factory=dict)


@dataclass
class Part:
    start: float
    end: Optional[float]
    text: str


@dataclass
class Entry:
    """One displayed lyric block (one source line, or several merged ones)."""
    start: float
    end: Optional[float]
    parts: list[Part]

    @property
    def merged(self) -> bool:
        return len(self.parts) > 1

    def display_text(self, sep: str = " / ") -> str:
        return sep.join(p.text for p in self.parts)


# ------------------------------------------------------------ text decoding
def _decode_score(s: str, enc: str) -> float:
    score = 0.0
    for ch in s:
        o = ord(ch)
        if 0x3040 <= o <= 0x30FF:
            score += 2.0 if enc == "cp932" else 1.0
        elif 0x4E00 <= o <= 0x9FFF:
            score += 1.0
        elif 0x3000 <= o <= 0x303F or 0xFF01 <= o <= 0xFF5E:
            score += 0.5
        elif 0xAC00 <= o <= 0xD7AF:
            score += 1.0 if enc == "cp949" else 0.2
        elif 0xFF61 <= o <= 0xFF9F:
            score -= 2.0
        elif 0xE000 <= o <= 0xF8FF or (o < 32 and ch not in "\r\n\t"):
            score -= 5.0
        elif 0x3400 <= o <= 0x4DBF or o >= 0x20000:
            score -= 1.0
    return score


def read_text(path: str) -> str:
    with open(path, "rb") as fh:
        raw = fh.read()
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:].decode("utf-8", errors="replace")
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return raw.decode("utf-16", errors="replace")
    if len(raw) > 4 and raw[1:2] == b"\x00" and raw[3:4] == b"\x00":
        return raw.decode("utf-16-le", errors="replace")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        pass
    best = None
    for enc in ("gb18030", "cp932", "big5", "cp949"):
        try:
            s = raw.decode(enc)
        except UnicodeDecodeError:
            continue
        sc = _decode_score(s, enc)
        if best is None or sc > best[0]:
            best = (sc, s)
    if best:
        return best[1]
    return raw.decode("latin-1")


# ------------------------------------------------------------------ helpers
_LRC_TIME = re.compile(r"\[(\d{1,3}):(\d{1,2})(?:[.:](\d{1,3}))?\]")
_LRC_META = re.compile(r"^\[([A-Za-z#]+):(.*)\]$")
_LRC_WORD = re.compile(r"<\d{1,3}:\d{1,2}(?:[.:]\d{1,3})?>")
_SRT_TS = r"(?:(\d{1,2}):)?(\d{1,2}):(\d{1,2})[,.](\d{1,3})"
_SRT_ARROW = re.compile(r"^\s*" + _SRT_TS + r"\s*-->\s*" + _SRT_TS)
_TAGS = re.compile(r"<[^>]*>")
_ASS_OVR = re.compile(r"\{[^}]*\}")


def _frac(s: Optional[str]) -> float:
    if not s:
        return 0.0
    return int(s) / (10 ** len(s))


def _clean(text: str) -> str:
    text = _ASS_OVR.sub("", _TAGS.sub("", text))
    return text.replace("\u3000", " ").strip()


def char_units(text: str) -> float:
    """Rough visual length: CJK/kana/hangul = 1, Latin letters/digits = 0.5."""
    u = 0.0
    for ch in text:
        if ch.isspace():
            continue
        cat = unicodedata.category(ch)
        if cat.startswith("P") or cat.startswith("S"):
            continue
        if unicodedata.east_asian_width(ch) in ("W", "F"):
            u += 1.0
        else:
            u += 0.5
    return u


# ------------------------------------------------------------------ parsers
def parse_lrc(text: str, join_same_time: bool = True) -> tuple[list[LyricLine], dict]:
    meta: dict = {}
    items: list[tuple[float, str, int]] = []
    order = 0
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        times = []
        pos = 0
        while True:
            m = _LRC_TIME.match(line, pos)
            if not m:
                break
            times.append(int(m.group(1)) * 60 + int(m.group(2)) + _frac(m.group(3)))
            pos = m.end()
        if not times:
            mm = _LRC_META.match(line)
            if mm:
                meta[mm.group(1).lower()] = mm.group(2).strip()
            continue
        body = _clean(_LRC_WORD.sub("", line[pos:]))
        for t in times:
            items.append((t, body, order))
            order += 1
    offset = 0.0
    if "offset" in meta:
        try:
            offset = float(meta["offset"]) / 1000.0
        except ValueError:
            pass
    items.sort(key=lambda x: (x[0], x[2]))
    lines: list[LyricLine] = []
    for t, body, _ in items:
        t = max(0.0, t - offset)
        if not body:
            if lines and lines[-1].end is None and t > lines[-1].start:
                lines[-1].end = t
            continue
        if lines and abs(lines[-1].start - t) < 1e-3:
            if join_same_time:
                lines[-1].text += "\n" + body
            continue
        if lines and lines[-1].end is not None and lines[-1].end > t:
            lines[-1].end = t
        lines.append(LyricLine(t, None, body))
    return lines, meta


def _srt_time(g: tuple) -> float:
    h = int(g[0]) if g[0] else 0
    return h * 3600 + int(g[1]) * 60 + int(g[2]) + _frac(g[3])


def parse_srt(text: str, join_same_time: bool = True) -> list[LyricLine]:
    """Also handles WebVTT (hour field optional, '.' separator)."""
    raw_lines = text.splitlines()
    cues: list[LyricLine] = []
    i = 0
    n = len(raw_lines)
    while i < n:
        m = _SRT_ARROW.match(raw_lines[i])
        if not m:
            i += 1
            continue
        g = m.groups()
        start, end = _srt_time(g[0:4]), _srt_time(g[4:8])
        i += 1
        body = []
        while i < n and raw_lines[i].strip():
            nxt_is_arrow = i + 1 < n and _SRT_ARROW.match(raw_lines[i + 1])
            if raw_lines[i].strip().isdigit() and nxt_is_arrow:
                break
            if _SRT_ARROW.match(raw_lines[i]):
                break
            c = _clean(raw_lines[i])
            if c:
                body.append(c)
            i += 1
        if body:
            cues.append(LyricLine(start, end if end > start else None, "\n".join(body)))
    cues.sort(key=lambda c: c.start)
    out: list[LyricLine] = []
    for c in cues:
        if out and abs(out[-1].start - c.start) < 1e-3:
            if join_same_time:
                out[-1].text += "\n" + c.text
            continue
        out.append(c)
    return out


def _ass_time(s: str) -> float:
    m = re.match(r"\s*(\d+):(\d{1,2}):(\d{1,2})[.:](\d{1,3})", s)
    if not m:
        return 0.0
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3)) + _frac(m.group(4))


def parse_ass(text: str) -> list[LyricLine]:
    fields = ["layer", "start", "end", "style", "name", "marginl", "marginr", "marginv", "effect", "text"]
    in_events = False
    out = []
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("["):
            in_events = line.lower() == "[events]"
            continue
        if not in_events:
            continue
        if line.lower().startswith("format:"):
            fields = [f.strip().lower() for f in line.split(":", 1)[1].split(",")]
        elif line.lower().startswith("dialogue:"):
            vals = line.split(":", 1)[1].split(",", len(fields) - 1)
            if len(vals) < len(fields):
                continue
            d = dict(zip(fields, vals))
            body = d.get("text", "").replace("\\N", "\n").replace("\\n", "\n").replace("\\h", " ")
            body = "\n".join(x for x in (_clean(r) for r in body.split("\n")) if x)
            if body:
                out.append(LyricLine(_ass_time(d.get("start", "0:00:00.00")), _ass_time(d.get("end", "0:00:00.00")), body))
    out.sort(key=lambda c: c.start)
    for c in out:
        if c.end is not None and c.end <= c.start:
            c.end = None
    return out


def parse_plain(text: str) -> list[str]:
    return [ln.strip().replace("\u3000", " ") for ln in text.splitlines() if ln.strip()]


def load_lyrics(path: str, join_same_time: bool = True) -> LyricDoc:
    text = read_text(path)
    ext = os.path.splitext(path)[1].lower()
    if ext in (".ass", ".ssa"):
        return LyricDoc(parse_ass(text), True, "ass", path)
    n_lrc = len(_LRC_TIME.findall(text))
    n_srt = sum(1 for ln in text.splitlines() if _SRT_ARROW.match(ln))
    if ext in (".srt", ".vtt") or (ext not in (".lrc",) and n_srt >= 2 and n_srt >= n_lrc):
        lines = parse_srt(text, join_same_time)
        if lines:
            return LyricDoc(lines, True, "vtt" if ext == ".vtt" else "srt", path)
    if ext == ".lrc" or n_lrc >= 2:
        lines, meta = parse_lrc(text, join_same_time)
        if lines:
            return LyricDoc(lines, True, "lrc", path, meta)
    plain = parse_plain(text)
    return LyricDoc([LyricLine(float(i) * 3.0, None, t) for i, t in enumerate(plain)], False, "txt", path)


# ------------------------------------------------------------------ writers
def _fmt_lrc(t: float) -> str:
    cs = int(round(max(0.0, t) * 100))
    return f"[{cs // 6000:02d}:{(cs // 100) % 60:02d}.{cs % 100:02d}]"


def _fmt_srt(t: float) -> str:
    ms = int(round(max(0.0, t) * 1000))
    return f"{ms // 3600000:02d}:{(ms // 60000) % 60:02d}:{(ms // 1000) % 60:02d},{ms % 1000:03d}"


def to_lrc(lines: list[LyricLine], meta: Optional[dict] = None) -> str:
    out = []
    for k, v in (meta or {}).items():
        out.append(f"[{k}:{v}]")
    for i, ln in enumerate(lines):
        for row in ln.text.split("\n"):
            out.append(_fmt_lrc(ln.start) + row)
        nxt = lines[i + 1].start if i + 1 < len(lines) else None
        if ln.end is not None and (nxt is None or nxt - ln.end >= 0.005):
            out.append(_fmt_lrc(ln.end))
    return "\n".join(out) + "\n"


def to_srt(lines: list[LyricLine]) -> str:
    out = []
    for i, ln in enumerate(lines):
        nxt = lines[i + 1].start if i + 1 < len(lines) else None
        end = ln.end if ln.end is not None else (nxt if nxt is not None else ln.start + 4.0)
        if nxt is not None and end > nxt:
            end = nxt
        if end <= ln.start:
            end = ln.start + 0.5
        out.append(f"{i + 1}\n{_fmt_srt(ln.start)} --> {_fmt_srt(end)}\n{ln.text}\n")
    return "\n".join(out)


def save_lyrics(lines: list[LyricLine], path: str) -> None:
    text = to_srt(lines) if path.lower().endswith(".srt") else to_lrc(lines)
    with open(path, "w", encoding="utf-8-sig", newline="\r\n") as fh:
        fh.write(text)


# ------------------------------------------------------------------- merging
@dataclass
class MergeOptions:
    enabled: bool = False
    max_units: float = 4.0     # a line this short (or shorter) counts as "short"
    max_gap: float = 1.5       # max silence between the merged lines (s)
    max_parts: int = 4


def _est_duration(text: str) -> float:
    return min(6.0, max(1.0, char_units(text) * 0.38))


def _gap(a: LyricLine, b: LyricLine) -> float:
    end = a.end if a.end is not None else min(b.start, a.start + _est_duration(a.text))
    return b.start - end


def build_entries(lines: list[LyricLine], opts: Optional[MergeOptions] = None,
                  fits: Optional[Callable[[list[str]], bool]] = None) -> list[Entry]:
    """Turn lyric lines into display entries, merging runs of very short lines.

    ``fits(texts)`` must say whether ``texts`` joined with the separator fit on
    ONE row at the current (largest) font size.
    """
    def single(i: int) -> Entry:
        ln = lines[i]
        return Entry(ln.start, ln.end, [Part(ln.start, ln.end, ln.text)])

    n = len(lines)
    if not opts or not opts.enabled or n < 2 or fits is None:
        return [single(i) for i in range(n)]

    multi = ["\n" in ln.text for ln in lines]
    short = [(not multi[i]) and char_units(lines[i].text) <= opts.max_units for i in range(n)]
    link = [(not multi[i]) and (not multi[i + 1]) and _gap(lines[i], lines[i + 1]) <= opts.max_gap
            for i in range(n - 1)]
    texts = [ln.text for ln in lines]

    def ok(idx: list[int]) -> bool:
        return len(idx) <= opts.max_parts and fits([texts[k] for k in idx])

    def width(idx: list[int]) -> float:
        return sum(char_units(texts[k]) for k in idx) + 1.2 * (len(idx) - 1)

    def partition(run: list[int]) -> list[list[int]]:
        m = len(run)
        inf = (math.inf, math.inf)
        best = [inf] * (m + 1)
        prev = [0] * (m + 1)
        best[0] = (0, 0.0)
        for b in range(1, m + 1):
            for a in range(b - 1, -1, -1):
                seg = run[a:b]
                if len(seg) > 1 and not ok(seg):
                    break
                if best[a] == inf:
                    continue
                cand = (best[a][0] + 1, max(best[a][1], width(seg)))
                if cand < best[b]:
                    best[b] = cand
                    prev[b] = a
        out = []
        b = m
        while b > 0:
            a = prev[b]
            out.append(run[a:b])
            b = a
        return out[::-1]

    groups: list[list[int]] = []
    i = 0
    while i < n:
        if short[i]:
            j = i
            while j + 1 < n and short[j + 1] and link[j]:
                j += 1
            run = list(range(i, j + 1))
            groups.extend(partition(run) if len(run) > 1 else [run])
            i = j + 1
        else:
            groups.append([i])
            i += 1

    # an isolated short line joins the neighbour it is sung closest to
    out: list[list[int]] = []
    k = 0
    while k < len(groups):
        g = groups[k]
        if len(g) == 1 and short[g[0]]:
            i0 = g[0]
            cands = []
            if out and i0 - 1 == out[-1][-1] and link[i0 - 1] and ok(out[-1] + g):
                cands.append((_gap(lines[i0 - 1], lines[i0]), "prev"))
            if k + 1 < len(groups) and i0 + 1 == groups[k + 1][0] and link[i0] and ok(g + groups[k + 1]):
                cands.append((_gap(lines[i0], lines[i0 + 1]), "next"))
            if cands:
                cands.sort()
                if cands[0][1] == "prev":
                    out[-1] = out[-1] + g
                else:
                    groups[k + 1] = g + groups[k + 1]
                k += 1
                continue
        out.append(g)
        k += 1

    entries = []
    for g in out:
        parts = [Part(lines[x].start, lines[x].end, lines[x].text) for x in g]
        last = lines[g[-1]]
        entries.append(Entry(parts[0].start, last.end, parts))
    return entries
