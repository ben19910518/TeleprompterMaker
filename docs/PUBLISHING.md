# GitHub 发布与维护说明

更新日期：2026-10-26。

## 1 仓库与许可证

- 仓库：https://github.com/ben19910518/TeleprompterMaker
- 项目许可证：GPL-3.0-only，完整正文见根目录 LICENSE。
- 版权署名：ben19910518 和 TeleprompterMaker contributors；第三方材料保留其原署名。
- 公开版本：v1.3.0，现补充 Windows x64 绿色包与第三方源码附件；运行方法见 README。
- 许可范围、Qt 翻译来源和二进制状态见 THIRD_PARTY_NOTICES.md。

GPL 允许免费及商业使用、修改和再分发；分发时需要遵守对应源码、版权与许可保留等要求。该选择适合本项目公开共享及其 Qt/GPL 兼容依赖，不代表自动解决所有第三方二进制发行义务。参考 [GPLv3 正文](https://www.gnu.org/licenses/gpl-3.0.html)。

## 2 上传清单

包含主程序与 Aligner 入口、src、tests、build_tools、tools、requirements、README、许可证、第三方 Qt 翻译源文件、使用手册与截图。

以下两份内部文档按维护者要求只保留本地，并加入 .gitignore：

- docs/TeleprompterMaker后续功能规划.docx
- docs/提词器生成工具需求文档.txt

.venv、.toolchain、build、dist、release、模型、CUDA、字体、个人设置、日志和凭据不提交。首次提交使用明确的文件清单，不使用未经检查的全目录上传。

## 3 Windows EXE 包

原本地 ZIP 保留。本次新增 Windows_x64.zip、ThirdPartySources.zip 和各自 SHA-256；补齐项目/第三方许可、源文件、原始补丁、重建资料与实际二进制清单，移除未再分发的 cuDNN 和 ASIO 扩展。

完整发行和验证记录见 [DISTRIBUTION.md](DISTRIBUTION.md)。FFmpeg 上游分类补丁造成的许可报告差异、LAME 仓库改名造成的 archive hash 差异均已记录并核实对应源内容。发布附件同时提供运行包和对应源码；不要仅复制旧包或重新生成一个空的 LICENSE 文件作为后续发行流程。

## 4 日常更新

修改代码或文档后，在项目根目录执行：

```powershell
git status --short
git diff
git add <需要提交的文件>
git diff --cached --stat
git commit -m "Describe the change"
git push origin main
```

发布新版时更新 src/teleprompter/__init__.py 中的版本，按构建流程运行测试和验证，创建对应版本标签，在 GitHub Releases 编写说明。不要重用已经公开的版本标签来指向不同代码。

## 5 验证

现有 26 项单元测试通过，文档本地链接已检查。发布前还检查暂存清单、内部文档排除、常见凭据模式与本机路径；这些检查不代替真实音频的人工校对和目标机器兼容性验证。

本次首次源码发布说明见 RELEASE_NOTES_v1.3.0.md。
