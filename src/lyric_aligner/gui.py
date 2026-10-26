"""Reuse the existing correction dialog; standalone audio/text picker."""
from pathlib import Path
import sys

def main(args):
    from PySide6.QtWidgets import QApplication,QFileDialog
    from PySide6.QtCore import QTimer
    from teleprompter.gui.align_dialog import AlignDialog
    app=QApplication.instance() or QApplication(sys.argv[:1])
    audio=args.audio
    if not audio:audio,_=QFileDialog.getOpenFileName(None,'选择待对轴音频','','音频 (*.wav *.mp3 *.flac *.m4a *.ogg)')
    if not audio:return 0
    text=args.text

    import sounddevice as sd
    import threading
    from .media import decode_audio
    preview={'audio':None,'error':None};closed=threading.Event()
    def prepare():
        try:preview['audio']=decode_audio(audio,48000,2)
        except Exception as exc:preview['error']=str(exc)
    if not args.smoke_test:threading.Thread(target=prepare,daemon=True).start()
    timer=QTimer();timer.setSingleShot(True);timer.timeout.connect(sd.stop)
    def audition(start,end):
        if preview['audio'] is None:
            dialog.status.setText(preview['error'] or '正在准备试听音频，请稍后');return
        block=preview['audio'][max(0,int(start*48000)):max(0,int(end*48000))]
        sd.stop();sd.play(block,48000);timer.start(max(100,round((end-start)*1000)))
    dialog=AlignDialog(None,audio,Path(text).read_text('utf-8-sig').splitlines() if text else [],audition=audition)
    dialog.setWindowTitle('Lyric Aligner · 歌词自动对轴与校对')
    if args.out:
        from teleprompter.lyrics import save_lyrics
        def apply(lines):
            Path(args.out).parent.mkdir(parents=True,exist_ok=True);save_lyrics(lines,args.out)
        dialog.applied.connect(apply);dialog.btn_apply.setText('保存并返回 LMT')
    else:dialog.btn_apply.hide()
    if args.smoke_test:
        QTimer.singleShot(1200,dialog.reject)
    dialog.exec();closed.set();sd.stop();return 0
