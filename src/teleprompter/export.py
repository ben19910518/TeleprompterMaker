"""Video export: renders only the frames that differ, encodes H.264 in
constant-QP mode through PyAV (bundled FFmpeg), muxes the song as AAC.

A teleprompter video is static most of the time, so identical frames are
rendered and colour-converted once and simply re-submitted to the encoder
with a new timestamp; x264 turns those into near-empty skip frames.
"""
from __future__ import annotations
from teleprompter.i18n import tr

import math
import os
import time
from dataclasses import dataclass
from fractions import Fraction
from typing import Callable, Optional

import av
import av.video.reformatter as R
import numpy as np
from PySide6.QtGui import QImage, QPainter

from .lyrics import LyricLine
from .media import decode_audio, probe
from .render import Renderer
from .style import Style

ENCODERS = {
    "libx264": tr('x264（CPU，兼容性最好）'),
    "h264_nvenc": tr('NVIDIA NVENC（显卡加速）'),
    "h264_amf": tr('AMD AMF（显卡加速）'),
    "h264_qsv": tr('Intel QSV（核显加速）'),
}
PRESETS_X264 = ["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower"]


class ExportCancelled(Exception):
    pass


@dataclass
class ExportResult:
    path: str
    frames: int
    unique_frames: int
    seconds: float
    size: int
    duration: float


def _video_options(style: Style, encoder: str) -> dict:
    qp = str(int(min(51, max(0, style.qp))))
    if encoder == "libx264":
        # no lookahead / scene-cut analysis: identical frames are the norm here
        # and these passes cost ~30% of the encode time for nothing
        return {"qp": qp, "preset": style.preset if style.preset in PRESETS_X264 else "veryfast",
                "tune": "stillimage", "x264-params": "rc-lookahead=0:b-adapt=0:scenecut=0"}
    if encoder == "h264_nvenc":
        return {"rc": "constqp", "qp": qp, "preset": "p5", "tune": "hq"}
    if encoder == "h264_amf":
        return {"rc": "cqp", "qp_i": qp, "qp_p": qp, "qp_b": qp, "quality": "quality"}
    if encoder == "h264_qsv":
        return {"preset": "medium"}
    return {}


def _setup_video_stream(out, style: Style, encoder: str, fps: Fraction):
    vs = out.add_stream(encoder, rate=fps)
    vs.width = int(style.width)
    vs.height = int(style.height)
    vs.pix_fmt = "nv12" if encoder == "h264_qsv" else "yuv420p"
    cc = vs.codec_context
    cc.time_base = 1 / fps
    cc.gop_size = max(1, int(round(float(fps) * max(0.5, style.keyint))))
    cc.color_primaries = 1   # BT.709
    cc.color_trc = 1
    cc.colorspace = 1
    cc.color_range = 1       # limited / tv
    if encoder == "h264_qsv":
        cc.qscale = True
        cc.global_quality = int(style.qp) * 118  # FF_QP2LAMBDA
    vs.options = _video_options(style, encoder)
    return vs


_ENCODER_CHECK: dict[str, bool] = {}


def encoder_available(name: str) -> bool:
    """Try a real 64x64 encode - a codec can be compiled in but have no GPU/driver."""
    if name in _ENCODER_CHECK:
        return _ENCODER_CHECK[name]
    ok = False
    try:
        import io
        buf = io.BytesIO()
        out = av.open(buf, "w", format="mp4")
        st = Style(width=256, height=144, fps=30)
        vs = _setup_video_stream(out, st, name, Fraction(30))
        fr = av.VideoFrame.from_ndarray(np.zeros((144, 256, 3), np.uint8), format="rgb24").reformat(format=vs.pix_fmt)
        n = 0
        for k in range(3):
            fr.pts = k
            for pkt in vs.encode(fr):
                out.mux(pkt)
                n += 1
        for pkt in vs.encode(None):
            out.mux(pkt)
            n += 1
        out.close()
        ok = n > 0
    except Exception:
        ok = False
    _ENCODER_CHECK[name] = ok
    return ok


def plan_frames(renderer: Renderer, n_frames: int, fps: Fraction,
                cancelled: Callable[[], bool] = lambda: False) -> list[tuple[int, int]]:
    """Group consecutive identical frames: [(first_frame, end_frame_exclusive), ...]."""
    runs: list[list[int]] = []
    prev = None
    fpsf = float(fps)
    for k in range(n_frames):
        if k % 2000 == 0 and cancelled():
            raise ExportCancelled()
        key = renderer.state_key(k / fpsf)
        if key != prev:
            runs.append([k, k + 1])
            prev = key
        else:
            runs[-1][1] = k + 1
    return [(a, b) for a, b in runs]


def export_video(style: Style, lines: list[LyricLine], audio_path: str, out_path: str,
                 progress: Optional[Callable[[float, str], None]] = None,
                 cancelled: Callable[[], bool] = lambda: False) -> ExportResult:
    t_start = time.time()
    say = progress or (lambda f, m: None)
    fps = Fraction(style.fps_arg())
    info = probe(audio_path)
    duration = info.duration
    if duration <= 0:
        raise ValueError(tr('无法读取音频时长'))
    n_frames = max(1, int(math.ceil(duration * fps - 1e-6)))

    say(0.0, tr('正在分析画面…'))
    renderer = Renderer(style, lines)
    runs = plan_frames(renderer, n_frames, fps, cancelled)

    pcm = None
    if style.audio_bitrate > 0:
        say(0.0, tr('正在读取音频…'))
        pcm = decode_audio(audio_path, 48000, 2, cancelled=cancelled)

    encoder = style.encoder if style.encoder in ENCODERS else "libx264"
    if encoder != "libx264" and not encoder_available(encoder):
        encoder = "libx264"

    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    tmp_path = out_path + ".part" + os.path.splitext(out_path)[1]
    fmt = {".mp4": "mp4", ".mov": "mov", ".mkv": "matroska"}.get(os.path.splitext(out_path)[1].lower(), "mp4")
    options = {"movflags": "faststart"} if fmt in ("mp4", "mov") else {}
    out = av.open(tmp_path, "w", format=fmt, options=options)
    ok = False
    try:
        out.metadata["comment"] = "Teleprompter video"
        vs = _setup_video_stream(out, style, encoder, fps)
        a_st = None
        if pcm is not None and len(pcm):
            a_st = out.add_stream("aac", rate=48000)
            a_st.codec_context.layout = "stereo"
            a_st.codec_context.bit_rate = int(style.audio_bitrate) * 1000
        a_pos = 0
        a_total = len(pcm) if pcm is not None else 0
        A_CHUNK = 4800

        def feed_audio(until_sample: int):
            nonlocal a_pos
            if a_st is None:
                return
            until_sample = min(until_sample, a_total)
            while a_pos < until_sample:
                n = min(A_CHUNK, until_sample - a_pos)
                chunk = np.ascontiguousarray(pcm[a_pos:a_pos + n].T)
                af = av.AudioFrame.from_ndarray(chunk, format="fltp", layout="stereo")
                af.sample_rate = 48000
                af.pts = a_pos
                for pkt in a_st.encode(af):
                    out.mux(pkt)
                a_pos += n

        W, H = int(style.width), int(style.height)
        img = QImage(W, H, QImage.Format.Format_RGB32)
        fpsf = float(fps)
        last_say = 0.0
        for ri, (k0, k1) in enumerate(runs):
            if cancelled():
                raise ExportCancelled()
            painter = QPainter(img)
            renderer.paint(painter, k0 / fpsf)
            painter.end()
            arr = np.frombuffer(img.constBits(), np.uint8).reshape(H, img.bytesPerLine() // 4, 4)[:, :W, :]
            vf = av.VideoFrame.from_ndarray(np.ascontiguousarray(arr), format="bgra")
            yuv = vf.reformat(format=vs.pix_fmt, dst_colorspace=R.Colorspace.ITU709,
                              dst_color_range=R.ColorRange.MPEG)
            for k in range(k0, k1):
                yuv.pts = k
                for pkt in vs.encode(yuv):
                    out.mux(pkt)
                if a_st is not None and (k % 15 == 0 or k == k1 - 1):
                    feed_audio(int((k + 1) / fpsf * 48000))
                if k % 30 == 0 and cancelled():
                    raise ExportCancelled()
            now = time.time()
            if now - last_say > 0.15:
                last_say = now
                say(k1 / n_frames, tr('正在生成视频… {p0}/{p1} 帧', p0=k1, p1=n_frames))
        for pkt in vs.encode(None):
            out.mux(pkt)
        if a_st is not None:
            feed_audio(a_total)
            for pkt in a_st.encode(None):
                out.mux(pkt)
        ok = True
    finally:
        out.close()
        if not ok:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
    if os.path.exists(out_path):
        os.remove(out_path)
    os.replace(tmp_path, out_path)
    say(1.0, tr('完成'))
    return ExportResult(out_path, n_frames, len(runs), time.time() - t_start,
                        os.path.getsize(out_path), duration)
