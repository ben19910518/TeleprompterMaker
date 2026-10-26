"""Package the audited Windows runtime with notices and matching source archives.

Run from the project root after preparing build/distribution-compliance/sources
and build/public-runtime-r1/TeleprompterMaker. Existing releases are preserved.
Downloaded source code is never executed by this script.
"""
from pathlib import Path, PurePosixPath
import argparse, hashlib, importlib.metadata as metadata, json, re, shutil, tarfile, zipfile

def sha(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,default=Path.cwd())
    args=parser.parse_args(); root=args.root.resolve()
    work=root/'build/distribution-compliance'; runtime=root/'build/public-runtime-r1/TeleprompterMaker'
    public=root/'build/public-release-source'; sources=work/'sources'
    assert (runtime/'TeleprompterMaker.exe').is_file()
    assert (public/'LICENSE').is_file()
    manifest=json.loads((work/'release-source-manifest.json').read_text('utf-8'))
    notice_dir=runtime/'licenses';notice_dir.mkdir(exist_ok=True)
    index=[]

    def save_notice(component,origin,data):
        if not data or len(data)>2_000_000 or b'\0' in data:return
        component=re.sub(r'[^A-Za-z0-9_.-]','_',component)
        base=re.sub(r'[^A-Za-z0-9_.-]','_',PurePosixPath(origin).name)[:90]
        digest=hashlib.sha256(data).hexdigest()
        rel=f'{component}/{digest[:12]}-{base}'
        target=notice_dir/rel;target.parent.mkdir(exist_ok=True);target.write_bytes(data)
        index.append(dict(component=component,original_path=origin,file=rel,sha256=digest))

    # Original license/copyright files from the exact installed Python packages.
    components=[]
    for d in metadata.distributions():
        name=d.metadata['Name']
        if name.lower() in {'pip','setuptools','onnxruntime','hf-xet'}:continue
        components.append(dict(name=name,version=d.version,license=d.metadata.get('License-Expression') or d.metadata.get('License'),project_urls=d.metadata.get_all('Project-URL') or []))
        for f in d.files or []:
            base=PurePosixPath(str(f).replace('\\','/')).name.lower()
            if any(s in base for s in ['license','copying','notice','copyright']) and not base.endswith('.pyc'):
                path=Path(d.locate_file(f))
                if path.is_file():save_notice(name,str(f).replace('\\','/'),path.read_bytes())

    # Upstream native-library and transitive Rust/C++ notices, including Qt's
    # third-party attribution records. Keep source archives intact separately.
    for entry in manifest['sources']:
        archive=sources/entry['file']
        if sha(archive)!=entry['sha256']:raise ValueError(f'Source checksum changed: {archive.name}')
        with tarfile.open(archive,'r:*') as tar:
            for m in tar:
                if not m.isfile() or m.size>2_000_000:continue
                parts=PurePosixPath(m.name).parts
                if '..' in parts:raise ValueError('Unsafe archive member')
                base=parts[-1].lower()
                if any(k in base for k in ['license','copying','notice','copyright','authors','qt_attributions']):
                    if not base.endswith(('.png','.jpg','.gif','.svg','.pyc','.pdf')):
                        save_notice(entry['name'],m.name,tar.extractfile(m).read())
    for p in (work/'extra-licenses').rglob('*'):
        if p.is_file():save_notice('supplemental',p.relative_to(work/'extra-licenses').as_posix(),p.read_bytes())

    (notice_dir/'INDEX.json').write_text(json.dumps(index,ensure_ascii=False,indent=2),'utf-8')
    (runtime/'INSTALLED_COMPONENTS.json').write_text(json.dumps(components,ensure_ascii=False,indent=2),'utf-8')
    (runtime/'SOURCE_MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),'utf-8')
    for name in ['LICENSE','COPYRIGHT','THIRD_PARTY_NOTICES.md']:
        shutil.copy2(public/name,runtime/name)
    (runtime/'docs').mkdir(exist_ok=True)
    for name in ['USER_GUIDE.md','DISTRIBUTION.md']:
        shutil.copy2(public/'docs'/name,runtime/'docs'/name)
    shutil.copytree(public/'docs/images',runtime/'docs/images',dirs_exist_ok=True)
    for locale in ['ja','zh_CN']:
        name='qtbase_'+locale+'.qm'
        shutil.copy2(root/'src/teleprompter/resources/i18n'/name,runtime/'_internal/teleprompter/resources/i18n'/name)
    (runtime/'README.txt').write_text('Teleprompter Maker v1.3.0 — Windows x64\n\n完整解压后双击 TeleprompterMaker.exe，不需要启动脚本或另装 Python。\n详细使用手册：docs/USER_GUIDE.md\n发行、源码与重建说明：docs/DISTRIBUTION.md\n项目许可：LICENSE；第三方声明：THIRD_PARTY_NOTICES.md；许可原文：licenses/\n\n标准包不含模型、CUDA/cuDNN 运行库和 ASIO 扩展。CPU 对轴与常规音频播放可直接使用。\n模型首次下载后可离线使用。NVIDIA 对轴加速需要用户另行配置兼容的运行库。\n\n源码和配套源码包：https://github.com/ben19910518/TeleprompterMaker/releases/tag/v1.3.0\n','utf-8-sig')

    inventory=[]
    for p in sorted(runtime.rglob('*')):
        if p.is_file() and p.suffix.lower() in {'.dll','.pyd','.exe'}:
            inventory.append(dict(file=p.relative_to(runtime).as_posix(),sha256=sha(p),size=p.stat().st_size))
    (runtime/'BINARY_INVENTORY.json').write_text(json.dumps(inventory,indent=2),'utf-8')
    assert not list(runtime.rglob('cudnn*.dll'))
    assert not list(runtime.rglob('*-asio.dll'))
    assert not (runtime/'settings.json').exists()
    assert not list((runtime/'models').rglob('model.bin'))

    output=root/'release';output.mkdir(exist_ok=True)
    zip_path=output/'TeleprompterMaker_v1.3.0_Windows_x64.zip'
    with zipfile.ZipFile(zip_path,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(runtime.rglob('*')):
            if p.is_file():z.write(p,'TeleprompterMaker/'+p.relative_to(runtime).as_posix())
    companion=output/'TeleprompterMaker_v1.3.0_ThirdPartySources.zip'
    with zipfile.ZipFile(companion,'w',zipfile.ZIP_STORED) as z:
        for e in manifest['sources']:z.write(sources/e['file'],'sources/'+e['file'])
        for p in [runtime/'SOURCE_MANIFEST.json',runtime/'BINARY_INVENTORY.json',runtime/'INSTALLED_COMPONENTS.json',public/'docs/DISTRIBUTION.md',public/'LICENSE',public/'COPYRIGHT',public/'THIRD_PARTY_NOTICES.md']:
            z.write(p,p.name)
        for p in notice_dir.rglob('*'):
            if p.is_file():z.write(p,'licenses/'+p.relative_to(notice_dir).as_posix())
        for name in ['lamer-source-provenance.json','intel-openmp-origin.json','ffmpeg-runtime.json']:
            z.write(work/name,'provenance/'+name)
        for p in public.rglob('*'):
            if p.is_file() and '.git' not in p.relative_to(public).parts:
                z.write(p,'ApplicationSource/'+p.relative_to(public).as_posix())
    for path in [zip_path,companion]:
        with zipfile.ZipFile(path) as z:
            bad=z.testzip()
            if bad:raise ValueError(f'ZIP CRC failure: {bad}')
        digest=sha(path);path.with_suffix('.zip.sha256').write_text(digest+'  '+path.name+'\n','ascii')
        print(json.dumps(dict(file=str(path),size=path.stat().st_size,sha256=digest),ensure_ascii=False))
    print('Notices:',len(index),'native binary records:',len(inventory),'source archives:',len(manifest['sources']))

if __name__=='__main__':main()
