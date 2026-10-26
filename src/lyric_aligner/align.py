"""Automatic timeline: audio + plain lyric lines -> start/end time per line.

1. faster-whisper (Whisper large-v3-turbo, int8 on CPU) transcribes the song
   with word timestamps; the user's lyrics are given as a prompt so the model
   leans towards the right characters.
2. The recognised characters are aligned to the user's lyric characters with
   a global dynamic-programming alignment that tolerates homophones
   (pinyin), simplified/traditional variants, missing and extra words.
3. Every lyric line takes its time from the characters that matched; lines
   that could not be heard are re-recognised once with only their own text as
   the prompt, and anything still missing is interpolated and flagged.
"""
from __future__ import annotations
from teleprompter.i18n import tr

import difflib
import math
import os
import unicodedata
from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np

from . import modelhub
from .media import decode_audio

SR = 16000
LANGUAGES = {"自动检测": None, "中文": "zh", "粤语": "yue", "日语": "ja", "英语": "en", "韩语": "ko"}


class AlignCancelled(Exception):
    pass


@dataclass
class Word:
    start: float
    end: float
    text: str
    prob: float


@dataclass
class AlignedLine:
    text: str
    start: float
    end: float
    score: float          # 0..1: how much of the line was actually heard
    interpolated: bool = False


# --------------------------------------------------------------- tokenising
def _is_cjk(ch: str) -> bool:
    o = ord(ch)
    return (0x4E00 <= o <= 0x9FFF or 0x3400 <= o <= 0x4DBF or 0x3040 <= o <= 0x30FF
            or 0xAC00 <= o <= 0xD7AF or 0xF900 <= o <= 0xFAFF or 0x20000 <= o <= 0x2FFFF)


def tokenize(text: str) -> list[str]:
    """CJK/kana/hangul: one token per character. Latin/digits: one per word."""
    out, buf = [], []
    for ch in unicodedata.normalize("NFKC", text):
        if _is_cjk(ch):
            if buf:
                out.append("".join(buf).lower())
                buf = []
            out.append(ch)
        elif ch.isalnum() or ch == "'":
            buf.append(ch)
        else:
            if buf:
                out.append("".join(buf).lower())
                buf = []
    if buf:
        out.append("".join(buf).lower())
    return [t.strip("'") for t in out if t.strip("'")]


_PY_CACHE: dict[str, str] = {}


def _pinyin(ch: str) -> str:
    v = _PY_CACHE.get(ch)
    if v is None:
        v = ""
        o = ord(ch)
        if 0x3040 <= o <= 0x30FF:          # kana: fold katakana onto hiragana
            v = "kana:" + (chr(o - 0x60) if 0x30A1 <= o <= 0x30F6 else ch)
        elif _is_cjk(ch):
            try:
                from pypinyin import Style, lazy_pinyin
                p = lazy_pinyin(ch, style=Style.NORMAL, errors="ignore")
                v = p[0] if p else ""
            except Exception:
                v = ""
        _PY_CACHE[ch] = v
    return v


def _fuzzy(py: str) -> str:
    if not py or py.startswith("kana:"):
        return py
    for a, b in (("zh", "z"), ("ch", "c"), ("sh", "s")):
        if py.startswith(a):
            py = b + py[len(a):]
            break
    if py.startswith("n"):
        py = "l" + py[1:]
    for a, b in (("ing", "in"), ("eng", "en"), ("ang", "an")):
        if py.endswith(a):
            py = py[: -len(a)] + b
            break
    return py


# ---------------------------------------------------------------- alignment
GAP_LYRIC = -0.45     # lyric token not heard
GAP_HEARD = -0.30     # heard token not in the lyrics
ONSET_BIAS = 0.10     # seconds added to recognised line starts


def _sim_matrix_rows(L: list[str], Rt: list[str]):
    """Yields similarity rows (numpy) for each lyric token against all heard tokens."""
    vocab: dict[str, int] = {}

    def vid(s: str) -> int:
        return vocab.setdefault(s, len(vocab))

    r_id = np.array([vid(t) for t in Rt], np.int64)
    r_py = np.array([vid("py:" + _pinyin(t)) if len(t) == 1 and _pinyin(t) else -1 for t in Rt], np.int64)
    r_fz = np.array([vid("fz:" + _fuzzy(_pinyin(t))) if len(t) == 1 and _pinyin(t) else -2 for t in Rt], np.int64)
    latin_idx = [j for j, t in enumerate(Rt) if not _is_cjk(t[0])]
    for t in L:
        row = np.where(r_id == vid(t), 1.0, 0.0)
        if len(t) == 1 and _is_cjk(t):
            py = _pinyin(t)
            if py:
                row = np.maximum(row, np.where(r_py == vid("py:" + py), 0.85, 0.0))
                row = np.maximum(row, np.where(r_fz == vid("fz:" + _fuzzy(py)), 0.55, 0.0))
        elif latin_idx:
            for j in latin_idx:
                if row[j] < 1.0:
                    r = difflib.SequenceMatcher(None, t, Rt[j]).ratio()
                    if r >= 0.6:
                        row[j] = max(row[j], r * 0.9)
        yield row


def align_tokens(L: list[str], Rt: list[str]) -> list[tuple[int, int, float]]:
    """Global alignment, free leading/trailing heard tokens.

    Returns [(lyric_index, heard_index, similarity)] for matched pairs.
    """
    n, m = len(L), len(Rt)
    if n == 0 or m == 0:
        return []
    S_prev = np.zeros(m + 1)                  # row 0: heard tokens before the lyrics are free
    back = np.zeros((n + 1, m + 1), np.uint8)  # 1 diag, 2 up (skip lyric), 3 left (skip heard)
    sims = []
    idx = np.arange(m + 1, dtype=np.float64)
    for i, row in enumerate(_sim_matrix_rows(L, Rt), start=1):
        sims.append(row)
        match = np.where(row > 0, 2.0 * row - 1.0, -1.0)
        diag = np.full(m + 1, -np.inf)
        diag[1:] = S_prev[:-1] + match
        up = S_prev + GAP_LYRIC
        cand = np.maximum(diag, up)
        # left chain: S[j] = max_k<=j cand[k] + GAP_HEARD*(j-k)
        acc = np.maximum.accumulate(cand - GAP_HEARD * idx) + GAP_HEARD * idx
        S = np.maximum(cand, acc)
        b = np.where(cand >= acc - 1e-9, np.where(diag >= up, 1, 2), 3).astype(np.uint8)
        b[0] = 2
        back[i] = b
        S_prev = S
    j = int(np.argmax(S_prev))
    i = n
    pairs = []
    while i > 0 and j >= 0:
        b = back[i, j]
        if b == 1:
            s = sims[i - 1][j - 1]
            if s > 0:
                pairs.append((i - 1, j - 1, float(s)))
            i -= 1
            j -= 1
        elif b == 2:
            i -= 1
        else:
            j -= 1
    return pairs[::-1]


def _words_to_tokens(words: list[Word]) -> tuple[list[str], list[tuple[float, float]]]:
    toks, times = [], []
    for w in words:
        tt = tokenize(w.text)
        if not tt:
            continue
        span = max(0.0, w.end - w.start)
        for k, t in enumerate(tt):
            a = w.start + span * k / len(tt)
            toks.append(t)
            times.append((a, w.start + span * (k + 1) / len(tt)))
    return toks, times


def lines_from_alignment(lines: list[str], words: list[Word], duration: float) -> list[AlignedLine]:
    line_toks = [tokenize(t) for t in lines]
    L, owner, pos = [], [], []
    for li, tt in enumerate(line_toks):
        for k, t in enumerate(tt):
            L.append(t)
            owner.append(li)
            pos.append(k)
    Rt, Rtime = _words_to_tokens(words)
    pairs = align_tokens(L, Rt)

    per_line: list[list[tuple[int, float, float, float]]] = [[] for _ in lines]
    for li_tok, rj, s in pairs:
        if s >= 0.5:
            per_line[owner[li_tok]].append((pos[li_tok], Rtime[rj][0], Rtime[rj][1], s))

    durs = [b - a for _, a, b, _ in (x for pl in per_line for x in pl) if b > a]
    char_d = float(np.clip(np.median(durs), 0.12, 0.6)) if durs else 0.3

    out: list[AlignedLine] = []
    for li, text in enumerate(lines):
        n_tok = max(1, len(line_toks[li]))
        pl = per_line[li]
        score = min(1.0, sum(x[3] for x in pl) / n_tok)
        if pl and score >= 0.2:
            first, last = pl[0], pl[-1]
            # Whisper tends to stretch the first word of a phrase back into the
            # preceding silence (and the last one forward): trust the far edge
            f_start = first[1]
            if first[2] - first[1] > 2.2 * char_d:
                f_start = first[2] - 1.3 * char_d
            l_end = last[2]
            if last[2] - last[1] > 2.5 * char_d:
                l_end = last[1] + 1.5 * char_d
            start = f_start - min(1.5, first[0] * char_d)
            # DTW word onsets come out a little early on sung material
            start = min(start + ONSET_BIAS, first[2])
            end = l_end + min(2.0, (n_tok - 1 - last[0]) * char_d)
            # a line cannot plausibly last much longer than its syllables need
            end = min(end, max(start, 0.0) + n_tok * char_d * 2.2 + 1.0)
            out.append(AlignedLine(text, max(0.0, start), end, score))
        else:
            out.append(AlignedLine(text, math.nan, math.nan, score, True))
    _fill_and_fix(out, line_toks, duration)
    return out


def _fill_and_fix(out: list[AlignedLine], line_toks: list[list[str]], duration: float) -> None:
    n = len(out)
    # drop anchors that break the order (keep the longest increasing chain)
    known = [i for i in range(n) if not out[i].interpolated]
    if known:
        best_len = [1] * len(known)
        prev = [-1] * len(known)
        for a in range(len(known)):
            for b in range(a):
                if out[known[b]].start < out[known[a]].start and best_len[b] + 1 > best_len[a]:
                    best_len[a] = best_len[b] + 1
                    prev[a] = b
        k = int(np.argmax(best_len))
        keep = set()
        while k >= 0:
            keep.add(known[k])
            k = prev[k]
        for i in known:
            if i not in keep:
                out[i].interpolated = True
                out[i].start = out[i].end = math.nan
    # interpolate unknown runs proportionally to their length
    i = 0
    while i < n:
        if not out[i].interpolated:
            i += 1
            continue
        j = i
        while j < n and out[j].interpolated:
            j += 1
        left = out[i - 1].end if i > 0 else 0.0
        right = out[j].start if j < n else max(duration, left + 1.0)
        if right <= left:
            right = left + 0.3 * (j - i)
        weights = [max(1, len(line_toks[k])) for k in range(i, j)]
        tot = float(sum(weights))
        t = left
        for k, wgt in zip(range(i, j), weights):
            span = (right - left) * wgt / tot
            out[k].start = t
            out[k].end = t + span
            t += span
        i = j
    # monotonic, non-overlapping
    for k in range(n):
        if k > 0 and out[k].start < out[k - 1].start + 0.05:
            out[k].start = out[k - 1].start + 0.05
        if out[k].end <= out[k].start:
            out[k].end = out[k].start + 0.3
    for k in range(n - 1):
        if out[k].end > out[k + 1].start:
            out[k].end = out[k + 1].start


# ------------------------------------------------------------ recognition
_MODEL_CACHE: dict = {}
DEVICE_USED = {"name": "cpu"}


def _add_cuda_dirs() -> None:
    """Let CUDA 12 runtime DLLs (cublas/cudnn) be found: <app>/cuda or the CUDA toolkit."""
    from .paths import app_dir
    cands = [os.path.join(app_dir(), "cuda")]
    if os.environ.get("CUDA_PATH"):
        cands.append(os.path.join(os.environ["CUDA_PATH"], "bin"))
    for d in cands:
        if os.path.isdir(d):
            try:
                os.add_dll_directory(d)
            except (OSError, AttributeError):
                pass
            os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")


def load_model(key: str, device: str = "auto"):
    """Whisper model, on the NVIDIA GPU when its CUDA libraries are usable, else int8 on CPU."""
    from faster_whisper import WhisperModel
    path = modelhub.model_path(key)
    for (k, dev), m in list(_MODEL_CACHE.items()):
        if k == key and (device == "auto" or dev == device):
            DEVICE_USED["name"] = dev
            return m
    _MODEL_CACHE.clear()
    if device in ("auto", "cuda"):
        try:
            import ctranslate2
            if ctranslate2.get_cuda_device_count() > 0:
                _add_cuda_dirs()
                m = WhisperModel(path, device="cuda", compute_type="float16", local_files_only=True)
                segs, _ = m.transcribe(np.zeros(SR * 2, np.float32), language="en", beam_size=1)
                list(segs)            # forces a real encode: fails here if cuBLAS/cuDNN are missing
                _MODEL_CACHE[(key, "cuda")] = m
                DEVICE_USED["name"] = "cuda"
                return m
        except Exception:
            pass
    threads = max(2, (os.cpu_count() or 4) // 2)
    m = WhisperModel(path, device="cpu", compute_type="int8", cpu_threads=threads, local_files_only=True)
    _MODEL_CACHE[(key, "cpu")] = m
    DEVICE_USED["name"] = "cpu"
    return m


def _prompt_from(lines: list[str], limit: int = 120) -> str:
    out, n = [], 0
    for ln in lines:
        s = " ".join(ln.split())
        if n + len(s) > limit:
            break
        out.append(s)
        n += len(s) + 1
    return "，".join(out)


def transcribe(model, audio: np.ndarray, language: Optional[str], prompt: str,
               progress: Callable[[float], None], cancelled: Callable[[], bool],
               offset: float = 0.0, beam_size: int = 5,
               max_new_tokens: Optional[int] = None) -> tuple[list[Word], str]:
    segments, info = model.transcribe(
        audio, language=language, beam_size=beam_size, word_timestamps=True,
        condition_on_previous_text=False, initial_prompt=prompt or None,
        vad_filter=False, no_speech_threshold=0.75, compression_ratio_threshold=2.6,
        max_new_tokens=max_new_tokens)
    dur = len(audio) / SR
    words: list[Word] = []
    for seg in segments:
        if cancelled():
            raise AlignCancelled()
        for w in seg.words or []:
            words.append(Word(w.start + offset, w.end + offset, w.word, w.probability))
        progress(min(1.0, seg.end / dur) if dur else 1.0)
    return words, info.language


def auto_align(audio_path: str, lines: list[str], model_key: str = modelhub.DEFAULT_MODEL,
               language: Optional[str] = None, refine: bool = True,
               progress: Optional[Callable[[float, str], None]] = None,
               cancelled: Callable[[], bool] = lambda: False,
               trace: Optional[dict] = None) -> list[AlignedLine]:
    say = progress or (lambda f, m: None)
    lines = [ln for ln in (" ".join(x.split()) for x in lines) if ln]
    if not lines:
        raise ValueError(tr('歌词为空'))
    if not modelhub.is_installed(model_key):
        raise FileNotFoundError(tr('识别模型还没有下载'))
    say(0.0, tr('正在读取音频…'))
    audio = decode_audio(audio_path, SR, 1, cancelled=cancelled)[:, 0].copy()
    duration = len(audio) / SR
    say(0.02, tr('正在加载识别模型（首次约需 10 秒）…'))
    model = load_model(model_key, "auto")
    if cancelled():
        raise AlignCancelled()
    dev = tr('显卡加速') if DEVICE_USED["name"] == "cuda" else tr('CPU，一首歌约 1~2 分钟')
    say(0.05, tr('正在识别歌声（{p0}）…', p0=dev))
    words, lang = transcribe(model, audio, language, _prompt_from(lines),
                             lambda f: say(0.05 + 0.75 * f, tr('正在识别歌声（{p0}）… {p1}%', p0=dev, p1=int(f * 100))), cancelled)
    say(0.82, tr('正在对齐歌词…'))
    result = lines_from_alignment(lines, words, duration)

    if refine:
        runs = _missing_runs(result)
        for ri, (i, j) in enumerate(runs):
            if cancelled():
                raise AlignCancelled()
            say(0.82 + 0.16 * ri / max(1, len(runs)), tr('正在补充识别漏掉的句子… {p0}/{p1}', p0=ri + 1, p1=len(runs)))
            a = result[i - 1].end if i > 0 else 0.0
            b = result[j].start if j < len(result) else duration
            a, b = max(0.0, a - 0.3), min(duration, b + 0.3)
            n_tok = sum(len(tokenize(t)) for t in lines[i:j])
            # too little audio to have sung these lines (e.g. title/credit lines
            # at the top of a lyric sheet): leave them interpolated
            if b - a < 1.5 or b - a < 0.12 * n_tok:
                continue
            seg = audio[int(a * SR):int(b * SR)]
            w2, _ = transcribe(model, seg, language or lang, _prompt_from(lines[i:j], 200),
                               lambda f: None, cancelled, offset=a, beam_size=1,
                               max_new_tokens=min(220, 3 * n_tok + 20))
            if not w2:
                continue
            words = [w for w in words if w.end <= a or w.start >= b] + w2
            words.sort(key=lambda w: w.start)
        if runs:
            result = lines_from_alignment(lines, words, duration)
    if trace is not None:
        trace.update(words=[w.__dict__ for w in words],language=lang,duration=duration)
        tokens,times=_words_to_tokens(words)
        lyric_tokens=[];owners=[]
        for index,line in enumerate(lines):
            current=tokenize(line);lyric_tokens.extend(current);owners.extend([index]*len(current))
        pairs=align_tokens(lyric_tokens,tokens)
        trace['tokens']=[dict(line=owners[i],text=lyric_tokens[i],start=times[j][0],end=times[j][1],score=score) for i,j,score in pairs if score>=.5]
    say(1.0, tr('完成'))
    return result


def _missing_runs(result: list[AlignedLine]) -> list[tuple[int, int]]:
    runs = []
    i = 0
    n = len(result)
    while i < n:
        if result[i].interpolated or result[i].score < 0.35:
            j = i
            while j < n and (result[j].interpolated or result[j].score < 0.35):
                j += 1
            runs.append((i, j))
            i = j
        else:
            i += 1
    return runs
