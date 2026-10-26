"""Program entry point."""
from __future__ import annotations
from teleprompter.i18n import tr

import faulthandler
import os
import sys
import traceback


def _setup_logging():
    """A windowed exe has no console: keep a crash log next to the program."""
    from .paths import app_dir
    log = os.path.join(app_dir(), "error.log")
    try:
        fh = open(log, "a", encoding="utf-8", buffering=1)
    except OSError:
        return
    import atexit

    def _cleanup():
        try:
            fh.flush()
            empty = os.path.getsize(log) == 0
            fh.close()
            if empty:
                os.remove(log)
        except OSError:
            pass
    atexit.register(_cleanup)
    if getattr(sys, "frozen", False) or sys.stderr is None:
        sys.stderr = fh
        sys.stdout = fh
    try:
        faulthandler.enable(fh)
    except Exception:
        pass

    def hook(et, ev, tb):
        traceback.print_exception(et, ev, tb, file=fh)
        try:
            from PySide6.QtWidgets import (QApplication)
            if QApplication.instance():
                QMessageBox.critical(None, tr('程序出错'),
                                     tr('{p0}\n\n详细信息已写入：\n{p1}', p0=ev, p1=log))
        except Exception:
            pass
    sys.excepthook = hook


def _selftest(out_dir: str) -> int:
    """Headless check that every bundled component loads and works (used after packaging)."""
    import math
    import struct
    import time
    import wave
    os.makedirs(out_dir, exist_ok=True)
    report = []
    ok = True

    def log(msg):
        report.append(msg)

    try:
        from PySide6.QtWidgets import (QApplication)
        app = QApplication.instance() or QApplication(sys.argv)
        import av, ctranslate2, numpy, pypinyin, sounddevice  # noqa: F401
        import faster_whisper
        log(tr('imports ok: av {p0}, ctranslate2 {p1}, faster_whisper {p2}, numpy {p3}', p0=av.__version__, p1=ctranslate2.__version__, p2=faster_whisper.__version__, p3=numpy.__version__))
        log(tr('cuda devices: {p0}', p0=ctranslate2.get_cuda_device_count()))
        from .align import _pinyin
        log(tr('pinyin 爱 -> {p0}', p0=_pinyin(tr('爱'))))
        from .lyrics import LyricLine
        from .render import Renderer
        from .style import Style
        st = Style(width=1280, height=720, fps=30)
        lines = [LyricLine(0.5 + i * 1.0, 0.5 + i * 1.0 + 0.8, t) for i, t in
                 enumerate([tr('自检第一行'), tr('这是当前行歌词'), "Self test line three", tr('第四行'), tr('第五行')])]
        Renderer(st, lines).render_image(1.7).save(os.path.join(out_dir, "selftest_frame.png"))
        wav = os.path.join(out_dir, "selftest.wav")
        with wave.open(wav, "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(44100)
            w.writeframes(b"".join(struct.pack("<hh", int(8000 * math.sin(i / 44100 * 2 * math.pi * 440)),
                                               int(8000 * math.sin(i / 44100 * 2 * math.pi * 440)))
                                   for i in range(44100 * 6)))
        from .export import encoder_available, export_video
        t = time.time()
        res = export_video(st, lines, wav, os.path.join(out_dir, "selftest.mp4"))
        log(tr('export ok: {p0} frames, {p1} unique, {p2} bytes, {p3:.1f}s', p0=res.frames, p1=res.unique_frames, p2=res.size, p3=time.time() - t))
        log(tr('nvenc available: {p0}', p0=encoder_available('h264_nvenc')))
        from . import modelhub
        log(tr('model dir: {p0} installed={p1}', p0=modelhub.models_dir(), p1=modelhub.is_installed(modelhub.DEFAULT_MODEL)))
        if modelhub.is_installed(modelhub.DEFAULT_MODEL):
            from .align import load_model, transcribe
            from .media import decode_audio
            m = load_model(modelhub.DEFAULT_MODEL)
            a = decode_audio(wav, 16000, 1)[:, 0].copy()
            words, lang = transcribe(m, a, "zh", "", lambda f: None, lambda: False)
            log(tr('whisper ok: {p0} words on a sine tone (lang {p1})', p0=len(words), p1=lang))
        try:
            import sounddevice as sd
            log(tr('audio out: {p0}', p0=sd.query_devices(kind='output')['name']))
        except Exception as e:
            log(tr('audio out: none ({p0})', p0=e))
    except Exception:
        ok = False
        log(traceback.format_exc())
    with open(os.path.join(out_dir, "selftest.txt"), "w", encoding="utf-8") as fh:
        fh.write(("PASS" if ok else "FAIL") + "\n" + "\n".join(report) + "\n")
    return 0 if ok else 1


def main() -> int:
    if len(sys.argv) >= 3 and sys.argv[1] == "--selftest":
        return _selftest(sys.argv[2])
    _setup_logging()
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    from PySide6.QtCore import Qt
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import (QApplication)
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeDialogs, True)
    app = QApplication(sys.argv)
    app.setApplicationName("TeleprompterMaker")
    from .gui.theme import apply_theme
    apply_theme(app)
    from .gui.main_window import MainWindow
    win = MainWindow()
    win.show()
    if len(sys.argv) >= 3 and sys.argv[1] == "--snapshot":   # packaging check: grab window and quit
        from PySide6.QtCore import QTimer
        target = sys.argv[2]

        def snap():
            win.grab().save(target)
            win.close()
            app.quit()
        QTimer.singleShot(3000, snap)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
