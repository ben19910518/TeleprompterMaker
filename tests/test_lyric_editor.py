"""Exercise the actual editor widgets, history and LRC round trips."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from teleprompter.gui.main_window import MainWindow
from teleprompter.lyrics import LyricLine, load_lyrics, to_lrc, parse_lrc


class EditorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        with patch("teleprompter.gui.main_window.paths.settings_path", return_value=str(self.folder / "settings.json")):
            self.win = MainWindow()
        self.win._tick_timer.stop()
        self.win._save_timer.stop()
        self.win._rebuild_timer.stop()
        self.win.lines = [LyricLine(1, 2.5, "在春天"), LyricLine(3, 4.5, "在夏天"), LyricLine(6, None, "第三句")]
        self.win.lines_timed = True
        self.win.lyrics_path = str(self.folder / "lyrics.lrc")
        self.win._reset_lyric_history()
        self.win.follow_lyrics.setChecked(False)
        self.win._rebuild()
        self.win._go_step(1)
        self.win.table.selectRow(0)

    def tearDown(self):
        self.win._saved_lyrics = self.win._lyric_state()
        self.win._editor_row = -1
        self.win._update_lyric_dirty()
        self.win._probe.wait(10000)
        self.win.close()
        self.temp.cleanup()

    def test_four_nudges_and_history(self):
        w = self.win
        for field, delta, value in (("start", -.05, .95), ("start", .05, 1),
                                    ("end", -.05, 2.45), ("end", .05, 2.5)):
            w._nudge_lyric(field, delta)
            self.assertAlmostEqual(getattr(w.lines[0], field), value)
            self.assertEqual(w.table.currentRow(), 0)
        w._history_lyric(False)
        self.assertAlmostEqual(w.lines[0].end, 2.45)
        w._history_lyric(True)
        self.assertAlmostEqual(w.lines[0].end, 2.5)

    def test_200ms_buttons(self):
        w = self.win
        for field, delta, value in (("start", -200, .8), ("start", 200, 1),
                                    ("end", -200, 2.3), ("end", 200, 2.5)):
            w.lyric_nudge_buttons[(field, delta)].click()
            self.assertAlmostEqual(getattr(w.lines[0], field), value)
        w.show()
        self.app.processEvents()
        fine = w.lyric_nudge_buttons[("start", -50)]
        coarse = w.lyric_nudge_buttons[("start", -200)]
        self.assertEqual(fine.x(), coarse.x())
        self.assertLess(fine.y(), coarse.y())

    def test_space_controls_playback_except_typing(self):
        w = self.win
        w.show()
        w.activateWindow()
        self.app.processEvents()
        with patch.object(w, "toggle_play") as toggle:
            for widget in (w.table, w.lyric_nudge_buttons[("start", -200)], w.follow_lyrics, w.btn_play):
                widget.setFocus()
                self.app.processEvents()
                before = toggle.call_count
                state = w._lyric_state()
                QTest.keyClick(widget, Qt.Key.Key_Space)
                self.assertEqual(toggle.call_count, before + 1)
                self.assertEqual(w._lyric_state(), state)
            w.editor_text.setFocus()
            w.editor_text.setPlainText("hello")
            w.editor_text.moveCursor(w.editor_text.textCursor().MoveOperation.End)
            before = toggle.call_count
            QTest.keyClick(w.editor_text, Qt.Key.Key_Space)
            self.assertEqual(w.editor_text.toPlainText(), "hello ")
            self.assertEqual(toggle.call_count, before)
            w.editor_text.setPlainText(w.lines[w._selected_lyric()].text)
            w.editor_start.setFocus()
            QTest.keyClick(w.editor_start, Qt.Key.Key_Space)
            self.assertEqual(toggle.call_count, before)
            w._sync_lyric_editor()
            font_input = w.font_combo.lineEdit()
            font_input.setFocus()
            self.app.processEvents()
            QTest.keyClick(font_input, Qt.Key.Key_Space)
            self.assertEqual(toggle.call_count, before)

    def test_merged_preview_edits_original_line(self):
        w = self.win
        w.style.merge_short = True
        w._rebuild()
        self.assertEqual(w.table.rowCount(), 3)
        self.assertLess(len(w.renderer.entries), 3)
        w.table.selectRow(1)
        w.editor_text.setPlainText("夏天修改\ntranslation")
        self.assertTrue(w._apply_lyric_fields())
        self.assertEqual(w.lines[1].text, "夏天修改\ntranslation")
        self.assertEqual(w.lines[0].text, "在春天")
        self.assertTrue(w._lyrics_dirty)
        self.assertTrue(w._save_lyrics_current())
        self.assertFalse(w._lyrics_dirty)
        self.assertEqual(load_lyrics(w.lyrics_path).lines[1].text, "夏天修改\ntranslation")

    def test_draft_switch_and_save(self):
        w = self.win
        w.editor_text.setPlainText("未按应用也要保留")
        w.table.selectRow(1)
        self.assertEqual(w.lines[0].text, "未按应用也要保留")
        self.assertEqual(w.table.currentRow(), 1)
        w.editor_text.setPlainText("保存时提交草稿")
        self.assertTrue(w._save_lyrics_current())
        self.assertEqual(load_lyrics(w.lyrics_path).lines[1].text, "保存时提交草稿")

    def test_invalid_times_do_not_mutate(self):
        w = self.win
        state = w._lyric_state()
        for bad in ("-1", "nan", "inf", "3.1", "oops"):
            w.editor_start.setText(bad)
            self.assertFalse(w._apply_lyric_fields())
            self.assertEqual(w._lyric_state(), state)
        w._sync_lyric_editor()
        w.editor_end.setText("3.1")
        self.assertFalse(w._apply_lyric_fields())
        self.assertEqual(w._lyric_state(), state)
        w._sync_lyric_editor()
        w.table.selectRow(2)
        w._nudge_lyric("end", -.05)
        self.assertAlmostEqual(w.lines[2].end, 8.95)

    def test_stamp_offset_insert_delete_undo(self):
        w = self.win
        w.style.time_offset = .5
        w._t = 1.75
        w._stamp_lyric("start")
        self.assertAlmostEqual(w.lines[0].start, 1.25)
        with patch("teleprompter.gui.lyric_editor.QInputDialog.getMultiLineText", return_value=("新增", True)):
            w._insert_lyric()
        self.assertEqual(len(w.lines), 4)
        self.assertEqual(w.lines[1].text, "新增")
        w._delete_lyric()
        self.assertEqual(len(w.lines), 3)
        w._history_lyric(False)
        self.assertEqual(w.lines[1].text, "新增")

    def test_unsaved_cancel_and_failed_save(self):
        w = self.win
        w._nudge_lyric("end", -.05)
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Cancel):
            self.assertFalse(w._confirm_lyric_changes())
        with patch("teleprompter.gui.main_window.save_lyrics", side_effect=OSError("denied")), \
             patch.object(QMessageBox, "warning"):
            self.assertFalse(w._save_lyrics_current())
        self.assertTrue(w._lyrics_dirty)

    def test_short_end_gap_roundtrip(self):
        lines = [LyricLine(1, 2.95, "第一句"), LyricLine(3, None, "第二句")]
        parsed, _ = parse_lrc(to_lrc(lines))
        self.assertAlmostEqual(parsed[0].end, 2.95)

    def test_invalid_draft_can_be_discarded(self):
        self.win.editor_start.setText("invalid")
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Discard):
            self.assertTrue(self.win._confirm_lyric_changes())

    def test_timeline_click_selects_and_edits_highlighted_sentence(self):
        w = self.win
        w.style.merge_short = False
        w._rebuild()
        w.show()
        self.app.processEvents()
        w.editor_text.setPlainText("切换前的草稿")
        timeline = w.timeline
        QTest.mouseClick(timeline, Qt.MouseButton.LeftButton,
                         pos=QPoint(round(timeline._x(3.8)), timeline.height() - 12))
        self.assertEqual(w.lines[0].text, "切换前的草稿")
        self.assertEqual(timeline.current, 1)
        self.assertEqual(w.table.currentRow(), 1)
        self.assertTrue(w.table.item(1, 0).isSelected())
        self.assertEqual(w.editor_text.toPlainText(), "在夏天")
        w.lyric_nudge_buttons[("start", -200)].click()
        w.lyric_nudge_buttons[("end", 50)].click()
        self.assertAlmostEqual(w.lines[1].start, 2.8)
        self.assertAlmostEqual(w.lines[1].end, 4.55)
        self.assertEqual(w.lines[0].start, 1)

    def test_timeline_merged_entry_offset_and_drag_signal(self):
        w = self.win
        w.style.merge_short = True
        w.style.time_offset = .5
        w._rebuild()
        self.assertLess(len(w.renderer.entries), len(w.lines))
        w.timeline.seekRequested.emit(1.8)
        self.assertEqual(w.table.currentRow(), 0)
        w.timeline.seekRequested.emit(3.8)
        self.assertEqual(w.table.currentRow(), 1)
        self.assertEqual(w._lyric_row_at_time(3.8), 1)
        w.lyric_nudge_buttons[("end", -200)].click()
        self.assertAlmostEqual(w.lines[1].end, 4.3)

    def test_timeline_invalid_draft_preserves_selection(self):
        w = self.win
        w.editor_start.setText("invalid")
        old_time = w._t
        w.timeline.seekRequested.emit(7)
        self.assertEqual(w.table.currentRow(), 0)
        self.assertEqual(w._t, old_time)
        w._sync_lyric_editor()


if __name__ == "__main__":
    unittest.main()
