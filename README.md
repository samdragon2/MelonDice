# Melon Dice terminal rebuild — development report

Version: **0.2.0**. Author: **SamRyong**. Date: **2026-10-18**.

## Delivery and verification boundary

The previous GUI interface has been replaced with a genuine prompt_toolkit terminal application. `melondice` runs inside its current terminal and targets ordinary interactive SSH and Raspberry Pi OS Lite without a graphical display. Source, packaging/dependencies, entry point, secret-free configuration, rewritten README/SPEC, component notices and this report are delivered.

Before coding, the complete `Melon Dice.txt`, previous `SPEC.md`, `README.md` and `DEVELOPMENT_REPORT.md` were read. Repository/ancestor instructions and workspace state were inspected. No AGENTS.md instructions were found in the inspected locations. Existing source was untracked from the prior delivery; unrelated work and the original design reference were retained. Only the authorized application files/documentation were replaced or updated.

**No application launch, login attempt, live inference request, unit/integration/functional/end-to-end test, terminal capability probe, PDF rendering execution, screen observation, or GUI/runtime test was performed.** Compilation/static checks cannot establish runtime success. All manual runtime verification belongs to the user.

## Implemented changes

- Replaced every GUI screen/dialog with terminal-native layouts, retained text buffers, menus, lists and decisions. Removed graphical toolkit imports, graphical launch checks, external window/browser launch code, GUI key notation in the example, and desktop installation instructions.
- Preserved Home number selection/Enter behavior, lazy sessions, cycle order, Home return/last-app resume, close/reopen semantics, shared text clipboard and guarded full exit.
- Ported chat transcript/composer, streaming/stop/retry, local history new/open/rename/delete, local image snapshot/removal, account/model/usage settings and status. Generation continues across application switches; viewport following stops when navigating away or manually moving the transcript cursor.
- Ported the editor to a retained prompt_toolkit buffer with selection/copy/paste, undo/redo, find/replace, line/column/dirty status, open/new/save/save-as, overwrite/conflict errors and recovery journals.
- Split PDF byte-snapshot/rendering work from image presentation. The owned MuPDF worker renders a zoomed/panned viewport to an in-memory PNG. The Kitty presenter independently queries capability and pixel geometry and places that PNG inside the terminal's reserved PDF region.
- Added an operational missing-capability PDF screen: normal text-terminal users can continue using the entire TUI and PDF metadata/file/password/outline controls. No graphical fallback or extracted-text imitation is used. Bare-console PDF graphics and tmux/screen graphics are explicitly unsupported.
- Added terminal input/restoration ownership, explicit key handling and alternatives, protocol reply filtering, optional mouse reporting, small-terminal notice, raw-mode flow-control handling and signal/EOF cleanup.
- Migrated legacy global shortcut spellings. GUI font preferences are ignored; font/size/Korean IME are clearly client-controlled. Settings use terminal key names and validate conflicts/reserved keys.
- Added explicit private-file retrieval of an authorization URL for headless/SSH browser use, with cleanup and no browser launch. Retained the official user-subscription billing path; no API-key fallback was introduced.

Screen capture, screenshot shortcuts, Ctrl+P actions, image clipboard, PDF text selection/copy/search, PDF editing/OCR/annotation creation/export remain excluded.

## Architecture and project structure

| File | Responsibility |
| --- | --- |
| `cli.py` | `melondice` entry point, TTY check, data directory, terminal guard and cleanup |
| `app.py` | Full-screen layout, retained navigation, global key dispatch, clipboard actions, dialogs, account orchestration and lifecycle |
| `terminal.py` | POSIX termios/descriptor restoration; version-pinned input reader; Kitty query/reply filtering, upload/placement/deletion |
| `clipboard.py` | Single internal prompt_toolkit clipboard and selection replacement helper |
| `dialogs.py` | In-terminal messages, decisions, prompts, highlighted-row choices and asynchronous local picker |
| `chat.py` / `conversations.py` | Retained chat buffers/tasks; local history and immutable image snapshots |
| `editor.py` | Retained document/undo/selection/viewport, file operations, find/replace and recovery |
| `pdf_backend.py` / `pdf_viewer.py` | Single-process MuPDF rasterizer; retained document/page/zoom/pan/outline/candidate state |
| `settings.py` | Terminal Options, account/workspace/model menus, browser authorization instructions |
| `auth.py` | Reviewed UI-independent official OAuth, JWT, credential/session, catalog and Responses adapter |
| `storage.py` | Private persistence, config migration/validation, regular-file reads, atomic writes and single-instance lock |
| `tasks.py` | Dedicated asyncio network/I/O dispatch loop and queued main-thread callbacks |
| `pyproject.toml` / `requirements.txt` | Python/dependency declarations and installed launch command |
| `scripts/static_check.py` | AST/metadata/config/source audit without importing app modules |

The main UI is prompt_toolkit **3.0.52**. This version is pinned because the input adapter wraps its POSIX reader and choice activation reads its highlighted index. Those extension points and constructor/method signatures were inspected directly in the downloaded framework source. No framework/app runtime was exercised by that inspection.

Background HTTP/I/O uses the retained `Tasks` dispatcher; callbacks mutate terminal widgets only on the UI thread. MuPDF remains exclusively in a spawned process, following its documented [multithreading restriction](https://pymupdf.readthedocs.io/en/latest/recipes-multiprocessing.html). Native worker diagnostics are redirected away from the terminal; startup failures become structured capability errors. Rendering coalesces and drops stale results. Clipboard and session state remain application-owned, not delegated to external editor/viewer programs.

## Terminal/display behavior

The text UI needs a real POSIX VT100-compatible TTY and UTF-8; 80×24 or larger is recommended. It does not need `DISPLAY`, a desktop, or graphical forwarding. Ordinary SSH carries the TUI; the optional in-band PNG protocol uses the same connection.

PDF images require a matching positive Kitty PNG query response and valid pixel cell dimensions. No environment variable alone enables images. Geometry is obtained from `CSI 16 t` or valid TTY window information and refreshed on cell-grid resize. Without it, the PDF screen reports capability unavailable and continues as a usable text interface. No framebuffer, DRM, Sixel, or other terminal-image backend is implemented. tmux/screen image passthrough is conservatively disabled. No bare Linux console PDF compatibility is claimed.

The presenter uses its own random image ID, chunked in-band PNG, cursor preservation, placement cleanup before render/dialog/switch, and image deletion on close/exit. It does not save page images or use a terminal/client shared filesystem. The renderer crops to the viewport before encoding, with a 12 MP / 16384-pixel viewport limit and 128 MiB document limit. Zoom/page/pan state is retained.

prompt_toolkit raw mode disables `ISIG`, `IXON` and `IXOFF`; an outer guard restores the original termios and file-descriptor flags. Ctrl+C copy is handled without termination. F6 avoids intercepted Alt+Tab, F8 avoids intercepted Ctrl+S, F10 avoids Ctrl+Q, and F7/Alt+S avoids Ctrl+Shift+S ambiguity. F2 avoids Ctrl+I/Tab equivalence. F12 sends when a client maps Enter to LF. Ctrl+Space/Alt+A selection works with ordinary arrows when modified keys fail. Mouse reporting can be disabled. Font/size/IME provisioning is a client/environment responsibility, with explicit Korean/UTF-8 guidance in README.

## Backend correctness and authentication review

The reused OAuth/history/storage/task code was read and checked for UI dependencies before reuse. No graphical toolkit or display assumption remains in those paths. The official adapter still uses dynamic OSS registration, a stable host UUID, fresh state/nonce/PKCE, an exact loopback URI, issued client IDs, discovery/JWKS signature validation, issuer/audience/expiry/subject/nonce checks, protected atomic records, serialized refresh rotation and discovery-based sign-out revocation. Identity-only grants cannot infer. Account/client identities remain separate; pending issued registrations do not become trusted identities before validation.

Current official pages reviewed during this rebuild include [registration/sign-in](https://developers.openai.com/siwc/token-sharing-open-source/sign-in), [accounts/sessions](https://developers.openai.com/siwc/token-sharing-open-source/profiles-and-sessions), [models/inference](https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference) and [preview restrictions](https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations). The [quickstart](https://developers.openai.com/siwc/quickstart) and reference links explain the eligible local/open-source subscription route. The adapter uses public Responses with full local input, `store: false` and `stream: true`, and requires the completion event. It does not use private website endpoints or different billing.

The terminal flow displays Continue with ChatGPT and the official authorization URL. The user opens the official site in their browser, authenticates/consents and returns through the loopback callback. Remote browsers need SSH loopback forwarding; README provides exact commands. No device-code endpoint is invented. Returning sign-in omits the optional ID-token hint so a long token-bearing URL does not need manual transfer; the official account selector and identity checks are used instead. A private temporary URL file is available explicitly and removed on ordinary attempt completion/cancel/cleanup.

Actual eligibility, authorization, renewal, revocation and inference have **not** been attempted. There is no demonstrated account-specific blocker and no fabricated success. If the provider rejects a user's account/workspace, region, policy or usage, the app exposes the available diagnostic and stops inference without changing billing. Usage-limit errors require explicit resume after reviewing usage. No website conversation access or unlimited allowance is claimed.

## Installation and launch

See README for full instructions. On Raspberry Pi OS Lite 64-bit, install Python 3.10+, venv/pip and CA certificates, create/activate a venv, and `pip install .`; run **`melondice`** in the terminal. No GUI packages are required. prompt_toolkit, HTTPX, PyJWT/cryptography, Pillow and PyMuPDF are declared; native ARM64 installation remains unverified. The project retains AGPL-3.0-or-later with updated component notices.

For remote authentication, use `ssh -t -L 1455:127.0.0.1:1455 USER@PI`, then run the installed command. This forwards only the OAuth callback while the TUI and PDF protocol use the ordinary terminal stream. The browser runs wherever the user chooses to authenticate, with that loopback routing configured. `--pdf-graphics off` disables all graphics probing. `--data-dir` selects private app storage. Configuration examples contain no secrets.

## Source-review fixes

Review corrected redo invalidation from custom navigation/undo bindings; highlighted-row activation after list typeahead/paging; immutable attachment cancellation/counting; transcript cursor/following behavior across hidden streaming; history snapshots that previously shared mutable message lists on reload; explicit incomplete/interrupted response states; recovery generation/epoch invalidation; PDF document identity in image caches; transactional candidate acceptance/cancel; stale render suppression; structured worker startup errors; native stdout/stderr isolation; regular-file reads before FIFO/device blocking; raw reply filtering; signal handler argument errors; and cleanup ordering when terminal output fails.

## Checks actually performed

Only non-interactive source/static checks were used. Initial compiler/static passes succeeded apart from one unused import identified by the audit and then removed. Final results:

| Check | Result |
| --- | --- |
| `python3 -X pycache_prefix=/private/tmp/melondice-bytecode -m compileall -q src` | Passed for all 16 application modules; no application execution |
| `/opt/homebrew/bin/python3 -B scripts/static_check.py` | Passed: Python 3.10 grammar/code-object compilation, global names/local import paths, dependencies/entry point, JSON fields, required artifacts, whitespace, no GUI imports or explicit Ctrl+P binding; no application imports |
| Pyflakes 3.4.0 on `src` and `scripts`, executed from its downloaded wheel | Passed with no diagnostics |
| Framework source/API inspection | Completed using AST/text inspection of the prompt_toolkit 3.0.52 wheel; checked widget, key-binding, layout, input-reader, run/exit and buffer APIs |
| GUI/forbidden-launch source scan and `git diff --check` | Passed; no GUI/display checks/browser launcher in app source. Ctrl+P occurs only as a reserved configuration key. The AST audit also checks whitespace in untracked new files. |

The framework and Pyflakes wheels were downloaded to `/private/tmp/melondice-source-audit` for inspection/linting. The first sandboxed download failed DNS; the approved retry succeeded. They were **not installed into the app environment**. Pyflakes was executed as a static analyzer from its wheel; it did not import app modules. No application dependencies were installed or run as part of this rebuild. The audit uses Python 3.14.7 for AST/metadata parsing and checks 3.10 grammar; bytecode compilation uses the available Python 3.9.6 interpreter. These results do not demonstrate dependency/runtime compatibility on the Pi.

## Remaining limitations and unverified behavior

- All interactive/terminal/native/network behavior remains unverified: startup without graphical variables, real SSH input, alternate-screen restoration, client interception, Korean composition, resize, clipboard selection and rendering fidelity/performance need user runtime verification.
- Only the Kitty PNG protocol with cell geometry is implemented for original-layout PDF images. Other terminals, text consoles and multiplexers retain the text UI/capability explanation. No claims are made for other image protocols or bare-console graphics.
- PDF raster transmission can be slow over SSH. Native calls are cancelled by rejecting their result; the worker may finish them in the background until viewer close terminates it. Font changes that preserve the cell-grid size may require restarting to refresh pixel geometry.
- The framework is pinned because of reviewed extension points/private highlighted-index access. A framework upgrade requires source/API review and user runtime verification. Some clients may deliver late/unsupported replies or modified-key encodings differently.
- Global/save shortcuts are configurable; per-app keys are fixed. Terminal-client paste or Shift+mouse copy is outside the internal clipboard's management. IME commit/Enter behavior is client-dependent.
- The editor supports UTF-8/BOM only, one buffer and an 8 MiB file limit. LF is recommended; no arbitrary encoding/line-ending controls are provided. Atomic replacement does not preserve extended attributes/hard links; size/mtime conflict detection is not transactional against another writer.
- Recovery is a private journal rather than source-file autosave. Work after the last interval can be lost; cursor/selection/undo/scroll are navigation state, not full restart recovery. Existing unconsumed recovery is retained instead of silently replaced.
- History uses JSON and includes image snapshots. Long conversations or large snapshots can consume considerable memory/disk; history serialization and journal commits may briefly delay input on slow storage. There is no context compaction or quota management.
- Image input remains conservatively limited to an authorized catalog exposing the verified `gpt-6.1-sol` model. Other models' image support is not guessed. No thumbnail preview is included.
- Credentials use owner-only storage and atomic writes, not at-rest encryption/keyrings. Revocation can fail remotely and is then explained. The optional private authorization-link file can survive SIGKILL/power loss and should then be removed manually.
- Uninterruptible filesystem/native/OS failures, SIGKILL and power loss cannot guarantee cleanup/recovery. Normal/handled cleanup is implemented, but has not been exercised. No successful authentication, inference, PDF rendering, Pi installation or terminal restoration result is claimed.

## User manual verification checklist (not performed)

- [ ] Install on the intended Pi and run `melondice` directly in a local terminal and ordinary SSH with no graphical display variables. Verify a clear non-TTY error and usable `--pdf-graphics off` mode.
- [ ] Home: Enter without selection; 1→3→2 selection; other numbers unchanged; Enter opens; lazy starts; F6/Alt+Tab order and last-app Home return; F1/F2/Options; close/reopen starts fresh sessions.
- [ ] Retain chat draft/cursor/selection/attachments/transcript scroll and generation; editor dirty buffer/cursor/selection/undo/redo/scroll; PDF file/page/zoom/pan across repeated switches/Home and dialogs.
- [ ] Copy/paste multiline English/Korean text with Shift+arrows, Ctrl+Space, Alt+A and mouse where supported. Empty copy preserves clipboard; Ctrl+C never exits; password cut/kill does not export; Home and app closes preserve clipboard; full restart clears it.
- [ ] Check Ctrl+S/Ctrl+Q do not freeze the TUI; test F8/F10 alternatives, Ctrl+I/Tab equivalence, CR Enter versus Ctrl+J, F12 send, Alt/Escape timeout and client interception. Confirm terminal echo/canonical/flow-control/mouse/alternate-screen state returns after exit and handled failure.
- [ ] Exercise editor save/save-as/overwrite/conflict/errors, UTF-8/BOM, unsupported files, undo→navigate→redo, find wrapping, replace-one/all, line/column and unsaved Save/Discard/Cancel before New/Open/Close/full exit. Failed save must preserve the old buffer and abort replacement.
- [ ] Test recovery interval, Cancel preserving an existing journal, F9 reopen, recover as Untitled, discard/save cleanup and stale background snapshot invalidation. Cancel a later app's full-exit decision and verify earlier buffers remain intact.
- [ ] On a terminal without Kitty capability, check the explanatory PDF screen and continued usability of all text features. No graphical window or fake extracted-text page should appear.
- [ ] On a compatible direct terminal/SSH client, verify capability acknowledgement/geometry, actual equation/figure/scanned layout, passwords, recent-file selection/typeahead, page bounds, go-to-page, zoom/pan, outline, resize and image removal on dialogs/switch/close/exit. Check render/file/dependency limits/errors and process cleanup.
- [ ] Test official browser authorization with loopback forwarding and optional private-link retrieval; denied/identity-only grants, wrong account rejection, multiple workspace registrations, first welcome, returning registration reuse, refresh and sign-out/revocation warnings. Do not share links/credentials in reports.
- [ ] Refresh/select account models and stream a message; switch applications during generation; stop/retry and preserve the next draft; verify partial/incomplete/interrupted/failed/completed states, network failures and usage-limit pause/resume. Confirm no alternate billing.
- [ ] Attach/remove supported/unsupported images, mutate/delete the source after attaching, replace clipboard, cancel snapshot loading, and verify snapshot independence and limits.
- [ ] Test theme, directory, mouse, shortcut migration/collision errors, Escape timeout, history persistence/deletion, font/IME guidance, tiny-terminal notice and resize restoration.
- [ ] Exit with dirty work and active account/network/PDF operations; verify required decisions, no owned child/background work remains, private-link/clipboard/image cleanup, recovery after handled hangup, and instance-lock reuse on the next launch.
