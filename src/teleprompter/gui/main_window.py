"""Main window."""
from __future__ import annotations
from ..i18n import tr, join_text, set_language, language, events, is_cancelled_message
from .i18n_widgets import QAction, QMenu, QStatusBar, QDialog
from .i18n_widgets import QCheckBox, QComboBox, QGroupBox, QLabel, QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem

import glob
import math
import os
import subprocess
import sys
from typing import Optional

from PySide6.QtCore import QEvent, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QFontDatabase, QIcon, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QAbstractSpinBox, QApplication, QButtonGroup, QFileDialog, QFontComboBox, QFormLayout, QFrame, QHBoxLayout, QHeaderView, QProgressBar, QScrollArea, QSplitter, QStackedWidget, QTextEdit, QVBoxLayout, QWidget, QDialogButtonBox)

from .. import APP_NAME, __version__, paths
from ..export import ENCODERS, PRESETS_X264
from ..lyrics import LyricLine, load_lyrics, save_lyrics
from ..media import AUDIO_EXTS
from ..player import AudioPlayer
from ..render import Renderer, demo_lines
from ..style import SEPARATORS, Style, load_settings, save_settings
from .align_dialog import AlignPanel
from .lyric_editor import LyricEditorMixin, edit_time
from .widgets import ColorButton, PreviewWidget, SliderSpin, TimelineWidget, card, fmt_time
from .workers import AudioLoadWorker, EncoderProbeWorker, ExportWorker

RESOLUTIONS = [
    (tr('1920×1080（横屏 1080p）'), 1920, 1080),
    (tr('1280×720（横屏 720p）'), 1280, 720),
    (tr("2560×1440（2K）"), 2560, 1440),
    (tr("3840×2160（4K）"), 3840, 2160),
    (tr('1080×1920（竖屏）'), 1080, 1920),
    (tr("1024×768（4:3）"), 1024, 768),
    (tr('自定义'), 0, 0),
]
FPS_LIST = [23.976, 24, 25, 29.97, 30, 50, 59.94, 60]
QUALITY = [(tr('高画质（QP 18）'), 18), (tr('标准（QP 22，推荐）'), 22), (tr('小文件（QP 27）'), 27)]
BG_PRESETS = [(tr('黑色'), "#000000"), (tr('绿幕'), "#00B140"), (tr('蓝幕'), "#0047BB")]
STRONG_STYLES = ["Bold", "Black", "Heavy", "ExtraBold", "SemiBold", "DemiBold", "Medium", "Regular", "Normal"]
STYLE_CN = {
    "thin": tr('极细'), "extralight": tr('特细'), "ultralight": tr('特细'), "light": tr('细'), "demilight": tr('半细'),
    "semilight": tr('半细'), "regular": tr('常规'), "normal": tr('常规'), "book": tr('常规'), "medium": tr('中等'),
    "semibold": tr('半粗'), "demibold": tr('半粗'), "bold": tr('粗'), "extrabold": tr('特粗'), "ultrabold": tr('特粗'),
    "black": tr('黑'), "heavy": tr('黑'),
}
LYRIC_FILTER = tr('歌词/字幕 (*.lrc *.srt *.vtt *.ass *.ssa *.txt);;所有文件 (*.*)')
LYRIC_EXTS = (".lrc", ".srt", ".vtt", ".ass", ".ssa", ".txt")


class FullPreview(PreviewWidget):
    """Frameless full-screen copy of the preview, for checking on the stage monitor."""

    def __init__(self, main: "MainWindow"):
        super().__init__(None)
        self.main = main
        self.framed = False
        from PySide6.QtGui import QColor
        self.backdrop = QColor("#000000")
        self.setWindowTitle(tr('全屏预览（Esc 退出，空格 播放/暂停）'))
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setCursor(Qt.CursorShape.BlankCursor)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.close()
        elif e.key() == Qt.Key.Key_Space:
            self.main.toggle_play()
        elif e.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down):
            self.main.keyPressEvent(e)

    def closeEvent(self, e):
        self.main.full_preview = None
        super().closeEvent(e)


class MainWindow(LyricEditorMixin, QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(tr('{p0}  v{p1}[*]', p0=tr(APP_NAME), p1=__version__))
        ico = os.path.join(paths.resource_dir(), "icon.ico")
        if os.path.isfile(ico):
            self.setWindowIcon(QIcon(ico))
        self.setAcceptDrops(True)
        self.settings_file = paths.settings_path()
        self.cfg = load_settings(self.settings_file)
        self.ui_language = self.cfg.get("ui_language", "auto")
        if self.ui_language not in ("auto", "zh", "en", "ja"):
            self.ui_language = "auto"
        set_language(self.ui_language)
        self.style = Style.from_dict(self.cfg.get("style", {}))
        self.align_cfg = self.cfg.get("align", {})
        self._refresh: list = []          # widget refreshers (style -> widget)
        self._adv_rows: list = []         # (form, field widget) shown only in detailed mode
        self._adv_widgets: list = []      # plain widgets shown only in detailed mode
        self.audio_path = ""
        self.lyrics_path = ""
        self.lines: list[LyricLine] = []
        self.lines_timed = False
        self.lines_note = ""
        self._init_lyric_editor()
        self.audio_info = None
        self.player = AudioPlayer()
        self.renderer: Optional[Renderer] = None
        self.full_preview: Optional[FullPreview] = None
        self._t = 0.0
        self._t_user = False
        self._stop_at: Optional[float] = None
        self._entries_sig = None
        self._cur_idx = -2
        self._audio_worker = None
        self._export_worker = None
        self._out_auto = True
        self.mode = "simple"

        self._rebuild_timer = QTimer(self)
        self._rebuild_timer.setSingleShot(True)
        self._rebuild_timer.setInterval(40)
        self._rebuild_timer.timeout.connect(self._rebuild)
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(1500)
        self._save_timer.timeout.connect(self._save_settings)
        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(15)
        self._tick_timer.timeout.connect(self._tick)

        self._build_ui()
        events.changed.connect(self._on_ui_language_changed)
        QApplication.instance().installEventFilter(self)
        self._load_fonts()
        self._refresh.append(self._sync_quality)
        self._refresh_widgets()
        self._set_mode(self.cfg.get("mode", "simple"))
        self._tick_timer.start()

        self._rebuild()
        geo = self.cfg.get("geometry")
        if geo:
            try:
                self.restoreGeometry(bytes.fromhex(geo))
            except Exception:
                pass
        else:
            self.resize(1500, 900)
        last = self.cfg.get("files", {})
        if last.get("out"):
            self.out_edit.setText(last["out"])
            self._out_auto = bool(last.get("out_auto", True))
        if last.get("audio") and os.path.isfile(last["audio"]):
            self.load_audio(last["audio"], quiet=True)
        if last.get("lyrics") and os.path.isfile(last["lyrics"]):
            self.load_lyrics_file(last["lyrics"], quiet=True)
        self._go_step(1 if self.lines and self.lines_timed else 0)
        self._probe = EncoderProbeWorker(self)
        self._probe.found.connect(self._encoders_found)
        self._probe.start()

    # ================================================================== UI
    def _build_ui(self):
        self.setStatusBar(QStatusBar(self))
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())
        self.pages = QStackedWidget()
        root.addWidget(self.pages, 1)
        self.pages.addWidget(self._build_import_page())
        self.pages.addWidget(self._build_edit_page())
        self.btn_play.setToolTip(tr('空格键：播放/暂停；在歌词、时间等输入框中保留正常输入'))
        self.statusBar().showMessage(tr('提示：可以直接把音频和歌词文件拖进窗口。空格键播放/暂停，←→ 快退快进，↑↓ 上一句/下一句。'))

    def _build_header(self):
        bar = QFrame()
        bar.setObjectName("header")
        h = QHBoxLayout(bar)
        h.setContentsMargins(16, 8, 16, 8)
        h.setSpacing(8)
        png = os.path.join(paths.resource_dir(), "icon.png")
        if os.path.isfile(png):
            logo = QLabel()
            logo.setPixmap(QPixmap(png).scaled(26, 26, Qt.AspectRatioMode.KeepAspectRatio,
                                               Qt.TransformationMode.SmoothTransformation))
            h.addWidget(logo)
        title = QLabel(tr(APP_NAME))
        title.setObjectName("appTitle")
        h.addWidget(title)
        h.addSpacing(24)
        self.step_buttons = []
        steps = QButtonGroup(self)
        for i, (text, tip) in enumerate(((tr('① 导入与对轴'), tr('导入音频和歌词，自动识别时间轴')),
                                         (tr('② 格式与微调'), tr('设置提词器画面格式，微调时间轴并导出视频')))):
            if i:
                arrow = QLabel("›")
                arrow.setObjectName("stepArrow")
                h.addWidget(arrow)
            b = QPushButton(text)
            b.setObjectName("step")
            b.setToolTip(tip)
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, k=i: self._go_step(k))
            steps.addButton(b)
            h.addWidget(b)
            self.step_buttons.append(b)
        h.addStretch(1)
        self.mode_box = QWidget()
        ml = QHBoxLayout(self.mode_box)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(0)
        self.btn_simple = QPushButton(tr('简易模式'))
        self.btn_adv = QPushButton(tr('详细模式'))
        self.btn_simple.setObjectName("segLeft")
        self.btn_adv.setObjectName("segRight")
        grp = QButtonGroup(self)
        for b in (self.btn_simple, self.btn_adv):
            b.setCheckable(True)
            grp.addButton(b)
            ml.addWidget(b)
        self.btn_simple.clicked.connect(lambda: self._set_mode("simple"))
        self.btn_adv.clicked.connect(lambda: self._set_mode("advanced"))
        h.addWidget(self.mode_box)
        h.addSpacing(6)
        self.settings_menu = QMenu(tr("设置"), self)
        self.language_action = QAction(tr("界面语言…"), self)
        self.language_action.triggered.connect(self._show_language_settings)
        self.settings_menu.addAction(self.language_action)
        self.btn_settings = QPushButton(tr("设置"))
        self.btn_settings.setObjectName("flat")
        self.btn_settings.setMenu(self.settings_menu)
        h.addWidget(self.btn_settings)
        return bar

    def _build_import_page(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(16, 14, 16, 12)
        lay.setSpacing(10)
        box, body, head = card(tr('音频'))
        drop = QLabel(tr('可以直接把音频和歌词文件拖进窗口'))
        drop.setObjectName("hint")
        head.addWidget(drop)
        row = QHBoxLayout()
        self.audio_edit = QLineEdit()
        self.audio_edit.setReadOnly(True)
        self.audio_edit.setPlaceholderText(tr('选择歌曲音频（mp3 / wav / flac / m4a …）'))
        row.addWidget(self.audio_edit, 1)
        self.audio_meta = QLabel("")
        self.audio_meta.setObjectName("hint")
        row.addWidget(self.audio_meta)
        b = QPushButton(tr('选择…'))
        b.clicked.connect(self._pick_audio)
        row.addWidget(b)
        body.addLayout(row)
        lay.addWidget(box)

        self.align = AlignPanel(page, self.audition, self.align_cfg, import_handler=self._pick_lyrics)
        self.align.applied.connect(self._apply_aligned)
        self.lyr_edit = QLineEdit()
        self.lyr_edit.setReadOnly(True)
        self.lyr_edit.setPlaceholderText(tr('选择歌词（lrc / srt / 纯文本 txt）'))
        self.lyr_edit.setVisible(False)
        self.lyr_edit.textChanged.connect(lambda t: self.lyr_edit.setVisible(bool(t)))
        self.align.text_footer.addWidget(self.lyr_edit)
        self.lyr_state = QLabel("")
        self.lyr_state.setWordWrap(True)
        self.lyr_state.setVisible(False)
        self.align.text_footer.addWidget(self.lyr_state)
        self.btn_skip = QPushButton(tr('已有时间轴，直接下一步 →'))
        self.btn_skip.setObjectName("accent")
        self.btn_skip.setToolTip(tr('歌词已经带时间轴（LRC / SRT）时，跳过自动识别'))
        self.btn_skip.clicked.connect(lambda: self._go_step(1))
        self.align.bottom.insertWidget(1, self.btn_skip)
        lay.addWidget(self.align, 1)
        return page

    def _build_edit_page(self):
        page = QWidget()
        root = QHBoxLayout(page)
        root.setContentsMargins(16, 14, 16, 12)
        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        root.addWidget(split)
        self.splitter = split

        # ---------------------------------------------------------- left
        left = QWidget()
        left.setMinimumWidth(380)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 6, 0)
        ll.setSpacing(10)
        self._build_project(ll)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        panel = QWidget()
        panel.setObjectName("settingsPanel")
        self.panel = QVBoxLayout(panel)
        self.panel.setContentsMargins(0, 0, 8, 0)
        self.panel.setSpacing(10)
        scroll.setWidget(panel)
        ll.addWidget(scroll, 1)

        self._build_canvas()
        self._build_text()
        self._build_opacity()
        self._build_motion()
        self._build_merge()
        self._build_output()
        self.panel.addStretch(1)

        # export box (always visible)
        exp, el, _ = card(heading=False)
        orow = QHBoxLayout()
        orow.addWidget(QLabel(tr('保存到')))
        self.out_edit = QLineEdit()
        self.out_edit.setPlaceholderText(tr('输出视频文件路径（.mp4）'))
        self.out_edit.textEdited.connect(lambda _: setattr(self, "_out_auto", False))
        orow.addWidget(self.out_edit, 1)
        b = QPushButton(tr('浏览…'))
        b.clicked.connect(self._pick_output)
        orow.addWidget(b)
        el.addLayout(orow)
        brow = QHBoxLayout()
        self.btn_export = QPushButton(tr('生成提词器视频'))
        self.btn_export.setObjectName("primary")
        self.btn_export.clicked.connect(self._export)
        brow.addWidget(self.btn_export, 1)
        self.btn_export_cancel = QPushButton(tr('取消'))
        self.btn_export_cancel.setVisible(False)
        self.btn_export_cancel.clicked.connect(self._export_cancel)
        brow.addWidget(self.btn_export_cancel)
        el.addLayout(brow)
        self.export_bar = QProgressBar()
        self.export_bar.setRange(0, 1000)
        self.export_bar.setTextVisible(False)
        self.export_bar.setFixedHeight(6)
        self.export_bar.setVisible(False)
        el.addWidget(self.export_bar)
        self.export_status = QLabel("")
        self.export_status.setObjectName("hint")
        self.export_status.setWordWrap(True)
        el.addWidget(self.export_status)
        ll.addWidget(exp)
        split.addWidget(left)

        # --------------------------------------------------------- right
        vsplit = QSplitter(Qt.Orientation.Vertical)
        vsplit.setChildrenCollapsible(False)
        stage, rl, _ = card(heading=False)
        self.preview = PreviewWidget()
        rl.addWidget(self.preview, 1)
        transport = QHBoxLayout()
        transport.setSpacing(6)
        self.btn_play = QPushButton(tr('▶ 播放'))
        self.btn_play.setObjectName("accent")
        self.btn_play.setMinimumWidth(96)
        self.btn_play.clicked.connect(self.toggle_play)
        self.btn_prev = QPushButton(tr('◀ 上一句'))
        self.btn_prev.clicked.connect(lambda: self._jump(-1))
        self.btn_next = QPushButton(tr('下一句 ▶'))
        self.btn_next.clicked.connect(lambda: self._jump(1))
        self.time_label = QLabel("00:00.00 / 00:00.00")
        self.time_label.setObjectName("timecode")
        self.time_label.setMinimumWidth(160)
        self.btn_full = QPushButton(tr('全屏预览'))
        self.btn_full.setToolTip(tr('在第二块屏幕（或当前屏幕）全屏显示，用来在真实提词屏上检查效果'))
        self.btn_full.clicked.connect(self._full_preview)
        for w in (self.btn_play, self.btn_prev, self.btn_next):
            transport.addWidget(w)
        transport.addSpacing(8)
        transport.addWidget(self.time_label)
        transport.addStretch(1)
        transport.addWidget(self.btn_full)
        rl.addLayout(transport)
        self.timeline = TimelineWidget()
        self.timeline.seekRequested.connect(self._timeline_seek)
        rl.addWidget(self.timeline)
        self.info = QLabel("")
        self.info.setObjectName("hint")
        rl.addWidget(self.info)
        vsplit.addWidget(stage)

        lower = QSplitter(Qt.Orientation.Horizontal)
        lower.setChildrenCollapsible(False)
        lyrics, tl, _ = card(tr('歌词与时间轴'))
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels([tr('开始'), tr('结束'), tr('原始歌词（点击跳转，双击编辑）')])
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.table.setColumnWidth(0, 96)
        self.table.setColumnWidth(1, 120)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.cellClicked.connect(self._table_clicked)
        tl.addWidget(self.table, 1)
        lower.addWidget(lyrics)
        self._build_lyric_editor(lower)
        lower.setStretchFactor(0, 1)
        lower.setStretchFactor(1, 0)
        vsplit.addWidget(lower)
        vsplit.setStretchFactor(0, 3)
        vsplit.setStretchFactor(1, 2)
        vsplit.setSizes([520, 320])
        split.addWidget(vsplit)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([420, 1080])
        return page

    def _build_project(self, layout):
        box, body, head = card(tr('项目'))
        self.btn_align = QPushButton(tr('← 重新对轴'))
        self.btn_align.setObjectName("small")
        self.btn_align.setToolTip(tr('只有音频和纯文本歌词时，自动听歌给每一行歌词配上时间，并可保存为 LRC / SRT'))
        self.btn_align.clicked.connect(self._open_align)
        head.addWidget(self.btn_align)
        self.btn_save_lyr = QPushButton(tr('另存歌词…'))
        self.btn_save_lyr.setObjectName("small")
        self.btn_save_lyr.setToolTip(tr('把当前时间轴保存为 LRC 或 SRT'))
        self.btn_save_lyr.clicked.connect(self._save_lyrics_as)
        head.addWidget(self.btn_save_lyr)
        self.proj_audio = QLabel("")
        self.proj_lyrics = QLabel("")
        for w in (self.proj_audio, self.proj_lyrics):
            w.setObjectName("projLine")
            w.setTextFormat(Qt.TextFormat.PlainText)
            body.addWidget(w)
        layout.addWidget(box)

    def _update_project(self):
        audio = os.path.basename(self.audio_path) if self.audio_path else tr('未选择音频')
        if self.audio_info:
            audio = tr('{p0}  ·  {p1}', p0=audio, p1=fmt_time(self.audio_info.duration, False))
        self.proj_audio.setText(tr('♪  {p0}', p0=audio))
        if not self.lines:
            lyr = tr('未导入歌词')
        else:
            name = os.path.basename(self.lyrics_path) if self.lyrics_path else tr('歌词')
            lyr = tr('{p0}  ·  {p1}', p0=name, p1=tr('{p0} 句', p0=len(self.lines)))
            if not self.lines_timed:
                lyr = tr('{p0}  ·  {p1}', p0=lyr, p1=tr('⚠ 未对轴'))
        self.proj_lyrics.setText(tr('☰  {p0}', p0=lyr))
        timed = bool(self.lines) and self.lines_timed
        self.step_buttons[0].setProperty("done", timed)
        for b in self.step_buttons:
            b.style().unpolish(b)
            b.style().polish(b)
        self.btn_save_lyr.setEnabled(timed)
        self.btn_skip.setEnabled(timed)

    def _go_step(self, step: int):
        if step == 0 and not self._flush_lyric_draft():
            step = self.pages.currentIndex()
        self.pages.setCurrentIndex(step)
        self.step_buttons[step].setChecked(True)
        self.mode_box.setVisible(step == 1)

    # ---------------------------------------------------------- helpers
    def _show_language_settings(self):
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("设置"))
        dialog.setMinimumWidth(480)
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        selector = QComboBox()
        for label, code in ((tr("跟随系统"), "auto"), ("简体中文", "zh"), ("English", "en"), ("日本語", "ja")):
            selector.addItem(label, code)
        selector.setCurrentIndex(max(0, selector.findData(self.ui_language)))
        form.addRow(QLabel(tr("界面语言")), selector)
        layout.addLayout(form)
        hint = QLabel(tr("跟随系统时：中文系统显示中文，日文系统显示日文，其他系统显示英文。切换立即生效并自动记住，不改变歌词内容或识别语言。"))
        hint.setWordWrap(True)
        layout.addWidget(hint)
        selector.currentIndexChanged.connect(lambda _: self._set_ui_language(selector.currentData()))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    def _set_ui_language(self, preference):
        if preference not in ("auto", "zh", "en", "ja"):
            preference = "auto"
        self.ui_language = preference
        set_language(preference)
        self._save_settings()

    def _on_ui_language_changed(self, _language):
        self._fill_weights(self.style.font_family, self.style.font_style)
        if self.full_preview is not None:
            self.full_preview.setWindowTitle(tr('全屏预览（Esc 退出，空格 播放/暂停）'))
        self._rebuild()

    def _section(self, title: str, advanced: bool = False):
        box = QGroupBox(title)
        form = QFormLayout(box)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(7)
        self.panel.addWidget(box)
        if advanced:
            self._adv_widgets.append(box)
        return box, form

    def _row(self, form: QFormLayout, label: str, widget: QWidget, adv: bool = False, tip: str = ""):
        if tip:
            widget.setToolTip(tip)
        lab = QLabel(label)
        if tip:
            lab.setToolTip(tip)
        form.addRow(lab, widget)
        if adv:
            self._adv_rows.append((form, widget))
        return widget

    def _changed(self):
        self._rebuild_timer.start()
        self._save_timer.start()

    def _bind_value(self, key: str, w, factor: float = 1.0, cast=float):
        def on(v):
            setattr(self.style, key, cast(v / factor) if cast is not int else int(round(v / factor)))
            self._changed()
        w.valueChanged.connect(on)

        def refresh():
            w.blockSignals(True)
            v = getattr(self.style, key) * factor
            w.setValue(int(round(v)) if isinstance(w, QSpinBox) else float(v))
            w.blockSignals(False)
        self._refresh.append(refresh)
        return w

    def _bind_check(self, key: str, cb: QCheckBox):
        def on(v):
            setattr(self.style, key, bool(v))
            self._changed()
        cb.toggled.connect(on)

        def refresh():
            cb.blockSignals(True)
            cb.setChecked(bool(getattr(self.style, key)))
            cb.blockSignals(False)
        self._refresh.append(refresh)
        return cb

    def _bind_combo(self, key: str, combo: QComboBox, cast=str):
        def on(_):
            d = combo.currentData()
            if d is not None:
                setattr(self.style, key, cast(d))
                self._changed()
        combo.currentIndexChanged.connect(on)

        def refresh():
            combo.blockSignals(True)
            v = getattr(self.style, key)
            for i in range(combo.count()):
                d = combo.itemData(i)
                if d == v or (isinstance(v, float) and isinstance(d, (int, float)) and abs(d - v) < 1e-3):
                    combo.setCurrentIndex(i)
                    break
            combo.blockSignals(False)
        self._refresh.append(refresh)
        return combo

    def _bind_color(self, key: str, btn: ColorButton):
        def on(c):
            setattr(self.style, key, c)
            self._changed()
        btn.colorChanged.connect(on)
        self._refresh.append(lambda: btn.setColor(getattr(self.style, key)))
        return btn

    def _refresh_widgets(self):
        for f in self._refresh:
            f()

    def _set_mode(self, mode: str):
        self.mode = "advanced" if mode == "advanced" else "simple"
        adv = self.mode == "advanced"
        self.btn_adv.setChecked(adv)
        self.btn_simple.setChecked(not adv)
        for form, w in self._adv_rows:
            form.setRowVisible(w, adv)
        for w in self._adv_widgets:
            w.setVisible(adv)
        self._update_custom_res_visibility()
        self._save_timer.start() if hasattr(self, "_save_timer") else None

    # ------------------------------------------------------ sections
    def _build_canvas(self):
        box, f = self._section(tr('画面'))
        self._canvas_form = f
        self.res_combo = QComboBox()
        for name, w, h in RESOLUTIONS:
            self.res_combo.addItem(name, (w, h))
        self.res_combo.currentIndexChanged.connect(self._res_changed)
        self._row(f, tr('分辨率'), self.res_combo)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        self.w_spin = QSpinBox()
        self.w_spin.setRange(160, 7680)
        self.w_spin.setSingleStep(2)
        self.h_spin = QSpinBox()
        self.h_spin.setRange(120, 4320)
        self.h_spin.setSingleStep(2)
        for s in (self.w_spin, self.h_spin):
            s.setKeyboardTracking(False)
            s.valueChanged.connect(self._custom_res)
        row.addWidget(self.w_spin)
        row.addWidget(QLabel("×"))
        row.addWidget(self.h_spin)
        row.addStretch(1)
        self.custom_res_w = QWidget()
        self.custom_res_w.setLayout(row)
        self._row(f, tr('自定义尺寸'), self.custom_res_w)

        def refresh_res():
            self.res_combo.blockSignals(True)
            idx = len(RESOLUTIONS) - 1
            for i, (_, w, h) in enumerate(RESOLUTIONS):
                if w == self.style.width and h == self.style.height:
                    idx = i
                    break
            self.res_combo.setCurrentIndex(idx)
            self.res_combo.blockSignals(False)
            for s, v in ((self.w_spin, self.style.width), (self.h_spin, self.style.height)):
                s.blockSignals(True)
                s.setValue(v)
                s.blockSignals(False)
            self._update_custom_res_visibility()
        self._refresh.append(refresh_res)

        self.fps_combo = QComboBox()
        for v in FPS_LIST:
            self.fps_combo.addItem(tr('{p0:g} fps', p0=v), float(v))
        self._bind_combo("fps", self.fps_combo, float)
        self._row(f, tr('帧率'), self.fps_combo, tip=tr('提词器画面变化很少，30 fps 足够；需要配合其它素材时选同样的帧率'))

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        for name, col in BG_PRESETS:
            b = QPushButton(name)
            b.setToolTip({'#000000': tr('提词器屏幕播放'), '#00B140': tr('用于抠像（标准绿 #00B140）'),
                          '#0047BB': tr('用于抠像（标准蓝 #0047BB）')}[col])
            b.clicked.connect(lambda _=False, c=col: self._set_bg(c))
            row.addWidget(b)
        self.bg_btn = ColorButton(self.style.bg_color)
        self._bind_color("bg_color", self.bg_btn)
        row.addWidget(self.bg_btn)
        row.addStretch(1)
        w = QWidget()
        w.setLayout(row)
        self._row(f, tr('背景颜色'), w)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        self.fg_btn = self._bind_color("text_color", ColorButton())
        row.addWidget(self.fg_btn)
        row.addWidget(QLabel(tr('  当前行')))
        self.cur_btn = self._bind_color("current_color", ColorButton())
        row.addWidget(self.cur_btn)
        row.addStretch(1)
        w = QWidget()
        w.setLayout(row)
        self._row(f, tr('文字颜色'), w, adv=True, tip=tr('当前行可以单独设一个颜色（例如黄色）以便一眼找到'))

    def _build_text(self):
        box, f = self._section(tr('文字'))
        self.font_combo = QFontComboBox()
        self.font_combo.currentFontChanged.connect(self._font_changed)
        self._row(f, tr('字体'), self.font_combo)
        self.weight_combo = QComboBox()
        self.weight_combo.currentIndexChanged.connect(self._weight_changed)
        self._row(f, tr('字重'), self.weight_combo, tip=tr('字体自带的粗细；字体本身较细时可在详细模式里加「描边」使其更粗'))
        b = QPushButton(tr('加载字体文件…'))
        b.setToolTip(tr('使用未安装的字体（.ttf/.otf）。也可以把字体文件放进程序目录的 fonts 文件夹，启动时自动加载'))
        b.clicked.connect(self._load_font_file)
        self._row(f, "", b, adv=True)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        self.auto_size = QCheckBox(tr('自动铺满屏幕'))
        self._bind_check("auto_size", self.auto_size)
        self.auto_size.toggled.connect(lambda on: self.size_spin.setEnabled(not on))
        row.addWidget(self.auto_size)
        self.size_spin = QSpinBox()
        self.size_spin.setRange(8, 1200)
        self.size_spin.setSuffix(" px")
        self.size_spin.setKeyboardTracking(False)
        self._bind_value("font_size", self.size_spin, cast=int)
        row.addWidget(self.size_spin)
        row.addStretch(1)
        w = QWidget()
        w.setLayout(row)
        self._row(f, tr('中间行字号'), w, tip=tr('勾选「自动铺满屏幕」时，按显示行数自动算出最大的字号'))
        self._row(f, tr('上下行比例'), self._bind_value("size_ratio", SliderSpin(30, 100, 1, 0, " %"), 100),
                  tip=tr('上下行字号 = 中间行字号 × 比例'))
        self._row(f, tr('字间距'), self._bind_value("letter_spacing", SliderSpin(-10, 40, 1, 0, " %")),
                  tip=tr('字与字之间额外的距离，按字号的百分比'))
        self._row(f, tr('行间距'), self._bind_value("line_spacing", SliderSpin(0, 150, 1, 0, " %"), 100),
                  tip=tr('两句歌词之间的距离，按字号的百分比'))
        self._row(f, tr('折行行距'), self._bind_value("wrap_spacing", SliderSpin(-10, 60, 1, 0, " %"), 100), adv=True,
                  tip=tr('一句歌词太长被折成两行时，这两行之间的距离（比行间距更紧，才能看出是同一句）'))
        lines_spin = QSpinBox()
        lines_spin.setRange(1, 21)
        lines_spin.setSuffix(tr(' 行'))
        self._row(f, tr('显示行数'), self._bind_value("visible_lines", lines_spin, cast=int),
                  tip=tr('屏幕上同时显示的歌词句数（例如 7：当前句 + 上下各 3 句）'))
        self.above_combo = QComboBox()
        self.above_combo.addItem(tr('居中'), -1)
        for k in range(0, 11):
            self.above_combo.addItem(tr('上方显示 {p0} 句', p0=k), k)
        self._bind_combo("lines_above", self.above_combo, int)
        self._row(f, tr('当前行位置'), self.above_combo, adv=True,
                  tip=tr('例如上方 2 句、下方 4 句，可以让演员看到更多即将要唱的歌词'))
        rows = QComboBox()
        for k in (1, 2, 3):
            rows.addItem({1: tr('不折行（缩小字号）'), 2: tr('最多 2 行'), 3: tr('最多 3 行')}[k], k)
        self._row(f, tr('长句折行'), self._bind_combo("max_rows", rows, int), adv=True)
        al = QComboBox()
        for name, v in ((tr('居中'), "center"), (tr('靠左'), "left"), (tr('靠右'), "right")):
            al.addItem(name, v)
        self._row(f, tr('对齐'), self._bind_combo("align", al), adv=True)
        self._row(f, tr('左右边距'), self._bind_value("margin_x", SliderSpin(0, 30, 0.5, 1, " %")), adv=True)
        self._row(f, tr('上下边距'), self._bind_value("margin_y", SliderSpin(0, 30, 0.5, 1, " %")), adv=True)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        ow = SliderSpin(0, 15, 0.5, 1, " %")
        self._bind_value("outline", ow)
        row.addWidget(ow, 1)
        oc = self._bind_color("outline_color", ColorButton())
        row.addWidget(oc)
        w = QWidget()
        w.setLayout(row)
        self._row(f, tr('描边'), w, adv=True, tip=tr('文字描边宽度和颜色；颜色设为与文字相同可以让字变得更粗'))

    def _build_opacity(self):
        box, f = self._section(tr('亮度 / 透明度'), advanced=True)
        self._row(f, tr('相邻行亮度'), self._bind_value("near_opacity", SliderSpin(5, 100, 1, 0, " %"), 100))
        self._row(f, tr('最远行亮度'), self._bind_value("far_opacity", SliderSpin(0, 100, 1, 0, " %"), 100),
                  tip=tr('越往外的行越透明，从「相邻行」线性过渡到「最远行」'))
        self._row(f, tr('已唱过的行'), self._bind_value("past_opacity", SliderSpin(20, 100, 1, 0, " %"), 100),
                  tip=tr('上方（已经唱过的）歌词再额外调暗'))
        self._row(f, tr('上下边缘渐隐'), self._bind_check("edge_fade", QCheckBox(tr('开启'))))

    def _build_motion(self):
        box, f = self._section(tr('动画与时间'))
        self._row(f, tr('过渡动画'), self._bind_check("animate", QCheckBox(tr('平滑滚动（关闭可减小文件）'))))
        self._row(f, tr('动画时长'), self._bind_value("anim_duration", SliderSpin(0.1, 1.5, 0.05, 2, tr(' 秒'))), adv=True)
        self._row(f, tr('提前切换'), self._bind_value("lead_time", SliderSpin(0, 1.0, 0.05, 2, tr(' 秒'))), adv=True,
                  tip=tr('比歌词时间提前多少秒切到下一句，方便演员提前看到'))
        self._row(f, tr('整体偏移'), self._bind_value("time_offset", SliderSpin(-5, 5, 0.05, 2, tr(' 秒'))), adv=True,
                  tip=tr('歌词整体比音乐早/晚时用来校正：正数 = 歌词推后'))
        self._row(f, tr('前奏/间奏提示'), self._bind_check("countdown", QCheckBox(tr('提前显示下一句并倒计时'))),
                  tip=tr('间奏较长时，上一句唱完后就把下一句移到中间（暗色等待），开唱前出现 ●●● 倒计时'))
        self._row(f, tr('间奏判定'), self._bind_value("countdown_gap", SliderSpin(2, 30, 0.5, 1, tr(' 秒'))), adv=True,
                  tip=tr('两句之间空白超过这个时间才算间奏'))
        cs = QSpinBox()
        cs.setRange(1, 5)
        cs.setSuffix(tr(' 秒'))
        self._row(f, tr('倒计时'), self._bind_value("countdown_secs", cs, cast=int), adv=True)
        self._row(f, tr('等待行亮度'), self._bind_value("upcoming_opacity", SliderSpin(10, 100, 1, 0, " %"), 100),
                  adv=True)

    def _build_merge(self):
        box, f = self._section(tr('短句合并'))
        self._row(f, tr('短句合并'), self._bind_check("merge_short", QCheckBox(tr('自动把很短的几句合成一行'))),
                  tip=tr('例如「在春天」「在夏天」会显示为「在春天 ／ 在夏天」，正在唱的部分高亮'))
        self._row(f, tr('短句标准'), self._bind_value("merge_max_units", SliderSpin(1, 12, 0.5, 1, tr(' 字以内'))),
                  adv=True, tip=tr('中文/日文一个字算 1，英文字母算 0.5'))
        self._row(f, tr('最大间隔'), self._bind_value("merge_max_gap", SliderSpin(0, 6, 0.1, 1, tr(' 秒'))), adv=True,
                  tip=tr('两句之间停顿超过这个时间就不合并'))
        mp = QSpinBox()
        mp.setRange(2, 8)
        mp.setSuffix(tr(' 句'))
        self._row(f, tr('最多合并'), self._bind_value("merge_max_parts", mp, cast=int), adv=True)
        sep = QComboBox()
        for k, v in SEPARATORS.items():
            sep.addItem(tr('{p0}   例：在春天{p1}在夏天', p0=tr(k), p1=v), k)
        self._row(f, tr('分隔符'), self._bind_combo("merge_separator", sep), adv=True)
        self._row(f, tr('未唱部分亮度'), self._bind_value("part_dim", SliderSpin(10, 100, 1, 0, " %"), 100), adv=True,
                  tip=tr('合并行中当前没在唱的那几句的亮度，用来区分正在唱的是哪一句'))

    def _build_output(self):
        box, f = self._section(tr('视频输出'))
        self.quality = QComboBox()
        for name, qp in QUALITY:
            self.quality.addItem(name, qp)
        self.quality.addItem(tr('自定义'), -1)
        self.quality.currentIndexChanged.connect(self._quality_changed)
        self._row(f, tr('画质'), self.quality, tip=tr('H.264 固定量化（CQP）编码：画面几乎不动的提词器视频体积会非常小'))
        qp = QSpinBox()
        qp.setRange(0, 51)
        qp.setToolTip(tr('数值越小画质越好、文件越大。18 接近无损，22 推荐，28 以上文字边缘会有毛刺'))
        self.qp_spin = self._bind_value("qp", qp, cast=int)
        self.qp_spin.valueChanged.connect(lambda _: self._sync_quality())
        self._row(f, tr('QP 值'), self.qp_spin, adv=True)
        self.enc_combo = QComboBox()
        self.enc_combo.addItem(ENCODERS["libx264"], "libx264")
        self._bind_combo("encoder", self.enc_combo)
        self._row(f, tr('编码器'), self.enc_combo, adv=True, tip=tr('显卡编码更快；x264 兼容性最好、文件最小'))
        pr = QComboBox()
        for p in PRESETS_X264:
            pr.addItem(p, p)
        self._row(f, tr('x264 速度'), self._bind_combo("preset", pr), adv=True,
                  tip=tr('对提词器这种静态画面，veryfast 和 slow 体积几乎一样，veryfast 快很多'))
        self._row(f, tr('关键帧间隔'), self._bind_value("keyint", SliderSpin(0.5, 20, 0.5, 1, tr(' 秒'))), adv=True,
                  tip=tr('越大文件越小；越小在播放软件里拖动/跳转越灵敏'))
        ab = QComboBox()
        for name, v in (("AAC 128 kbps", 128), ("AAC 192 kbps", 192), ("AAC 256 kbps", 256),
                        ("AAC 320 kbps", 320), (tr('不包含音频（静音视频）'), 0)):
            ab.addItem(name, v)
        self._row(f, tr('音频'), self._bind_combo("audio_bitrate", ab, int), adv=True)

    # ============================================================ actions
    def _set_bg(self, col: str):
        self.style.bg_color = col
        self.bg_btn.setColor(col)
        self._changed()

    def _res_changed(self, idx: int):
        w, h = self.res_combo.itemData(idx)
        if w:
            self.style.width, self.style.height = w, h
            self.w_spin.blockSignals(True)
            self.h_spin.blockSignals(True)
            self.w_spin.setValue(w)
            self.h_spin.setValue(h)
            self.w_spin.blockSignals(False)
            self.h_spin.blockSignals(False)
            self._changed()
        self._update_custom_res_visibility()

    def _custom_res(self, _=None):
        w = self.w_spin.value() // 2 * 2
        h = self.h_spin.value() // 2 * 2
        self.style.width, self.style.height = w, h
        self._changed()

    def _update_custom_res_visibility(self):
        if not hasattr(self, "res_combo"):
            return
        custom = self.res_combo.currentData() == (0, 0)
        self._canvas_form.setRowVisible(self.custom_res_w, custom)

    def _quality_changed(self, idx: int):
        qp = self.quality.itemData(idx)
        if qp is not None and qp >= 0:
            self.style.qp = int(qp)
            self.qp_spin.blockSignals(True)
            self.qp_spin.setValue(qp)
            self.qp_spin.blockSignals(False)
            self._changed()

    def _sync_quality(self):
        self.quality.blockSignals(True)
        i = self.quality.findData(int(self.style.qp))
        self.quality.setCurrentIndex(i if i >= 0 else self.quality.count() - 1)
        self.quality.blockSignals(False)

    def _encoders_found(self, names: list):
        self.enc_combo.blockSignals(True)
        self.enc_combo.clear()
        for n in names:
            self.enc_combo.addItem(ENCODERS[n], n)
        i = self.enc_combo.findData(self.style.encoder)
        self.enc_combo.setCurrentIndex(i if i >= 0 else 0)
        if i < 0:
            self.style.encoder = "libx264"
        self.enc_combo.blockSignals(False)

    # ---------------------------------------------------------------- fonts
    def _load_fonts(self):
        files = []
        d = paths.fonts_dir()
        if os.path.isdir(d):
            for ext in ("*.ttf", "*.otf", "*.ttc", "*.otc"):
                files += glob.glob(os.path.join(d, ext))
        if self.style.font_file and os.path.isfile(self.style.font_file):
            files.append(self.style.font_file)
        for fp in files:
            QFontDatabase.addApplicationFont(fp)
        self._refresh.append(self._refresh_font)

    def _refresh_font(self):
        fam = self.style.font_family
        if fam not in QFontDatabase.families():
            for alt in ("Microsoft YaHei", tr('微软雅黑'), "SimHei", "Arial"):
                if alt in QFontDatabase.families():
                    fam = alt
                    break
            self.style.font_family = fam
        self.font_combo.blockSignals(True)
        from PySide6.QtGui import QFont
        self.font_combo.setCurrentFont(QFont(fam))
        self.font_combo.blockSignals(False)
        self._fill_weights(fam, self.style.font_style)

    def _fill_weights(self, family: str, prefer: str = ""):
        styles = QFontDatabase.styles(family) or ["Regular"]
        self.weight_combo.blockSignals(True)
        self.weight_combo.clear()
        for s in styles:
            cn = STYLE_CN.get(s.lower().replace(" ", ""), "")
            self.weight_combo.addItem(tr('{p0}  {p1}', p0=cn, p1=s) if cn and language() != "en" else s, s)
        pick = prefer if prefer in styles else next((s for s in STRONG_STYLES if s in styles), styles[0])
        self.weight_combo.setCurrentIndex(max(0, self.weight_combo.findData(pick)))
        self.weight_combo.blockSignals(False)
        if self.style.font_style != pick:
            self.style.font_style = pick
            self._changed()

    def _font_changed(self, font):
        fam = font.family()
        self.style.font_family = fam
        self._fill_weights(fam, self.style.font_style)
        self._changed()

    def _weight_changed(self, idx: int):
        d = self.weight_combo.itemData(idx)
        if d:
            self.style.font_style = d
            self._changed()

    def _load_font_file(self):
        fp, _ = QFileDialog.getOpenFileName(self, tr('选择字体文件'), "", tr('字体 (*.ttf *.otf *.ttc *.otc)'))
        if not fp:
            return
        fid = QFontDatabase.addApplicationFont(fp)
        fams = QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
        if not fams:
            QMessageBox.warning(self, tr('无法加载'), tr('这个字体文件无法使用。'))
            return
        self.style.font_file = fp
        self.style.font_family = fams[0]
        self.style.font_style = ""
        self._refresh_font()
        self._changed()

    # ---------------------------------------------------------------- files
    def _pick_audio(self):
        start = os.path.dirname(self.audio_path) if self.audio_path else ""
        fp, _ = QFileDialog.getOpenFileName(self, tr('选择音频'), start, tr('音频 ({p0});;所有文件 (*.*)', p0=AUDIO_EXTS))
        if fp:
            self.load_audio(fp)

    def _pick_lyrics(self):
        start = os.path.dirname(self.lyrics_path or self.audio_path) if (self.lyrics_path or self.audio_path) else ""
        fp, _ = QFileDialog.getOpenFileName(self, tr('选择歌词'), start, LYRIC_FILTER)
        if fp:
            self.load_lyrics_file(fp)

    def _pick_output(self):
        cur = self.out_edit.text().strip() or self._default_out()
        fp, _ = QFileDialog.getSaveFileName(self, tr('保存视频'), cur, tr('MP4 视频 (*.mp4);;MOV 视频 (*.mov);;MKV 视频 (*.mkv)'))
        if fp:
            self.out_edit.setText(fp)
            self._out_auto = False
            self._save_timer.start()

    def _default_out(self) -> str:
        if not self.audio_path:
            return ""
        base = os.path.splitext(self.audio_path)[0]
        return base + tr('_提词器.mp4')

    def load_audio(self, fp: str, quiet: bool = False):
        self.player.stop()
        self.audio_path = fp
        self.audio_edit.setText(fp)
        self.audio_meta.setText("")
        self.audio_info = None
        self.align.set_audio(fp)
        self._update_project()
        if self._out_auto or not self.out_edit.text().strip():
            self.out_edit.setText(self._default_out())
            self._out_auto = True
        if self._audio_worker is not None:
            self._audio_worker.cancel()
        w = AudioLoadWorker(fp, self)
        w.loaded.connect(self._audio_loaded)
        w.failed.connect(lambda m: QMessageBox.warning(self, tr('音频'), m))
        self._audio_worker = w
        w.start()
        self.statusBar().showMessage(tr('正在读取音频…'))
        self._save_timer.start()
        # a lyric file next to the song with the same name: offer it
        if not self.lyrics_path and not quiet:
            base = os.path.splitext(fp)[0]
            for ext in (".lrc", ".srt", ".vtt", ".ass", ".txt"):
                if os.path.isfile(base + ext):
                    self.load_lyrics_file(base + ext)
                    break

    def _audio_loaded(self, info, pcm, peaks):
        if self.sender() is not self._audio_worker:
            return
        self.audio_info = info
        self.player.set_audio(pcm, 48000)
        self.timeline.set_audio(info.duration, peaks, 100)
        self.audio_meta.setText(fmt_time(info.duration, False))
        self.statusBar().showMessage(tr('音频已载入：{p0}  时长 {p1}', p0=os.path.basename(info.path), p1=fmt_time(info.duration)), 6000)
        self._update_info()

    def load_lyrics_file(self, fp: str, quiet: bool = False):
        try:
            doc = load_lyrics(fp, self.style.join_same_time)
        except Exception as e:
            QMessageBox.warning(self, tr('歌词'), tr('无法读取歌词文件：{p0}', p0=e))
            return
        if not doc.lines:
            QMessageBox.warning(self, tr('歌词'), tr('这个文件里没有找到歌词。'))
            return
        if not self._confirm_lyric_changes():
            return
        self.lyrics_path = fp
        self.lyr_edit.setText(fp)
        self.lines = doc.lines
        self.lines_timed = doc.timed
        self._reset_lyric_history()
        self.align.set_texts([ln.text.replace("\n", " ") for ln in doc.lines])
        fmt = doc.fmt.upper()
        if doc.timed:
            self._set_lyr_state(tr('✓ {p0} 歌词，共 {p1} 句', p0=fmt, p1=len(doc.lines)) +
                                tr('，已带时间轴，可以直接进入下一步。'), ok=True)
        else:
            self._set_lyr_state(tr('⚠ 这是纯文本歌词（{p0} 行），没有时间轴。请点击「开始识别」自动对轴。', p0=len(doc.lines)), ok=False)
        self._t_user = False
        self._entries_sig = None
        self._rebuild()
        self._save_timer.start()
        if not doc.timed and not quiet and self.audio_path and self.pages.currentIndex() == 1:
            r = QMessageBox.question(self, tr('没有时间轴'), tr('这个歌词文件没有时间轴，现在自动识别吗？'))
            if r == QMessageBox.StandardButton.Yes:
                self._go_step(0)

    def _set_lyr_state(self, text: str, ok: bool):
        self.lyr_state.setText(text)
        self.lyr_state.setObjectName("okbox" if ok else "warnbox")
        self.lyr_state.style().unpolish(self.lyr_state)
        self.lyr_state.style().polish(self.lyr_state)
        self.lyr_state.setVisible(True)

    def _open_align(self):
        """Back to step 1 with the current (possibly edited) lines as the text to align."""
        if not self._flush_lyric_draft():
            return
        if self.lines:
            self.align.set_texts([ln.text.replace("\n", " ") for ln in self.lines])
        self._go_step(0)

    def _apply_aligned(self, lines: list):
        saved = getattr(self.sender(), "saved_path", "") if self.sender() else ""
        if not self._confirm_lyric_changes():
            return
        self.lines = lines
        self.lines_timed = True
        if not saved:
            # the requirement is to *generate* an lrc/srt: write one next to the
            # lyric text (never overwriting an existing file)
            plain = self.lyrics_path and os.path.splitext(self.lyrics_path)[1].lower() == ".txt"
            base = os.path.splitext(self.lyrics_path if plain else self.audio_path or self.lyrics_path)[0]
            cand = base + ".lrc"
            k = 1
            while os.path.exists(cand):
                cand = tr('{p0}_自动识别{p1}.lrc', p0=base, p1='' if k == 1 else k)
                k += 1
            try:
                save_lyrics(lines, cand)
                saved = cand
            except OSError:
                saved = ""
        if saved:
            self.lyrics_path = saved
            self.lyr_edit.setText(saved)
        self._reset_lyric_history(saved=bool(saved))
        self._set_lyr_state(tr('✓ 自动识别的时间轴，共 {p0} 句', p0=len(lines)) +
                            (tr('，已保存为 {p0}', p0=os.path.basename(saved)) if saved else tr('（请点「另存歌词」保存）')), ok=True)
        self._t_user = False
        self._entries_sig = None
        self._rebuild()
        self._save_timer.start()
        self._go_step(1)

    def _save_lyrics_as(self):
        if not self._flush_lyric_draft():
            return False
        if not self.lines or not self.lines_timed:
            QMessageBox.information(self, tr('另存歌词'), tr('当前没有带时间轴的歌词。'))
            return False
        base = os.path.splitext(self.lyrics_path or self.audio_path or "lyrics")[0]
        fp, flt = QFileDialog.getSaveFileName(self, tr('另存歌词'), base + ".lrc", tr('LRC 歌词 (*.lrc);;SRT 字幕 (*.srt)'))
        if not fp:
            return False
        if not os.path.splitext(fp)[1]:
            fp += ".srt" if "srt" in flt.lower() else ".lrc"
        return self._write_lyrics(fp)

    def _write_lyrics(self, fp):
        try:
            save_lyrics(self.lines, fp)
        except OSError as exc:
            QMessageBox.warning(self, tr('保存歌词失败'), str(exc))
            return False
        self.lyrics_path = fp
        self.lyr_edit.setText(fp)
        self._update_project()
        self.statusBar().showMessage(tr('已保存：{p0}', p0=fp), 6000)
        self._save_timer.start()
        self._saved_lyrics = self._lyric_state()
        self._update_lyric_dirty()
        self._sync_lyric_editor()
        return True

    def _save_lyrics_current(self):
        if not self._flush_lyric_draft():
            return False
        if not self.lines_timed:
            self._editor_error(tr('纯文本的时间仍是临时值，请先自动识别时间轴。'))
            return False
        if os.path.splitext(self.lyrics_path)[1].lower() not in (".lrc", ".srt"):
            return self._save_lyrics_as()
        return self._write_lyrics(self.lyrics_path)

    # -------------------------------------------------------------- drag&drop
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        audio_exts = tuple(x.strip("*") for x in AUDIO_EXTS.split())
        for url in e.mimeData().urls():
            fp = url.toLocalFile()
            ext = os.path.splitext(fp)[1].lower()
            if ext in LYRIC_EXTS:
                self.load_lyrics_file(fp)
            elif ext in audio_exts:
                self.load_audio(fp)

    # ============================================================ rebuild
    def _rebuild(self):
        lines = self.lines if self.lines else demo_lines()
        try:
            self.renderer = Renderer(self.style.copy(), lines)
        except Exception as e:
            self.statusBar().showMessage(tr('渲染设置有误：{p0}', p0=e))
            return
        r = self.renderer
        self.preview.set_renderer(r)
        if self.full_preview is not None:
            self.full_preview.set_renderer(r)
        if self.style.auto_size:
            self.size_spin.blockSignals(True)
            self.size_spin.setValue(int(round(r.Fc)))
            self.size_spin.blockSignals(False)
        self.size_spin.setEnabled(not self.style.auto_size)
        if not self.lines:
            self.preview.note = tr('示例歌词 —— 请先选择音频和歌词文件')
        elif not self.lines_timed:
            self.preview.note = tr('纯文本歌词：临时按每行 3 秒显示，请先「自动识别时间轴」')
        else:
            self.preview.note = ""
        sig = tuple((line.start, line.end, line.text) for line in (self.lines or demo_lines()))
        if sig != self._entries_sig:
            self._entries_sig = sig
            self._fill_table()
            if not self._t_user and r.entries:
                k = min(3, len(r.entries) - 1)
                self._t = r.act[k] + r.style.anim_duration + 0.1
        self.timeline.set_entries([(e.start + self.style.time_offset,
                                    (e.end if e.end is not None else (r.entries[i + 1].start if i + 1 < len(r.entries) else e.start + 3)) + self.style.time_offset,
                                    e.merged) for i, e in enumerate(r.entries)])
        self._cur_idx = -2
        self._show_time(self._t)
        self._update_info()

    def _fill_table(self):
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.lines))
        for i, line in enumerate(self.lines):
            self.table.setItem(i, 0, QTableWidgetItem(edit_time(line.start)))
            end = edit_time(line.end) if line.end is not None else edit_time(self._effective_lyric_end(i)) + tr(' 自动')
            self.table.setItem(i, 1, QTableWidgetItem(end))
            self.table.setItem(i, 2, QTableWidgetItem(line.text.replace("\n", " ⏎ ")))
        self.table.blockSignals(False)
        self._sync_lyric_editor()

    def _update_info(self):
        self._update_project()
        r = self.renderer
        if r is None:
            return
        s = self.style
        n_src = len(self.lines)
        n_ent = len(r.entries)
        parts = [tr('输出 {p0}×{p1} · {p2:g} fps', p0=s.width, p1=s.height, p2=s.fps),
                 tr('中间行 {p0:.0f}px / 上下行 {p1:.0f}px', p0=r.Fc, p1=r.Fo)]
        if n_src:
            parts.append(tr('{p0} 句', p0=n_src) + (tr('（合并后 {p0} 行）', p0=n_ent) if n_ent != n_src else ""))
        if self.audio_info:
            parts.append(tr('时长 {p0}', p0=fmt_time(self.audio_info.duration)))
        self.info.setText(join_text("   |   ", parts))

    # ============================================================ playback
    def _duration(self) -> float:
        if self.audio_info:
            return self.audio_info.duration
        r = self.renderer
        if r and r.entries:
            e = r.entries[-1]
            return (e.end or e.start + 3) + 3
        return 30.0

    def toggle_play(self):
        if self.player.playing:
            self.player.stop()
            self._t = self.player.position()
            self._stop_at = None
        else:
            self.player.set_duration(self._duration())
            if self._t >= self._duration() - 0.05:
                self._t = 0.0
            self.player.play(self._t)
            if self.player.error and self.player.data is not None:
                self.statusBar().showMessage(tr('声卡不可用，静音预览：{p0}', p0=self.player.error), 8000)
        self._t_user = True
        self.btn_play.setText(tr('❚❚ 暂停') if self.player.playing else tr('▶ 播放'))

    def audition(self, t0: float, t1: float):
        """Play a range (used by the alignment dialog)."""
        self._t = max(0.0, t0 - 0.4)
        self.player.set_duration(self._duration())
        self.player.play(self._t)
        self._stop_at = t1 + 0.3
        self.btn_play.setText(tr('❚❚ 暂停'))

    def _seek(self, t: float):
        self._t = max(0.0, min(t, self._duration()))
        self._t_user = True
        if self.player.playing:
            self.player.play(self._t)
        self._show_time(self._t)

    def _timeline_seek(self, t: float):
        # An explicit timeline pick must select an editable source line even
        # when automatic playback following has been disabled by a prior edit.
        if not self._flush_lyric_draft():
            return
        self.follow_lyrics.setChecked(False)
        self._stop_at = None
        self._seek(t)
        row = self._lyric_row_at_time(self._t)
        if row >= 0:
            self.table.selectRow(row)
            self.table.scrollToItem(self.table.item(row, 0), QAbstractItemView.ScrollHint.PositionAtCenter)

    def _jump(self, d: int):
        r = self.renderer
        if not r or not r.entries:
            return
        cur = r.current_index(self._t)
        if d < 0 and self._t - r.act[cur] > 1.2 and self.player.playing:
            target = cur
        else:
            target = min(max(cur + d, 0), len(r.entries) - 1)
        if self.player.playing:
            self._seek(max(0.0, r.start[target] - 1.0))
        else:
            self._seek(r.act[target] + r.style.anim_duration + 0.05)

    def _table_clicked(self, row: int, col: int):
        if 0 <= row < len(self.lines):
            self.follow_lyrics.setChecked(False)
            self._seek(self.lines[row].start + self.style.time_offset)

    def _tick(self):
        if self.player.playing:
            t = self.player.position()
            if self._stop_at is not None and t >= self._stop_at:
                self.player.stop()
                self._stop_at = None
            elif t >= self._duration() - 0.01:
                self.player.stop()
                t = self._duration()
            self._t = t
            self._show_time(t)
            if not self.player.playing:
                self.btn_play.setText(tr('▶ 播放'))

    def _show_time(self, t: float):
        self.preview.set_time(t)
        if self.full_preview is not None:
            self.full_preview.set_time(t)
        r = self.renderer
        cur = r.current_index(t) if r else -1
        self.timeline.set_time(t, cur)
        self.time_label.setText(tr('{p0} / {p1}', p0=fmt_time(t), p1=fmt_time(self._duration())))
        self._cur_idx = cur
        self._follow_lyric_time(t)

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Type.ShortcutOverride, QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            if event.key() == Qt.Key.Key_Space and event.modifiers() == Qt.KeyboardModifier.NoModifier:
                focus = QApplication.focusWidget()
                if focus is not None and focus.window() is self and QApplication.activeModalWidget() is None:
                    typing = (isinstance(focus, (QPlainTextEdit, QTextEdit, QAbstractSpinBox)) or
                              focus.inherits("QLineEdit") and not focus.isReadOnly() or
                              focus.inherits("QComboBox") and focus.isEditable())
                    if not typing:
                        if event.type() == QEvent.Type.KeyPress and not event.isAutoRepeat():
                            self.toggle_play()
                        event.accept()
                        return True
        return super().eventFilter(watched, event)

    def keyPressEvent(self, e):
        k = e.key()
        if k == Qt.Key.Key_Left:
            self._seek(self._t - 2.0)
        elif k == Qt.Key.Key_Right:
            self._seek(self._t + 2.0)
        elif k == Qt.Key.Key_Up:
            self._jump(-1)
        elif k == Qt.Key.Key_Down:
            self._jump(1)
        else:
            super().keyPressEvent(e)

    def _full_preview(self):
        if self.full_preview is not None:
            self.full_preview.close()
            return
        fp = FullPreview(self)
        fp.set_renderer(self.renderer)
        fp.set_time(self._t)
        screens = QApplication.screens()
        here = self.screen()
        target = next((s for s in screens if s is not here), here)
        fp.setGeometry(target.geometry())
        fp.showFullScreen()
        fp.setFocus()
        self.full_preview = fp

    # ============================================================== export
    def _export(self):
        if not self._flush_lyric_draft():
            return
        if self._export_worker is not None:
            return
        if not self.audio_path or not os.path.isfile(self.audio_path):
            QMessageBox.warning(self, tr('生成视频'), tr('请先选择音频文件。'))
            return
        if not self.lines:
            QMessageBox.warning(self, tr('生成视频'), tr('请先选择歌词文件。'))
            return
        if not self.lines_timed:
            r = QMessageBox.question(self, tr('生成视频'), tr('歌词还没有时间轴（目前是每行 3 秒的临时时间）。\n先去自动识别时间轴吗？'),
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No |
                                     QMessageBox.StandardButton.Cancel)
            if r == QMessageBox.StandardButton.Yes:
                self._open_align()
                return
            if r != QMessageBox.StandardButton.No:
                return
        out = self.out_edit.text().strip() or self._default_out()
        if not os.path.splitext(out)[1]:
            out += ".mp4"
        self.out_edit.setText(out)
        if os.path.exists(out):
            if QMessageBox.question(self, tr('文件已存在'), tr('{p0}\n已经存在，要覆盖吗？', p0=out)) != QMessageBox.StandardButton.Yes:
                return
        if self.player.playing:
            self.toggle_play()
        w = ExportWorker(self.style.copy(), self._copy_lyric_lines(), self.audio_path, out, self)
        w.progress.connect(self._export_progress)
        w.finished_ok.connect(self._export_done)
        w.failed.connect(self._export_failed)
        self._export_worker = w
        self.btn_export.setEnabled(False)
        self.btn_export.setText(tr('正在生成…'))
        self.btn_export_cancel.setVisible(True)
        self.export_bar.setVisible(True)
        self.export_bar.setValue(0)
        self.export_status.setText(tr('准备中…'))
        w.start()

    def _export_cancel(self):
        if self._export_worker is not None:
            self._export_worker.cancel()
            self.export_status.setText(tr('正在取消…'))

    def _export_progress(self, frac: float, msg: str):
        self.export_bar.setValue(int(frac * 1000))
        self.export_status.setText(msg)

    def _export_reset(self):
        self._export_worker = None
        self.btn_export.setEnabled(True)
        self.btn_export.setText(tr('生成提词器视频'))
        self.btn_export_cancel.setVisible(False)
        self.export_bar.setVisible(False)

    def _export_done(self, res):
        self._export_reset()
        mb = res.size / 1024 / 1024
        self.export_status.setText(
            tr('✓ 已生成 {p0}（{p1:.1f} MB，{p2}，用时 {p3:.0f} 秒）', p0=os.path.basename(res.path), p1=mb, p2=fmt_time(res.duration, False), p3=res.seconds))
        box = QMessageBox(self)
        box.setWindowTitle(tr('完成'))
        box.setText(tr('视频已生成：\n{p0}\n\n大小 {p1:.1f} MB · 时长 {p2} · 共 {p3} 帧（其中 {p4} 帧有变化）', p0=res.path, p1=mb, p2=fmt_time(res.duration, False), p3=res.frames, p4=res.unique_frames))
        b_open = box.addButton(tr('打开所在文件夹'), QMessageBox.ButtonRole.ActionRole)
        b_play = box.addButton(tr('播放视频'), QMessageBox.ButtonRole.ActionRole)
        box.addButton(tr('关闭'), QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is b_open:
            if sys.platform == "win32":
                subprocess.Popen(tr('explorer /select,"{p0}"', p0=os.path.normpath(res.path)))
            else:
                QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(res.path)))
        elif box.clickedButton() is b_play:
            QDesktopServices.openUrl(QUrl.fromLocalFile(res.path))

    def _export_failed(self, msg: str):
        self._export_reset()
        self.export_status.setText(msg)
        if not is_cancelled_message(msg):
            QMessageBox.warning(self, tr('生成视频'), msg)

    # ============================================================ settings
    def _save_settings(self):
        data = {
            "ui_language": self.ui_language,
            "style": self.style.to_dict(),
            "mode": self.mode,
            "align": self.align_cfg,
            "files": {"audio": self.audio_path, "lyrics": self.lyrics_path if self.lines_timed or not self.lines else self.lyrics_path,
                      "out": self.out_edit.text().strip(), "out_auto": self._out_auto},
            "geometry": bytes(self.saveGeometry()).hex(),
        }
        try:
            save_settings(self.settings_file, data)
        except OSError:
            pass

    def closeEvent(self, e):
        if not self._confirm_lyric_changes() or not self.align.cancel_worker():
            e.ignore()
            return
        if self._export_worker is not None:
            if QMessageBox.question(self, tr('正在生成'), tr('视频还在生成中，确定要退出吗？')) != QMessageBox.StandardButton.Yes:
                e.ignore()
                return
            self._export_worker.cancel()
            self._export_worker.wait(5000)
        self.player.stop()
        if self.full_preview is not None:
            self.full_preview.close()
        self._save_settings()
        QApplication.instance().removeEventFilter(self)
        events.changed.disconnect(self._on_ui_language_changed)
        super().closeEvent(e)
