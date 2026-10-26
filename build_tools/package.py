"""Assemble the portable release after PyInstaller.

  .venv\\Scripts\\python.exe build_tools\\package.py

- removes runtime leftovers (settings.json, error.log) from dist
- adds README.txt (UTF-8 with BOM so Notepad shows it), empty models/ and fonts/
- writes release/TeleprompterMaker_v<ver>.zip WITHOUT any downloaded model
- optionally (--with-model) copies the dev model into dist for offline use
"""
import os
import shutil
import sys
import zipfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
from teleprompter import __version__  # noqa: E402

DIST = os.path.join(ROOT, "dist", "TeleprompterMaker")
REL = os.path.join(ROOT, "release")


def main():
    if not os.path.isfile(os.path.join(DIST, "TeleprompterMaker.exe")):
        raise SystemExit("dist not built")
    for f in ("settings.json", "settings.json.tmp", "error.log"):
        p = os.path.join(DIST, f)
        if os.path.exists(p):
            os.remove(p)
    with open(os.path.join(ROOT, "build_tools", "README.txt"), encoding="utf-8") as fh:
        readme = fh.read()
    with open(os.path.join(DIST, "README.txt"), "w", encoding="utf-8-sig", newline="\r\n") as fh:
        fh.write(readme)
    for name in ("README_en.txt", "README_ja.txt"):
        with open(os.path.join(ROOT, "build_tools", name), encoding="utf-8") as fh:
            localized_readme = fh.read()
        with open(os.path.join(DIST, name), "w", encoding="utf-8-sig", newline="\r\n") as fh:
            fh.write(localized_readme)
    os.makedirs(os.path.join(DIST, "models"), exist_ok=True)
    os.makedirs(os.path.join(DIST, "fonts"), exist_ok=True)
    with open(os.path.join(DIST, "fonts", "README.txt"), "w", encoding="utf-8-sig") as fh:
        fh.write("把 .ttf / .otf / .ttc 字体文件放进这个文件夹，程序启动时会自动加载，不需要安装到系统。\r\n")
    with open(os.path.join(DIST, "models", "README.txt"), "w", encoding="utf-8-sig") as fh:
        fh.write("自动识别时间轴用的模型会下载到这个文件夹。\r\n"
                 "已经下载过的电脑可以把整个 models 文件夹拷过来，就不用再下载。\r\n")

    os.makedirs(REL, exist_ok=True)
    zpath = os.path.join(REL, f"TeleprompterMaker_v{__version__}.zip")
    if os.path.exists(zpath):
        os.remove(zpath)
    n = 0
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for base, dirs, files in os.walk(DIST):
            rel_base = os.path.relpath(base, os.path.dirname(DIST))
            parts = rel_base.split(os.sep)
            if len(parts) >= 3 and parts[1] == "models":     # never ship a downloaded model
                continue
            if len(parts) >= 2 and parts[1] == "cuda":
                continue
            for f in files:
                if len(parts) == 2 and parts[1] == "models" and not f.endswith(".txt"):
                    continue
                z.write(os.path.join(base, f), os.path.join(rel_base, f))
                n += 1
    print(f"zip: {zpath}  files={n}  size={os.path.getsize(zpath) / 1e6:.1f} MB")

    if "--with-model" in sys.argv:
        src = os.path.join(ROOT, "models")
        for key in os.listdir(src) if os.path.isdir(src) else []:
            s, d = os.path.join(src, key), os.path.join(DIST, "models", key)
            if os.path.isdir(s) and not os.path.isdir(d):
                # hard links: no extra disk space, and a later rebuild that wipes
                # dist only removes the extra names, never the dev copy
                shutil.copytree(s, d, copy_function=_link_or_copy)
                print("model linked:", d)


def _link_or_copy(src, dst):
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


if __name__ == "__main__":
    main()
