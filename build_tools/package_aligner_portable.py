"""Build an offline portable folder and ZIP; not an application launcher."""
from pathlib import Path
import hashlib,json,shutil,zipfile
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'dist/aligner'  # PyInstaller output of build_tools/LyricAligner.spec
DEST=ROOT/'release/LyricAligner_Portable'
WHEELS=ROOT/'build/aligner-runtime-wheels'

def main():
    if DEST.exists():
        raise SystemExit(f'Refusing to overwrite existing folder: {DEST}')
    wheels=sorted(WHEELS.glob('*.whl'))
    for required in ('nvidia_cublas_cu12-', 'nvidia_cudnn_cu12-', 'nvidia_cuda_runtime_cu12-'):
        if not any(p.name.startswith(required) for p in wheels):
            raise SystemExit(f'Missing runtime wheel: {required}')
    shutil.copytree(SOURCE,DEST,ignore=shutil.ignore_patterns('models.path','使用说明.md','settings.json','error.log','__pycache__'))
    shutil.copytree(ROOT/'models/large-v3-turbo',DEST/'models/large-v3-turbo')
    (DEST/'models.path').write_text('models\n',encoding='utf-8')
    shutil.copy2(ROOT/'build_tools/ALIGNER_PORTABLE_README.txt',DEST/'使用说明.txt')
    shutil.copy2(ROOT/'build_tools/ALIGNER_CLI_README.txt',DEST/'命令行使用说明.txt')
    cuda=DEST/'cuda';cuda.mkdir()
    runtime=[]
    for wheel in wheels:
        runtime.append(dict(wheel=wheel.name,sha256=hashlib.file_digest(wheel.open('rb'),'sha256').hexdigest()))
        with zipfile.ZipFile(wheel) as z:
            for name in z.namelist():
                p=Path(name)
                if name.endswith('/'):
                    continue
                if p.suffix.lower()=='.dll':
                    target=cuda/p.name
                elif any(t in name.lower() for t in ('license','copying','notice')):
                    target=DEST/'licenses'/wheel.stem/p.name
                else:
                    continue
                target.parent.mkdir(parents=True,exist_ok=True)
                with z.open(name) as src,target.open('wb') as dst:shutil.copyfileobj(src,dst)
    # Replace the tiny DLL shipped with CTranslate2 with the complete cuDNN DLL.
    shutil.copy2(cuda/'cudnn64_9.dll',DEST/'_internal/ctranslate2/cudnn64_9.dll')
    files=[]
    for p in sorted(DEST.rglob('*')):
        if p.is_file():
            with p.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
            files.append(dict(path=p.relative_to(DEST).as_posix(),bytes=p.stat().st_size,sha256=digest))
    manifest=dict(created='2026-10-23',model='large-v3-turbo',runtime_sources=runtime,total_bytes=sum(f['bytes'] for f in files),files=files)
    (DEST/'打包清单.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    archive=DEST.with_suffix('.zip')
    if archive.exists():raise SystemExit(f'Archive already exists: {archive}')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=1,allowZip64=True) as z:
        for p in sorted(DEST.rglob('*')):
            if p.is_file():z.write(p,p.relative_to(DEST.parent))
    print(json.dumps(dict(directory=str(DEST),zip=str(archive),files=len(files)+1,total_bytes=manifest['total_bytes'],zip_bytes=archive.stat().st_size),ensure_ascii=False),flush=True)
if __name__=='__main__':main()
