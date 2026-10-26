"""Audio probing/decoding through PyAV (bundled FFmpeg libraries)."""
from __future__ import annotations
from teleprompter.i18n import tr

from dataclasses import dataclass
from typing import Callable, Optional

import av
import numpy as np

AUDIO_EXTS = "*.mp3 *.wav *.flac *.m4a *.aac *.ogg *.opus *.wma *.ape *.aiff *.aif *.mp4 *.mkv *.mov *.webm"


@dataclass
class AudioInfo:
    path: str
    duration: float
    sample_rate: int
    channels: int
    codec: str


class DecodeCancelled(Exception):
    pass


def probe(path: str) -> AudioInfo:
    with av.open(path) as c:
        if not c.streams.audio:
            raise ValueError(tr('该文件中没有音频轨道'))
        st = c.streams.audio[0]
        dur = 0.0
        if st.duration is not None and st.time_base is not None:
            dur = float(st.duration * st.time_base)
        if dur <= 0 and c.duration:
            dur = c.duration / 1_000_000
        if dur <= 0:  # no header duration (some raw streams): decode to find out
            last = 0.0
            for fr in c.decode(st):
                if fr.time is not None:
                    last = fr.time + fr.samples / (fr.sample_rate or 1)
            dur = last
        cc = st.codec_context
        return AudioInfo(path, dur, cc.sample_rate or 0, cc.channels if hasattr(cc, "channels") else 2,
                         cc.name or "")


def decode_audio(path: str, sr: int = 48000, channels: int = 2,
                 progress: Optional[Callable[[float], None]] = None,
                 cancelled: Callable[[], bool] = lambda: False) -> np.ndarray:
    """Decode to float32 array of shape (samples, channels)."""
    layout = "mono" if channels == 1 else "stereo"
    chunks = []
    with av.open(path) as c:
        st = c.streams.audio[0]
        total = float(st.duration * st.time_base) if st.duration and st.time_base else (c.duration or 0) / 1e6
        rs = av.AudioResampler(format="flt", layout=layout, rate=sr)
        n = 0
        for fr in c.decode(st):
            if cancelled():
                raise DecodeCancelled()
            for o in rs.resample(fr):
                chunks.append(o.to_ndarray().reshape(-1, channels))
            n += 1
            if progress and total and n % 200 == 0 and fr.time is not None:
                progress(min(1.0, fr.time / total))
        for o in rs.resample(None):
            chunks.append(o.to_ndarray().reshape(-1, channels))
    if not chunks:
        return np.zeros((0, channels), np.float32)
    return np.ascontiguousarray(np.concatenate(chunks).astype(np.float32, copy=False))


def peaks(data: np.ndarray, sr: int, per_sec: int = 100) -> np.ndarray:
    """Peak envelope (0..1), ``per_sec`` values per second, mono."""
    if data.size == 0:
        return np.zeros(0, np.float32)
    mono = np.abs(data).max(axis=1) if data.ndim == 2 else np.abs(data)
    hop = max(1, sr // per_sec)
    n = len(mono) // hop
    env = mono[: n * hop].reshape(n, hop).max(axis=1)
    m = float(env.max()) or 1.0
    return (env / m).astype(np.float32)
