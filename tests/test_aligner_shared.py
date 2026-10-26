import sys,unittest,tempfile,json
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from lyric_aligner import align
from lyric_aligner.cli import main

class SharedTest(unittest.TestCase):
 def test_identity(self):
  from teleprompter import align as old
  from teleprompter import modelhub as oldhub
  from lyric_aligner import modelhub
  self.assertIs(old,align);self.assertIs(oldhub,modelhub)
 def test_line_alignment(self):
  words=[align.Word(1,2,'你好',1),align.Word(3,4,'世界',1)]
  lines=align.lines_from_alignment(['你好','世界'],words,5)
  self.assertEqual(len(lines),2);self.assertLess(lines[0].start,lines[1].start);self.assertFalse(lines[0].interpolated)
 def test_cli_outputs(self):
  with tempfile.TemporaryDirectory() as folder:
   p=Path(folder);(p/'lyrics.txt').write_text('你好\n世界','utf-8')
   def fake(*args,**kwargs):
    kwargs['trace'].update(words=[],tokens=[],language='zh',duration=5)
    return [align.AlignedLine('你好',1,2,1),align.AlignedLine('世界',3,4,1)]
   with patch.object(align,'auto_align',side_effect=fake):
    self.assertEqual(main(['--audio','voice.wav','--text',str(p/'lyrics.txt'),'--out',str(p/'out.lrc'),'--json',str(p/'report.json'),'--lang','zh']),0)
   self.assertIn('[00:01.00]你好',(p/'out.lrc').read_text('utf-8'));self.assertEqual(len(json.loads((p/'report.json').read_text('utf-8'))['lines']),2)
 def test_shared_models(self):
  from lyric_aligner.paths import models_dir
  with patch.dict('os.environ',{'LYRIC_ALIGNER_MODELS':str(Path.cwd()/'models')}):self.assertEqual(Path(models_dir()),Path.cwd()/'models')

if __name__=='__main__':unittest.main()
