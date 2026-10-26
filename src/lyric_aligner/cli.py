"""Standalone CLI. No teleprompter GUI or LMT dependency."""
from __future__ import annotations
import argparse,json,os,sys,time
from pathlib import Path
from dataclasses import asdict

def timestamp(seconds):
    cs=max(0,round(seconds*100));minutes,rem=divmod(cs,6000);sec,cs=divmod(rem,100)
    return f'{minutes:02}:{sec:02}.{cs:02}'

def main(argv=None):
    parser=argparse.ArgumentParser(description='Lyric Aligner — audio + lyrics -> LRC + alignment report')
    parser.add_argument('--audio');parser.add_argument('--text');parser.add_argument('--lang',default='auto');parser.add_argument('--out');parser.add_argument('--json',dest='report');parser.add_argument('--models-dir');parser.add_argument('--model',default='large-v3-turbo');parser.add_argument('--no-refine',action='store_true');parser.add_argument('--enhanced',action='store_true');parser.add_argument('--gui',action='store_true');parser.add_argument('--smoke-test',action='store_true')
    args=parser.parse_args(argv)
    if args.models_dir:os.environ['LYRIC_ALIGNER_MODELS']=args.models_dir
    if args.gui or args.smoke_test or not any((args.audio,args.text,args.out)):
        from .gui import main as gui_main
        return gui_main(args)
    if not all((args.audio,args.text,args.out)):parser.error('--audio, --text and --out are required together')
    started=time.time()
    try:
        from .align import auto_align
        text=Path(args.text).read_text('utf-8-sig');lines=[line.strip() for line in text.splitlines() if line.strip()];trace={}
        def progress(fraction,message):print(json.dumps(dict(event='progress',progress=fraction,message=message),ensure_ascii=False),flush=True)
        result=auto_align(args.audio,lines,args.model,None if args.lang=='auto' else args.lang,not args.no_refine,progress,trace=trace)
        output=[]
        for i,line in enumerate(result):
            body=line.text
            if args.enhanced:
                tokens=[token for token in trace.get('tokens',[]) if token['line']==i]
                # Keep original punctuation/text in normal LRC; detailed recognised tokens are in JSON.
                if tokens and len(tokens)==len(body) and ''.join(t['text'] for t in tokens)==body:
                    body=''.join('<'+timestamp(t['start'])+'>'+t['text'] for t in tokens)
            output.append('['+timestamp(line.start)+']'+body)
        path=Path(args.out);path.parent.mkdir(parents=True,exist_ok=True);temporary=path.with_suffix(path.suffix+'.tmp');temporary.write_text('\n'.join(output)+'\n','utf-8');temporary.replace(path)
        report=dict(schema_version=1,audio=str(Path(args.audio).resolve()),model=args.model,elapsed=time.time()-started,lines=[asdict(line) for line in result],**trace)
        if args.report:
            target=Path(args.report);target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
        print(json.dumps(dict(event='done',out=str(path.resolve()),report=args.report),ensure_ascii=False),flush=True);return 0
    except KeyboardInterrupt:return 130
    except Exception as exc:
        print(json.dumps(dict(event='error',message=str(exc)),ensure_ascii=False),file=sys.stderr,flush=True);return 1

if __name__=='__main__':raise SystemExit(main())
