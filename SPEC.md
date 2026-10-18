# Melon Dice 0.2.0 — terminal implementation specification

Author: SamRyong. Python 3.10+. `Melon Dice.txt` is the original screen/behavior reference. The user's later instructions require a genuine TUI and exclude capture, image clipboard, and PDF editing/search/copy/export features from that reference.

## Interface and target environment

`melondice` opens a full-screen prompt_toolkit interface **inside its current terminal**. It does not inspect or require `DISPLAY`, create a graphical window, run a GUI toolkit, launch a browser frontend, or require a desktop. Ordinary interactive SSH is a supported text-UI target. Non-TTY streams and `TERM=dumb` fail with a clear explanation. Recommended minimum: 80×24 cells, VT100-compatible control sequences, UTF-8, Linux/POSIX; primary installation target is Raspberry Pi OS Lite 64-bit.

Home, chat, editor, Options, file picker, information, authentication instructions, and all decisions are terminal widgets. Terminal font size and IME are client-controlled. Mouse reporting is optional and configurable; complete keyboard paths exist. The small-terminal body requests a resize while global controls remain available.

## Navigation, sessions, and clipboard

Home displays Melon Dice, made by SamRyong, the numbered list (1 ChatGPT, 2 pdfViewer, 3 Text editor), the Enter selection, and global/clipboard status. Keys 1–3 immediately replace the selection; the latest valid number wins. Other numbers do not change it. Enter opens the selection or does nothing without one.

Sessions start on first entry and retain their buffers/controllers until explicitly closed. Alt+Tab (Escape+Tab bytes) or F6 cycles Chat → PDF → Editor. At Home it returns to the most recently active app or starts ChatGPT. F1 returns Home; F2 Information; Ctrl+O Options; Ctrl+Q/F10 closes the current app to Home or exits all apps from Home. Closed sessions reopen fresh, while local history/recovery are independent persistence mechanisms.

In-process navigation preserves conversation/draft/attachments/generation/scroll, editor document/dirty state/cursor/selection/undo-redo/scroll, and PDF document/page/zoom/pan. Hidden chat streaming does not force its transcript viewport to the bottom on return. PageDown to the bottom resumes following new output.

A single in-memory text clipboard is shared across text inputs. Successful copy replaces it; failed/empty copy preserves it; paste inserts/replaces selection and does not clear it. Home, switches and per-app closes preserve it; exit clears it. Footers display Empty/Text. No OS clipboard, OSC52 sync, screenshot, Ctrl+P action, or image clipboard exists. Password fields cannot export through copy/cut/kill bindings. PDF copy/document paste are unsupported.

## Terminal input and lifecycle

prompt_toolkit owns alternate-screen/raw input and disables signals/IXON/IXOFF so Ctrl+C, Ctrl+S and Ctrl+Q arrive as keys. An outer POSIX guard restores the initial termios attributes and descriptor flags on normal shutdown and handled failures. SIGINT does not bypass copy/close behavior; SIGTERM requests guarded exit; EOF/SIGHUP use emergency cleanup. Uncatchable termination cannot guarantee recovery/restoration.

Ctrl+I and Tab share a terminal code; Information is F2. Enter is CR, Ctrl+J is LF; F12 is a chat-send fallback for clients that remap Enter. Save As uses F7/Alt+S because Ctrl+Shift+S is not reliably distinct. Alt+Tab may be intercepted; F6 is the default alternate. Escape timeout is configurable. Shift+arrows/mouse selection depend on client support; Ctrl+Space or Alt+A plus ordinary arrows is a keyboard selection fallback. No permanent shell flow-control modification is required. Configurable alternatives cover navigation and Save; per-app shortcuts are fixed.

Unsaved editor replacement/close and dirty chat replacement/close offer Save/Discard/Cancel. Active chat generation requires Stop/Cancel first. Failed saves retain work and cancel the pending operation. Required decision dialogs hold navigation; ordinary dialogs dismiss on navigation, and Esc cancels. Full exit checks editor then chat, handles pending account cancellation, cancels network work, terminates/reaps the PDF process, removes owned graphics/link resources, clears the clipboard, restores signals and terminal state.

## ChatGPT

Terminal transcript plus multiline composer; Enter/F12 sends, Ctrl+J newline, Ctrl+N new, F3 local history, F4 attach file, F5 remove, F9 retry, Alt+U usage, PageUp/PageDown transcript scroll, Tab composer/transcript focus, Esc stop/cancel. Selection and internal paste work in text buffers. Generation and file snapshots run in background workers; UI mutations are queued to the main loop.

Local history supports new/open/rename/delete and optional persistence. No existing ChatGPT website conversations are accessed. Immutable attachment snapshots preserve existing-file image bytes independently of source changes/deletion and clipboard replacement. They are sent only with Send. Four pending files, 8 MiB each, 16 MiB total and 25 MP each; PNG/JPEG/WEBP/non-animated GIF. Image input requires plan authorization, current catalog membership and the verified `gpt-6.1-sol` allowlist. No thumbnails, inferred image capabilities, API-key billing fallback, private endpoints, password collection, or cookie/credential borrowing.

The reviewed UI-independent adapter implements the official OSS dynamic registration and loopback authorization-code flow with PKCE/state/nonce, stable host ID, discovery/JWKS signature/issuer/audience/expiry/nonce/subject checks, separate account/client records, protected atomic credentials, serialized token rotation, revocation/sign-out, and distinct signed-out/identity-only/plan/expired/usage-limit states. Returning sign-in uses the documented account-selector path with optional email hint; retained ID tokens stay in protected storage rather than a long manual authorization URL.

Continue with ChatGPT presents the official URL inside the TUI. The user opens it in their browser and grants permission. SSH browser callbacks require loopback port forwarding, documented in README. An explicit action can write the full link to a private temporary file for manual retrieval through a second SSH session; completion/cancel/cleanup removes it. No browser process/frontend or invented device-code flow is launched. First authorized sign-in confirms plan usage; Manage usage presents ChatGPT's official usage URL. Eligibility, admission and live behavior remain unverified.

Model choices are fetched from the selected account's visible catalog in server order. Requests use public Responses, full local context, `store: false`, `stream: true`, and no unsupported preview fields. Only `response.completed` marks success. Stopped/incomplete/interrupted/network/other failures retain partial output and diagnostics. Retry is explicit, replaces the last partial response, and retains the next draft. Usage limits suspend new requests until explicit user resume after reviewing usage; server limits remain authoritative.

## PDF rendering and terminal presentation

`pdf_backend.py` owns a spawned MuPDF process with no terminal/GUI presentation role. It opens a ≤128 MiB regular-file snapshot, handles passwords, retains a committed document and separate candidate, exposes page count/outline, and rasterizes a zoomed/panned **viewport**. A candidate commits only after parent acceptance. The worker suppresses native stdout/stderr diagnostics and returns structured errors.

`terminal.py` owns the independent **Kitty graphics protocol** presenter. On entering PDF, it queries in-band PNG support using a random ID and obtains cell pixel dimensions using `CSI 16 t` or valid TTY window pixel information. Both a matching positive acknowledgement and pixel geometry are required. Split/late protocol replies are filtered before keyboard decoding. `TERM` alone never establishes image support. Graphics can be disabled. tmux/screen and bare Linux console PDF images are explicitly unsupported in this version.

In a compatible terminal, a reserved TUI viewport receives PNG image data through the same terminal stream, including over ordinary SSH. No shared terminal-local paths, graphical windows or text-extraction substitutions are used. Placement cleanup precedes redraw/dialog/navigation; the app frees only its own image ID on close/exit. Resizes re-render for the new cell area and refresh geometry. Queries/encoded buffers are display plumbing, not screen capture, clipboard images or exports.

F3 open, local picker and recent files; PageUp/PageDown pages; G go to page; +/− zoom 25–400%; arrows pan by 32 pixels; F4 local-page outline; password prompts; file/dependency/render errors. One viewport is bounded to 12 MP and 16384 pixels per dimension. Stale results are discarded, later requests coalesce, and rendering errors do not display an old image as the requested page. Esc cancels acceptance while native work may finish; close terminates/reaps the worker.

Without graphics, the PDF screen explains the missing capability, keeps its metadata/password/file/outline controls usable, and leaves the entire text UI operational. It does not claim to display the original layout there. No framebuffer/DRM/Sixel/other backend is included. PDF editing, annotation creation, OCR, search, text selection/copy, paste, and export are excluded.

## Editor

One retained prompt_toolkit text buffer with UTF-8/BOM files up to 8 MiB, new/open/save/save-as, selection, internal copy/paste, undo/redo, literal case-sensitive wrapping find, replace-one/all, line/column, unsaved marker, guarded replacement/close and clear file errors. Ctrl+S/F8 Save; F7/Alt+S Save As; F3 Open; Ctrl+N New; Ctrl+F Find/Replace; Ctrl+Z Undo; Ctrl+Y Redo; F9 Recovery. Tab inserts four spaces. Custom navigation/copy/undo keys do not clear redo history.

File I/O is dispatched off the UI thread where practical. Regular-file reads reject devices/FIFOs before reading. Save uses atomic replacement, existing permission bits, explicit overwrite confirmation, final-symlink rejection, and original size/mtime conflict checks. It cannot guarantee an atomic conflict check against another writer, preserve extended attributes/hard-link identity, or convert arbitrary encodings. Failed reads/writes retain the prior buffer.

Optional recovery autosave writes a private journal (default 30s, 0 disables), preserves the dirty marker and leaves the original file untouched. Recovery opens as Untitled; Cancel retains an unconsumed journal; successful save/discard removes consumed recovery. Background prepared snapshots are invalidated after replacement/save/discard/close. Undo, cursor/selection and viewports persist across navigation, not process restart.

## Options, persistence and information

Terminal menus provide account connection/plan authorization/account picker/sign-out/usage/resume; catalog refresh/model selection; default directory; dark/light theme; mouse reporting; graphics mode (restart); Escape timeout; global/save alternatives; conversation persistence; editor recovery interval; callback port. Font/IME control is explicitly delegated to the terminal/client. Menus save changes immediately, except the shortcut editor's explicit Save. Legacy GUI key names are migrated and obsolete GUI font preferences ignored.

Private XDG config directory or `--data-dir`: config, host identity, separate credential registrations, optional pending registration, conversation index/records, PDF recents, editor recovery, optional authorization-link file and single-instance lock. Owner-only directories/files protect data; no at-rest encryption or OS keyring is provided. History includes local drafts and image snapshots; clipboard never persists. Information displays version, SamRyong, components/licenses and supported environments.

## Verification boundary

Only source review, compilation, static lint, framework-source/API inspection and metadata/configuration checks were permitted/performed. No app launch, login, inference or runtime tests establish operational behavior. See DEVELOPMENT_REPORT.md for actual results, known limitations and the user's manual checklist.
