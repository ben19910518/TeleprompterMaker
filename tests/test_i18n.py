"""Language defaults, live switching, persistence and user-data regression tests."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from PySide6.QtCore import QCoreApplication, QLocale
from PySide6.QtWidgets import QApplication, QMessageBox
from teleprompter.i18n import resolve_language, set_language, tr, language, is_cancelled_message
from teleprompter.gui.main_window import MainWindow
from teleprompter.gui.align_dialog import AlignDialog
from teleprompter.gui.i18n_widgets import QLabel
from teleprompter.lyrics import LyricLine
from lyric_aligner.align import AlignedLine


class LanguageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.settings = Path(self.temp.name)/'settings.json'
        self.settings.write_text(json.dumps({'ui_language':'zh'}), 'utf-8')
        with patch('teleprompter.gui.main_window.paths.settings_path', return_value=str(self.settings)):
            self.win = MainWindow()
        self.win._tick_timer.stop()
        self.win._save_timer.stop()
        self.win._rebuild_timer.stop()

    def tearDown(self):
        self.win._probe.wait(10000)
        self.win._saved_lyrics = self.win._lyric_state()
        self.win._editor_row = -1
        self.win._update_lyric_dirty()
        self.win.close()
        set_language('zh')
        self.temp.cleanup()

    def test_system_and_manual_defaults(self):
        for system, expected in [('zh_CN','zh'),('zh-TW','zh'),('zh-Hans-CN','zh'),
                                 ('ja_JP','ja'),('en_US','en'),('fr_FR','en'),('ko_KR','en'),('','en')]:
            self.assertEqual(resolve_language('auto', system), expected)
            self.assertEqual(resolve_language('ja', system), 'ja')

    def test_live_switch_preserves_draft_selection_and_player(self):
        w = self.win
        w.lines = [LyricLine(1, 2.5, '开始'), LyricLine(3, None, '日本語 English 中文')]
        w.lines_timed = True
        w._reset_lyric_history()
        w.follow_lyrics.setChecked(False)
        w._rebuild()
        w.table.selectRow(0)
        w._t = 1.7
        w.editor_text.setPlainText('还没有应用的歌词 draft')
        w.editor_start.setText('1.234')
        before = w._lyric_state()
        style_before = w.style.to_dict()
        for code, button, header, menu in [('en','▶ Play','Start','Settings'),
                                          ('ja','▶ 再生','開始','設定'),('zh','▶ 播放','开始','设置')]:
            w._set_ui_language(code)
            self.assertEqual(w.btn_play.text(), button)
            self.assertEqual(w.table.horizontalHeaderItem(0).text(), header)
            self.assertEqual(w.settings_menu.title(), menu)
            self.assertEqual(w.editor_text.toPlainText(), '还没有应用的歌词 draft')
            self.assertEqual(w.editor_start.text(), '1.234')
            self.assertEqual(w.table.item(0, 2).text(), '开始')
            self.assertEqual(w._lyric_state(), before)
            self.assertEqual(w.style.to_dict(), style_before)
            self.assertEqual(w.table.currentRow(), 0)
            self.assertEqual(w._t, 1.7)

    def test_manual_language_is_saved_and_restored(self):
        self.win._set_ui_language('ja')
        self.assertEqual(json.loads(self.settings.read_text('utf-8'))['ui_language'], 'ja')
        with patch('teleprompter.gui.main_window.paths.settings_path', return_value=str(self.settings)), \
             patch('teleprompter.i18n.QLocale.system', return_value=QLocale('fr_FR')):
            other = MainWindow()
        try:
            self.assertEqual(language(), 'ja')
            self.assertEqual(other.btn_play.text(), '▶ 再生')
        finally:
            other._probe.wait(10000)
            other.close()

    def test_auto_uses_system_language_including_english_fallback(self):
        self.win._probe.wait(10000)
        for system, expected in [('ja_JP','ja'),('zh_TW','zh'),('de_DE','en')]:
            with patch('teleprompter.i18n.QLocale.system', return_value=QLocale(system)):
                self.win._set_ui_language('auto')
            self.assertEqual(language(), expected)
            self.assertEqual(json.loads(self.settings.read_text('utf-8'))['ui_language'], 'auto')

    def test_recognition_language_and_result_data_remain_stable(self):
        dialog = AlignDialog(self.win, 'song.wav', ['開始'], settings={'align_lang':'日语'})
        dialog.result = [AlignedLine('用户歌詞', 1, 2, .3, True)]
        dialog._fill_table()
        for code in ('en', 'ja', 'zh'):
            self.win._set_ui_language(code)
            self.assertEqual(dialog.lang.currentData(), 'ja')
            self.assertEqual(dialog.result[0].score, .3)
            self.assertTrue(dialog.result[0].interpolated)
            self.assertEqual(dialog.table.item(0,3).text(), '用户歌詞')
        dialog.close()

    def test_dynamic_progress_keeps_parameters_and_switches(self):
        set_language('en')
        status = QLabel()
        text = tr('正在识别歌声（{p0}）… {p1}%', p0=tr('显卡加速'), p1=42)
        status.setText(str(text))  # A Qt signal converts Text to str.
        self.assertIn('42%', status.text())
        set_language('ja')
        self.assertIn('GPU高速化', status.text())
        self.assertIn('42%', status.text())
        self.assertNotIn('{p', status.text())
        status.close()

    def test_qt_standard_buttons_are_localized(self):
        for code, expected in [('en','Cancel'),('ja','キャンセル'),('zh','取消')]:
            set_language(code)
            dialog = QMessageBox()
            dialog.setStandardButtons(QMessageBox.StandardButton.Cancel)
            self.assertIn(expected, dialog.button(QMessageBox.StandardButton.Cancel).text().replace('&',''))
            dialog.close()

    def test_queued_cancellation_survives_language_change(self):
        set_language('en')
        cancellation = str(tr('已取消'))
        set_language('ja')
        self.assertTrue(is_cancelled_message(cancellation))

    def test_first_launch_demo_is_localized_without_changing_user_lyrics(self):
        from teleprompter.render import demo_lines
        set_language('en')
        self.assertIn('currently being sung', demo_lines()[1].text)
        self.assertFalse(any('\u3400' <= c <= '\u9fff' for row in demo_lines() for c in row.text))
        set_language('ja')
        self.assertIn('歌詞', demo_lines()[1].text)


if __name__ == '__main__':
    unittest.main()
