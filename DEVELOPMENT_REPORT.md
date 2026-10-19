# Melon Dice Sixel PDF presentation — development report

## Follow-up fix: PDF viewer construction (2026-10-19)

The user reported `Label.__init__() got an unexpected keyword argument 'height'`
when opening pdfViewer on the Pi. The pinned prompt_toolkit 3.0.52 `Label`
constructor does not accept `height`; this prevented construction of the viewer,
before a PDF could be opened or displayed.

Replaced the heading Label with a non-focusable `Window` containing a callable
`FormattedTextControl`. `Window` supports `height=2`, so the intended fixed
two-row heading remains in place during status updates. Reviewed the locally
installed framework source and all project Label calls; no other Label call
passes `height`.

Verification: source compilation, the existing source-only static audit, Pyflakes,
and `git diff --check` passed. No application modules were imported or run;
no graphics probe, conversion experiment, login or runtime test was performed.
The user still needs to verify viewer startup and PDF presentation on the Pi.
No commit, branch change or push was performed for this follow-up. The original
implementation report below describes the earlier delivery, including its Git
state at that time.

Date: **2026-10-19**. Project version: **0.2.0**. Author: **SamRyong**. Workspace: `/Users/samryong/MelonDice`, branch **pdfattach**.

## Scope and verification boundary

Implemented Sixel presentation alongside the existing Kitty PDF path in the current checkout. Before editing, read SPEC, README, the prior development report, terminal/PDF worker/viewer/app/CLI code, settings, configuration validation, task dispatch and dependency declarations. The checkout was clean initially. No applicable AGENTS.md was found in the workspace/inspected ancestor locations. No branch switch, commit, merge or push was performed. No Pi software was installed or reconfigured.

**No Melon Dice launch, terminal graphics probe, PDF rendering/conversion experiment, login attempt, live inference request, unit/integration/functional/end-to-end test, screenshot, screen sharing or remote viewing was performed or requested.** All implementation checks were source review or non-interactive static analysis. Static success does not establish runtime behavior.

## Hardware observations supplied by the user

These observations were performed by the user on the physical Pi **before this implementation**, not by the developer:

- Raspberry Pi 5, host `sam-pi`, user `samryong`, Debian GNU/Linux 13 Trixie / Raspberry Pi OS Lite, aarch64, direct `/dev/tty1`, framebuffer/DRI devices and video/render/input group membership. No desktop/X11/Wayland setup was present. No fixed IP, monitor resolution or cell size is assumed.
- mlterm **3.9.5 framebuffer build**, configured with `--with-gui=fb --with-tools=mlimgloader,mlcc --with-utmp=none`, installed as `/home/samryong/.local/bin/mlterm-fb`. This is not a claim that a newer KMS/DRM backend was built.
- The launcher `"$HOME/.local/bin/mlterm-fb" --aafont=true --fontsize=24 --fg=white --bg=black` opened an interactive terminal on the directly connected monitor. `~/.mlterm/aafont` uses `DEFAULT=DejaVu Sans Mono`.
- The user piped a three-pixel RGB PPM into img2sixel and observed red/green/blue rectangles.
- The user rendered the W3C dummy PDF with `mutool draw -r 96 -o test.png test.pdf 1` and displayed it with `img2sixel -h 600 test.png`. The photographed observation showed a white page and “Dummy PDF file.” MuPDF's ICC warning did not prevent PNG generation.

These establish that the external mutool → PNG → img2sixel → mlterm-fb pipeline displayed images on that device. They do **not** establish Melon Dice installation, Python dependency availability, PyMuPDF rendering, viewer positioning, zoom/pan, redraw behavior or terminal restoration.

## Implemented changes

| Area | Result |
| --- | --- |
| Presentation separation | New `graphics_presenters.py` contains small Kitty/Sixel presenters. `terminal.py` handles common selection, geometry, reply filtering and output coordination. The spawned PyMuPDF rasterizer remains the production renderer; no mutool shell fallback or GUI backend was added. |
| Modes | CLI, config validation, example config, Options, capability messages and docs consistently support `auto`, `kitty`, `sixel`, `off`. Existing auto/off values remain valid. CLI overrides saved config for one run; Options applies graphics/geometry changes after restart. |
| Bounded detection | Auto sends a random-ID Kitty PNG query and Primary DA. A positive matching Kitty response within 1.5 seconds wins. Otherwise at the deadline Sixel requires advertised feature 4 and available img2sixel. Late replies cannot switch protocols. Explicit Kitty still requires acknowledgement; explicit Sixel requires no Kitty/DA response and trusts the user's terminal choice. TERM alone neither proves nor rules out graphics. |
| Geometry | Query cell pixels (`CSI 16 t`) and text-area pixels (`CSI 14 t`), and inspect matching-grid TTY pixel dimensions. Whole-area dimensions must divide exactly by the grid; direct cell reports take precedence. Invalid values are rejected. Resize invalidates old geometry and opens another bounded geometry window. `--pdf-cell-pixels WIDTHxHEIGHT` / `pdf_cell_pixels` provides a measured override (width 1–256, height 1–512); empty config queries automatically. Font size is never treated as cell size. |
| Encoding | Detect img2sixel through PATH. Invoke it using an argument array on the existing background asyncio loop, pipe the PNG through stdin and capture stdout/stderr. Use 7-bit output, 256 colors, no diffusion and low quantizer quality without scaling. Bound conversion to 30 seconds, stdout to 128 MiB, stderr to 64 KiB, and child exit after pipe completion to two seconds. Validate one DCS and matching raster dimensions; sanitize failure diagnostics before showing them. |
| Cancellation/resources | Cancel obsolete converter work, kill and reap owned children, drain pipes, and reject stale callbacks by generation. Protect child acquisition against cancellation during process creation. Retain one completed encoded viewport, free it on PDF close/shutdown, and preserve it across ordinary hide/show. PDF raster results also check document identity. |
| Placement/cleanup | Sixel uses the reserved viewport origin and saves/restores cursor and DECSDM mode. Raster height rounds down to six-pixel bands; a text row below permits terminal post-image cursor advancement without screen scrolling. ECH clears occupied picture cells; the text renderer is repainted once after damage. Kitty continues using its own image ID, PNG chunks and protocol deletion. |
| Redraw coordination | Raw output remains on the UI/lifecycle thread through prompt_toolkit's output. Unchanged Sixel output survives ordinary text redraws. The 50ms pump polls work but no longer invalidates text unconditionally. Page/zoom/pan/resize, overlays, switches, full repaints and close clear/repaint when necessary. Fixed two-row PDF metadata prevents busy/encoding labels from changing viewport dimensions repeatedly. |
| Usability/docs | Missing capabilities, missing executable, geometry and converter errors leave text apps and PDF metadata/password/file/outline controls usable. Updated README, SPEC, dependency comments, component notices and this report. README now contains actual installation/use instructions rather than duplicating the previous report. Static audit checks graphics choices across CLI/validation/Options. |

Existing Home selection/Enter, retained application controllers, F1 and Alt+Tab/F6 navigation, background chat streaming, editor and text clipboard, PDF picker/recents/password/outline/navigation, guarded close and terminal guard remain in place. Their runtime preservation is awaiting user verification. No screenshot, image clipboard, PDF editing, OCR, extraction substitute or PDF export feature was introduced.

## Checks actually performed

Only the following source/static checks were run, without importing or executing application modules:

| Check | Result |
| --- | --- |
| `python3 -X pycache_prefix=/private/tmp/melondice-bytecode -m compileall -q src` | Passed: compilation of 17 source modules; bytecode is outside the checkout. |
| `/opt/homebrew/bin/python3 -B scripts/static_check.py` | Passed: Python 3.10 grammar/code-object compilation, global symbols and local imports, entry point, dependency consistency, config fields/mode consistency, forbidden GUI/Ctrl+P scan, required docs and whitespace. |
| Pyflakes 3.4.0 on `src` and `scripts`, loaded from the pre-existing wheel in `/private/tmp/melondice-source-audit` | Passed with no diagnostics. No package installation or application import. |
| `git diff --check` and source/diff review | Passed. Reviewed tracked changes and the new untracked presenter source. No runtime checks. |
| Framework/protocol source inspection | Read the pre-existing prompt_toolkit 3.0.52 wheel's render hooks, diff/erase behavior and public renderer accessors; consulted upstream terminal/mlterm/libsixel sources for query, cursor-origin and encoder behavior. No graphics sequences were executed. |

The local compile interpreter is Python 3.9.6; the static audit/Pyflakes interpreter is Python 3.14.7, with the audit explicitly parsing Python 3.10 grammar. These are compiler/linter results, not proof that dependencies work on the Pi's Python/aarch64 environment. No new wheels/dependencies were installed for this implementation.

Source references used for implementation review: [XTerm control sequences](https://invisible-island.net/xterm/ctlseqs/ctlseqs.html) defines DA feature 4, cell/text-area pixel queries and DECSDM; [mlterm parser source](https://github.com/arakiken/mlterm/blob/master/vtemu/vt_parser.c) shows cursor-origin versus home-origin image behavior and picture cells; [img2sixel command source](https://github.com/saitoha/libsixel/blob/master/converters/img2sixel.c) and [libsixel encoding source](https://github.com/saitoha/libsixel/blob/master/src/tosixel.c) describe the options and raster envelope. Upstream source inspection is not runtime validation of the user's installed 3.9.5 build.

## Installation and use on the Pi

Full one-line instructions and dependency details are in [README.md](README.md). These are **user instructions, not commands executed on the Pi by the developer**.

From the development computer, copy this uncommitted project tree (adjust the destination if needed):

```sh
rsync -av --exclude='.git' --exclude='.venv' --exclude='__pycache__' /Users/samryong/MelonDice/ samryong@sam-pi:~/MelonDice/
```

On the Pi, create the project venv if necessary:

```sh
cd "$HOME/MelonDice" && python3 -m venv .venv
```

Then install/update the copied project:

```sh
cd "$HOME/MelonDice" && .venv/bin/python -m pip install --upgrade .
```

Inside the existing mlterm-fb session:

```sh
"$HOME/MelonDice/.venv/bin/melondice" --pdf-graphics sixel
```

The code has not been pushed; a remote pull alone cannot retrieve these local edits. No fixed IP is prescribed. `libsixel-bin` is already installed according to the user; do not reinstall mlterm or change Pi display configuration for this code update. Python packages, especially PyMuPDF, must still install successfully; `mupdf-tools` does not replace them. If geometry is unavailable, use independently measured `--pdf-cell-pixels WIDTHxHEIGHT` as documented in README, never guessed values from font size 24.

## Remaining limitations and unverified runtime behavior

- **All Melon Dice integration behavior remains unverified**, including installation, Python dependencies, PyMuPDF worker startup, actual image display/fidelity, position/clipping, scroll avoidance, cursor/focus, CPU/output volume, cancellation/reaping, redraws and terminal restoration on the Pi. No runtime success is claimed.
- Sixel is a palette protocol: this initial encoder reduces color fidelity and retains one encoded viewport. The original aspect ratio/layout is retained, but photographs/gradients can differ from Kitty's PNG display. Up to five bottom pixels of viewport space are unused to contain bands.
- Correct cleanup requires compatible text/graphics erasure and cursor-origin/DEC mode behavior. mlterm's picture-cell semantics inform the implementation; other Sixel terminals require manual verification. No universal Sixel compatibility is claimed.
- tmux/screen graphics and bare Linux-console images remain unsupported. Run inside mlterm-fb or another compatible direct terminal. Text apps remain available without image support.
- Detection has a fixed 1.5-second window; high-latency/filtered replies can prevent automatic selection. Known Sixel terminals can use explicit mode; geometry may require a measured override. Pixel replies lack request IDs, so very late replies during rapid consecutive resizes remain a protocol limitation. Font changes without grid resize may require restart; explicit overrides must be updated manually.
- Encoding stays off the UI thread, but transmitting the completed raster is serialized on terminal output and can briefly block input. Very large/complex viewports may hit conversion or raster limits; no Pi performance measurements were made. Cleanup/full repaint on actual image damage may still be visible and needs user assessment for flicker.
- Cancellation stops converter children; native PDF calls may finish before stale output is rejected. Uninterruptible OS/native failures, SIGKILL or power loss cannot guarantee immediate cleanup/restoration. Existing guarded close/terminal restoration paths require user verification.
- Authentication, inference, editor/clipboard/history behavior were not runtime tested or redesigned. No system software, login or live network inference operation was attempted.

## User manual verification checklist — not performed by the developer

- [ ] Transfer/install on the Pi; confirm the Python dependencies install on aarch64. Launch **inside the existing mlterm-fb session** using explicit Sixel. Verify missing-converter/geometry messages are actionable if encountered; provide measured cell geometry only when required.
- [ ] Open `/home/samryong/melondice-pdf-test/test.pdf` through F3. Confirm the white page and text appear inside the reserved region, with headers/footers intact, no full-TUI scrolling, and working keyboard focus. This is the first Melon Dice integration display check, distinct from the earlier external pipeline test.
- [ ] Open real multi-page PDFs with equations, vector figures, embedded fonts/Korean text, photos and scanned pages. Compare document layout/aspect ratio and legibility with the originals; assess the documented palette/color limitation.
- [ ] Exercise recent-file selection/Enter, file errors, password/incorrect-password/cancel, F4 outline, G page selection and page bounds. PageUp/PageDown must update the page and never retain a stale requested image.
- [ ] Zoom repeatedly with +/− to limits and pan in every direction. Confirm page clipping stays within the viewport, pan clamps at edges, and page/zoom/pan state survives Home and switching back.
- [ ] Resize the terminal/cell grid, including below 80×24 and back. Verify geometry refresh, re-rendering, containment, no old-size image, and focus recovery. If changing fonts, restart/update the measured override when necessary.
- [ ] Open/close Options, Information, picker, password, outline and page dialogs over a visible PDF. The image must disappear behind overlays and reappear at the same viewing position after dismissal. Verify no picture fragments, blank dialog cells or lost cursor/focus.
- [ ] Stay idle on a PDF and use keys/text updates that do not change its viewport. Assess whether the image remains steady without periodic erase/retransmit, flicker or excessive CPU/output. Check busy/encoding status does not repeatedly resize the viewport.
- [ ] Test F1 Home, Alt+Tab/F6 cycle order and Home selection/Enter behavior. Preserve PDF position, editor dirty text/cursor/selection/undo and chat draft/transcript scroll. Verify chat streaming continues while PDF/editor is active.
- [ ] Rapidly change page/zoom/pan, open a different document with the same viewport shape, resize, press Esc during rasterization/encoding and switch away/close while work is pending. No stale completion should appear, no cancelled conversion should write to the TUI, and owned children should terminate/reap.
- [ ] Close PDF/reopen, close to Home, perform guarded full exit/cancel, and inspect shell restoration. Check image cleanup, cursor, echo/raw/canonical/flow-control/mouse/alternate-screen state and ability to launch again. Check handled hangup/failure recovery when appropriate.
- [ ] On a Kitty-capable terminal, verify explicit Kitty and auto selection, PNG placement, cleanup and resize. On a terminal advertising both protocols, auto should prefer a positive Kitty acknowledgement; explicit Sixel should remain Sixel.
- [ ] Verify auto, explicit Sixel, explicit Kitty and off settings/CLI behavior and restart semantics. Unsupported terminals must retain chat/editor and a clear PDF capability explanation. tmux/screen should explain the direct-terminal requirement.
- [ ] Check internal text copy/paste, editor save/undo/guarded close and existing navigation shortcuts. Confirm no screenshot/image clipboard/PDF editing/export flow was added.
