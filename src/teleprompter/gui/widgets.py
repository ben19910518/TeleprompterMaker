"""Reusable widgets: colour button, slider+spinbox, live preview, waveform timeline."""
from __future__ import annotations
from ..i18n import tr
from .i18n_widgets import QDoubleSpinBox, QLabel, QPushButton

import math
from typing import Optional

import numpy as np
from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QColorDialog, QFrame, QHBoxLayout, QSizePolicy, QSlider, QVBoxLayout, QWidget)

from ..render import Renderer


def card(title=None, heading=True):
    """A rounded surface with an optional heading; returns (frame, body layout, heading row)."""
    frame = QFrame()
    frame.setObjectName("card")
    body = QVBoxLayout(frame)
    body.setContentsMargins(14, 12, 14, 12)
    body.setSpacing(8)
    head = QHBoxLayout()
    head.setSpacing(6)
    if title is not None:
        label = QLabel(title)
        label.setObjectName("cardTitle")
        head.addWidget(label)
    head.addStretch(1)
    if heading:
        body.addLayout(head)
    return frame, body, head


def fmt_time(t: float, cs: bool = True) -> str:
    if t is None or not math.isfinite(t):
        return "--:--"
    t = max(0.0, t)
    m = int(t // 60)
    s = t - m * 60
    return tr('{p0:02d}:{p1:05.2f}', p0=m, p1=s) if cs else tr('{p0:02d}:{p1:02d}', p0=m, p1=int(s))


def parse_time(text: str) -> Optional[float]:
    text = text.strip().replace("：", ":").replace(",", ".")
    try:
        if ":" in text:
            parts = text.split(":")
            v = 0.0
            for p in parts:
                v = v * 60 + float(p)
            return v
        return float(text)
    except ValueError:
        return None


class ColorButton(QPushButton):
    colorChanged = Signal(str)

    def __init__(self, color: str = "#FFFFFF", parent=None):
        super().__init__(parent)
        self._color = QColor(color)
        self.setFixedSize(QSize(46, 24))
        self.clicked.connect(self._pick)
        self.setToolTip(tr('点击选择颜色'))

    def color(self) -> str:
        return self._color.name().upper()

    def setColor(self, c: str) -> None:
        q = QColor(c)
        if q.isValid() and q != self._color:
            self._color = q
            self.update()

    def _pick(self):
        c = QColorDialog.getColor(self._color, self, tr('选择颜色'))
        if c.isValid():
            self._color = c
            self.update()
            self.colorChanged.emit(self.color())

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        r = self.rect().adjusted(5, 5, -5, -5)
        p.setPen(QPen(QColor("#888"), 1))
        p.setBrush(self._color)
        p.drawRoundedRect(r, 3, 3)


class SliderSpin(QWidget):
    """Slider and spin box kept in sync; emits a float."""
    valueChanged = Signal(float)

    def __init__(self, lo: float, hi: float, step: float = 1.0, decimals: int = 0,
                 suffix: str = "", value: float = 0.0, parent=None):
        super().__init__(parent)
        self._k = 10 ** decimals
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(int(round(lo * self._k)), int(round(hi * self._k)))
        self.slider.setSingleStep(max(1, int(round(step * self._k))))
        self.spin = QDoubleSpinBox()
        self.spin.setRange(lo, hi)
        self.spin.setDecimals(decimals)
        self.spin.setSingleStep(step)
        self.spin.setSuffix(suffix)
        self.spin.setFixedWidth(84)
        self.spin.setKeyboardTracking(False)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.slider, 1)
        lay.addWidget(self.spin)
        self.slider.valueChanged.connect(self._from_slider)
        self.spin.valueChanged.connect(self._from_spin)
        self.setValue(value)

    def value(self) -> float:
        return float(self.spin.value())

    def setValue(self, v: float) -> None:
        self.spin.blockSignals(True)
        self.slider.blockSignals(True)
        self.spin.setValue(v)
        self.slider.setValue(int(round(v * self._k)))
        self.spin.blockSignals(False)
        self.slider.blockSignals(False)

    def _from_slider(self, iv: int):
        v = iv / self._k
        self.spin.blockSignals(True)
        self.spin.setValue(v)
        self.spin.blockSignals(False)
        self.valueChanged.emit(v)

    def _from_spin(self, v: float):
        self.slider.blockSignals(True)
        self.slider.setValue(int(round(v * self._k)))
        self.slider.blockSignals(False)
        self.valueChanged.emit(float(v))


class PreviewWidget(QWidget):
    """Paints the renderer's frame letter-boxed into the widget."""
    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.renderer: Optional[Renderer] = None
        self.t = 0.0
        self.note = ""
        self.backdrop = QColor("#0f1115")
        self.framed = True
        self.setMinimumSize(320, 180)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def set_renderer(self, r: Renderer) -> None:
        self.renderer = r
        self.update()

    def set_time(self, t: float) -> None:
        self.t = t
        self.update()

    def frame_rect(self) -> QRectF:
        r = self.renderer
        W, H = (r.W, r.H) if r else (16, 9)
        pad = 6 if self.framed else 0
        avail = QRectF(self.rect()).adjusted(pad, pad, -pad, -pad)
        sc = min(avail.width() / W, avail.height() / H)
        w, h = W * sc, H * sc
        return QRectF(avail.center().x() - w / 2, avail.center().y() - h / 2, w, h)

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), self.backdrop)
        r = self.renderer
        if r is None:
            return
        fr = self.frame_rect()
        p.save()
        p.setClipRect(fr)
        p.translate(fr.topLeft())
        p.scale(fr.width() / r.W, fr.height() / r.H)
        r.paint(p, self.t)
        p.restore()
        if not self.framed:
            return
        p.setPen(QPen(QColor("#2c313b"), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(fr.adjusted(-0.5, -0.5, 0.5, 0.5))
        if self.note:
            f = QFont(self.font())
            f.setPointSize(9)
            p.setFont(f)
            fm = p.fontMetrics()
            box = QRectF(fr.left() + 6, fr.top() + 6, fm.horizontalAdvance(self.note) + 16, fm.height() + 8)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(20, 20, 24, 215))
            p.drawRoundedRect(box, 4, 4)
            p.setPen(QColor("#ffd38a"))
            p.drawText(box, Qt.AlignmentFlag.AlignCenter, self.note)

    def mousePressEvent(self, e):
        self.setFocus()
        self.clicked.emit()
        super().mousePressEvent(e)


class TimelineWidget(QWidget):
    """Waveform overview + one block per lyric entry + playhead. Click/drag to seek."""
    seekRequested = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.duration = 0.0
        self.peaks = np.zeros(0, np.float32)
        self.peak_rate = 100
        self.entries: list[tuple[float, float, bool]] = []   # start, end, merged
        self.t = 0.0
        self.current = -1
        self.setMinimumHeight(64)
        self.setMaximumHeight(80)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)
        self._hover = None
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def set_audio(self, duration: float, peaks: Optional[np.ndarray], rate: int = 100) -> None:
        self.duration = max(0.0, duration)
        self.peaks = peaks if peaks is not None else np.zeros(0, np.float32)
        self.peak_rate = rate
        self.update()

    def set_entries(self, entries: list[tuple[float, float, bool]]) -> None:
        self.entries = entries
        self.update()

    def set_time(self, t: float, current: int = -1) -> None:
        self.t = t
        self.current = current
        self.update()

    def _dur(self) -> float:
        if self.duration > 0:
            return self.duration
        if self.entries:
            return self.entries[-1][1] + 3
        return 60.0

    def _x(self, t: float) -> float:
        return 8 + (self.width() - 16) * (t / self._dur())

    def _t(self, x: float) -> float:
        return max(0.0, min(self._dur(), (x - 8) / max(1, self.width() - 16) * self._dur()))

    def _wave_path(self, w: int, mid: float, amp: float) -> Optional[QPainterPath]:
        key = (w, self.height(), id(self.peaks), self.peaks.size)
        if getattr(self, "_wave_key", None) == key:
            return self._wave
        self._wave_key = key
        self._wave = None
        if self.peaks.size and w > 16:
            n = w - 16
            dur_samples = self._dur() * self.peak_rate
            ends = np.linspace(0, dur_samples, n + 1)
            idx = np.clip(ends[:-1].astype(int), 0, max(0, len(self.peaks) - 1))
            cols = np.maximum.reduceat(self.peaks, idx) if len(idx) else np.zeros(0)
            cols[ends[:-1] >= len(self.peaks)] = 0
            path = QPainterPath()
            path.moveTo(8, mid)
            for i, v in enumerate(cols):
                path.lineTo(8 + i, mid - float(v) * amp)
            for i in range(len(cols) - 1, -1, -1):
                path.lineTo(8 + i, mid + float(cols[i]) * amp)
            path.closeSubpath()
            self._wave = path
        return self._wave

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor("#121419"))
        mid = h * 0.42
        amp = h * 0.32
        path = self._wave_path(w, mid, amp)
        if path is not None:
            p.fillPath(path, QColor("#33435e"))
        # lyric blocks
        y0 = h - 16
        for i, (s, en, merged) in enumerate(self.entries):
            x1, x2 = self._x(s), self._x(max(en, s + 0.2))
            col = QColor("#4c8dff") if i == self.current else (QColor("#8a6cf0") if merged else QColor("#4d5566"))
            p.fillRect(QRectF(x1, y0, max(1.5, x2 - x1 - 1), 10), col)
        # playhead
        x = self._x(self.t)
        p.setPen(QPen(QColor("#ff5d5d"), 2))
        p.drawLine(QPointF(x, 2), QPointF(x, h - 2))
        if self._hover is not None:
            p.setPen(QPen(QColor(255, 255, 255, 90), 1))
            p.drawLine(QPointF(self._hover, 2), QPointF(self._hover, h - 2))
            p.setPen(QColor("#c8c8c8"))
            p.drawText(QPointF(min(self._hover + 4, w - 60), 12), fmt_time(self._t(self._hover)))

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.setFocus()
            self.seekRequested.emit(self._t(e.position().x()))

    def mouseMoveEvent(self, e):
        self._hover = e.position().x()
        if e.buttons() & Qt.MouseButton.LeftButton:
            self.seekRequested.emit(self._t(e.position().x()))
        self.update()

    def leaveEvent(self, e):
        self._hover = None
        self.update()
