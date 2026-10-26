Teleprompter Maker v1.3.0 — portable Windows edition

Extract the entire folder, then double-click TeleprompterMaker.exe.
Keep _internal with the executable. No Python installation is required.

INTERFACE LANGUAGE
Settings > Interface language… offers Follow system, 简体中文, English, and 日本語.
The default is Follow system: Chinese for Chinese systems, Japanese for Japanese systems,
and English for all other system languages. Manual choices are remembered.
Changes apply immediately and preserve lyrics, edit drafts, fonts and playback position.
Interface language and the recognition language in Auto-align lyrics are independent.

QUICK START
The step bar at the top ("① Import and align › ② Format and fine-tune") switches between the two steps.
Step 1 — Import and align
1. Select an audio file (MP3, WAV, FLAC, M4A, etc.), or drag it into the window.
2. Paste or type the lyrics (one phrase per line), or use Import file… for TXT/LRC/SRT.
3. Click Start alignment (download a model if needed), review the result, then Apply and continue.
   Lyrics that are already timed (LRC/SRT) can skip this with "Already timed, next step".
Step 2 — Format and fine-tune
4. Adjust the layout and preview the result. Space plays or pauses outside text/time input fields.
5. Select a source line in the list or timeline. Use Start/End ±50ms or ±200ms to adjust it.
   Edit the text or times, then Apply changes. Switching lines or saving also commits the draft.
6. Save lyrics with Ctrl+S, or use Save lyrics as to export LRC/SRT. Undo/Redo is available.
7. Choose an output path and click Export teleprompter video.

EDITING NOTES
The list always shows source lines, even when the preview merges short phrases.
Displayed editing times exclude the global preview offset. A blank end time is inferred automatically.
Use Set start here / Set end here to stamp the current playback position.
Time values must stay non-negative and ordered; a line cannot end after the next line starts.
Review estimated lines before exporting. Preview timing does not guarantee recognition accuracy.

FILES AND MODELS
This standard release includes application components and translations, but no downloaded speech model
or CUDA runtime libraries. Auto-alignment models are stored under models; copy that entire folder
from an existing installation for offline use. CUDA DLLs may be placed in a cuda folder next to the EXE.
Compatible NVIDIA drivers must be installed on the target machine. CPU fallback is automatic.
Put optional font files in fonts. Settings and the language preference are stored in settings.json.
If an error occurs, include the error.log file when reporting it.
