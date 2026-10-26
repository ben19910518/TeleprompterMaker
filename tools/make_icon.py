"""Draw the app icon with Qt and save a multi-resolution .ico (build-time only)."""
import io
import os
import sys

from PySide6.QtCore import QBuffer, QIODevice, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QLinearGradient, QPainter, QPainterPath
from PIL import Image

OUT = os.path.join(os.path.dirname(__file__), "..", "src", "teleprompter", "resources")


def draw(size: int) -> QImage:
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    s = size / 256.0
    bg = QPainterPath()
    bg.addRoundedRect(QRectF(8 * s, 8 * s, 240 * s, 240 * s), 52 * s, 52 * s)
    g = QLinearGradient(0, 0, 0, size)
    g.setColorAt(0, QColor("#1f2a44"))
    g.setColorAt(1, QColor("#0b0f19"))
    p.fillPath(bg, g)
    p.setPen(Qt.PenStyle.NoPen)
    bars = [(62, 56, 132, 20, 70), (96, 36, 184, 34, 255), (142, 56, 132, 20, 120), (176, 74, 96, 16, 55)]
    for y, x, w, h, a in bars:
        c = QColor(255, 255, 255, a)
        p.setBrush(c)
        p.drawRoundedRect(QRectF(x * s, y * s, w * s, h * s), h * s / 2, h * s / 2)
    # cue triangle
    tri = QPainterPath()
    tri.moveTo(16 * s, 99 * s)
    tri.lineTo(30 * s, 113 * s)
    tri.lineTo(16 * s, 127 * s)
    tri.closeSubpath()
    p.fillPath(tri, QColor("#3d8bfd"))
    p.end()
    return img


def to_pil(img: QImage) -> Image.Image:
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return Image.open(io.BytesIO(bytes(buf.data()))).convert("RGBA")


if __name__ == "__main__":
    app = QGuiApplication(sys.argv)
    os.makedirs(OUT, exist_ok=True)
    big = to_pil(draw(256))
    big.save(os.path.join(OUT, "icon.png"))
    big.save(os.path.join(OUT, "icon.ico"), sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("icon written to", os.path.abspath(OUT))
