# Melon Dice

Melon Dice 0.2.0, by SamRyong, is a Python 3.10+ prompt_toolkit TUI with ChatGPT, an original-layout PDF viewer, and a text editor. It runs inside the launching terminal, including Raspberry Pi OS Lite and ordinary interactive SSH. No desktop, graphical window, X11, Wayland, or browser frontend is required.

## Install and update on the Pi

Python requirements are declared in `pyproject.toml` and `requirements.txt`: `prompt_toolkit==3.0.52`, `httpx>=0.27,<1`, `PyJWT[crypto]>=2.9,<3` (including cryptography), `Pillow>=10.4,<13`, and `PyMuPDF>=1.24.10,<2`. Python 3.10+ with pip/venv and CA certificates is required. Installation of these dependencies on the user's aarch64 Debian 13 Pi has **not** been verified. A compatible PyMuPDF wheel or successful native build is necessary; installing `mupdf-tools` alone does not satisfy the Python dependency.

Sixel additionally requires `img2sixel` on the Pi's `PATH`, provided by Debian's **libsixel-bin** package. The user already installed it and built **mlterm 3.9.5 with `--with-gui=fb`**, not the KMS/DRM backend. No reinstallation/reconfiguration of that setup is needed for this code change. Kitty presentation does not need img2sixel. `mutool` is useful for the user's independent experiment but is not called by Melon Dice. Native libraries, fonts, mlterm and libsixel are not bundled or installed by pip.

The changes in this development checkout have not been committed or pushed. To copy this tree to the Pi, run this **on the development computer**, substituting a reachable hostname if `sam-pi` does not resolve. The destination below is a suggested project directory, not an observed existing path:

```sh
rsync -av --exclude='.git' --exclude='.venv' --exclude='__pycache__' /Users/samryong/MelonDice/ samryong@sam-pi:~/MelonDice/
```

On the Pi, create a project venv if one does not already exist:

```sh
cd "$HOME/MelonDice" && python3 -m venv .venv
```

Install or update the copied project and its Python dependencies:

```sh
cd "$HOME/MelonDice" && .venv/bin/python -m pip install --upgrade .
```

Use the corresponding paths if the project/venv lives elsewhere. These commands are instructions for the user; they were not executed on the Pi during development. A later `git pull --ff-only` can retrieve this implementation only after the user explicitly publishes it to their own remote; no Git history or remote was changed for this delivery.

## Run inside the existing mlterm-fb session

From the Pi's directly connected local console, the user's already working launcher is:

```sh
"$HOME/.local/bin/mlterm-fb" --aafont=true --fontsize=24 --fg=white --bg=black
```

**Inside that interactive mlterm-fb terminal**, launch the installed app:

```sh
"$HOME/MelonDice/.venv/bin/melondice" --pdf-graphics sixel
```

If the venv is activated or its bin directory is on PATH, the equivalent is `melondice --pdf-graphics sixel`. Enter Home selection `2`, then Enter, then F3 to choose a PDF. The user's sample is at `/home/samryong/melondice-pdf-test/test.pdf`. Starting directly in `/dev/tty1` without mlterm-fb does not give the bare Linux console an image protocol. The application itself never opens framebuffer/DRM devices.

## Kitty and Sixel presentation

| Mode (`--pdf-graphics` / `pdf_graphics`) | Selection policy |
| --- | --- |
| `auto` (default) | On entering PDF, send a random-ID Kitty in-band PNG query and Primary Device Attributes query. Select Kitty on a positive matching PNG acknowledgement within 1.5 seconds. Otherwise, at the deadline select Sixel if DA advertises feature 4 and img2sixel is available. No recognized capability yields a clear text explanation. |
| `kitty` | Require the positive matching PNG acknowledgement within 1.5 seconds. Do not fall back to Sixel. |
| `sixel` | Explicitly trust the user's Sixel terminal selection; require img2sixel and valid cell geometry. No Kitty query/acknowledgement or Sixel advertisement is required. This is the intended choice for the experimentally confirmed mlterm-fb setup. |
| `off` | Disable image presentation and capability/geometry queries; retain chat, editing and PDF file/metadata/password/outline controls. |

A terminal name such as `TERM=xterm` never proves Kitty support; terminal names alone do not disable graphics either. The decision is bounded and retained for the session; late replies are filtered but do not switch protocols. tmux/screen image passthrough is not implemented in any mode: launch outside the multiplexer. Unsupported text terminals remain useful for chat/editing; PDF viewing requires a supported image protocol.

Kitty sends PNG bytes and uses an owned image ID for placement/deletion. Sixel sends a palette raster; it has no equivalent image-ID deletion model. Both reuse the existing spawned PyMuPDF viewport renderer, preserving page layout/aspect ratio, zoom and pan. Sixel encoding uses a captured, asynchronous `img2sixel` subprocess with PNG stdin, encoded stdout and captured stderr. It uses 256 colors, no diffusion and low quantizer quality for responsiveness; gradients/photos may lose color fidelity compared with Kitty PNG. It does not resize or distort the raster.

Sixel images are positioned at the reserved text viewport using the cursor origin, with DECSDM mode and cursor saved/restored. The image height is rounded down to a multiple of six pixels (at most five pixels unused) to contain Sixel bands. A text row remains below the viewport for terminals that advance the cursor after a picture. Cleanup erases picture cells using ECH, then repaints the text screen once. This requires a terminal that erases intersecting Sixel graphics when text cells are erased, as mlterm's picture-cell model does. Terminals with incompatible erasure/positioning behavior are unsupported until verified.

The latest encoded viewport is cached across ordinary text updates, dialogs and app switching. A changed page/zoom/pan/geometry requires a new viewport; obsolete conversions are cancelled and stale results are rejected. The background pump still polls pending work every 50ms, but invalidates text only for changes; an unchanged image is neither erased nor retransmitted on each poll. Overlays/switches/resize/full repaint clear the image as needed and restore cached presentation when returning. Returning after a grid change may require rendering again. Full image transmission can still block terminal output briefly, particularly over slow SSH; no performance claim is made for the Pi.

## Pixel geometry

Graphics need measured **terminal character-cell pixels**, independent of the `--fontsize=24` font request. There is no hard-coded resolution, IP address or inferred font-to-cell conversion.

On first PDF entry and on cell-grid resize, Melon Dice requests `CSI 16 t` (cell pixels) and `CSI 14 t` (text-area pixels), and checks `TIOCGWINSZ` pixel information against the current grid. A direct cell report takes precedence over whole-area/TTY information. Whole-area dimensions must divide exactly by the current grid; zero/invalid/non-integral values are rejected. Replies are accepted for a bounded 1.5-second geometry window. Old pixel geometry is invalidated at resize instead of reused blindly. This follows the [terminal query definitions](https://invisible-island.net/xterm/ctlseqs/ctlseqs.html).

If the terminal does not report valid geometry, the PDF screen requests an explicit override. Set `--pdf-cell-pixels WIDTHxHEIGHT` to the **independently measured** cell width and height. Accepted range: width 1–256 and height 1–512 pixels. For shell use, first assign your actual measurements to `CELL_WIDTH` and `CELL_HEIGHT`, then run:

```sh
"$HOME/MelonDice/.venv/bin/melondice" --pdf-graphics sixel --pdf-cell-pixels "${CELL_WIDTH}x${CELL_HEIGHT}"
```

Measure the terminal's usable text area and divide by its column/row count, or use reliable cell metrics from the terminal; physical monitor resolution and font size alone are insufficient. A wrong override can cause misplaced images. If exact measurements are unavailable, leave images disabled until geometry can be established. An override deliberately takes precedence over queries and must be updated after a font/cell-size change. Font changes that leave the same cell grid may require restarting even in automatic geometry mode.

Options provides all four graphics choices and a cell-pixel field; both apply after restart. CLI values override saved settings for that run. Existing `auto` and `off` configs still load. `config.example.json` uses `"pdf_graphics": "auto"` and `"pdf_cell_pixels": ""` (empty means query). Config is stored in `$XDG_CONFIG_HOME/melondice` or `~/.config/melondice`, or the private directory selected by `--data-dir`. Keep credentials/history private.

## Controls and retained sessions

Home: 1 ChatGPT, 2 pdfViewer, 3 Text editor; the latest valid number selects, Enter opens. F1 returns Home; Alt+Tab/F6 cycles retained sessions; F2 shows Information; Ctrl+O opens Options; Ctrl+Q/F10 closes the app, or exits from Home. Unsaved editor/chat work has Save/Discard/Cancel guards. Chat streaming continues when another app is active. PDF page/zoom/pan and editor buffers/undo/selection remain in memory across switches.

PDF: F3 open/recent files, F4 outline, PageUp/PageDown pages, G go to page, +/− zoom (25–400%), arrows pan, Esc cancel pending acceptance/display work. Password PDFs are supported. The existing renderer limits documents to 128 MiB and viewports to 12 MP / 16384 pixels per dimension. Conversion is limited to 30 seconds, 128 MiB encoded stdout and 64 KiB diagnostic stderr. Failed encoding explains the problem and leaves the text UI available; restart after correcting dependencies. Only the latest encoded viewport is retained; no page-image files are exported.

Chat: Enter/F12 send, Ctrl+J newline, Esc stop, F3 local history, F4 attach an existing image, F5 remove, F9 retry, Alt+U usage. Editor: Ctrl+S/F8 save, F7/Alt+S Save As, F3 open, Ctrl+N new, Ctrl+F find/replace, Ctrl+Z undo, Ctrl+Y redo, F9 recovery. Ctrl+C/X/V use a shared internal **text** clipboard; Ctrl+Space/Alt+A starts selection where Shift+arrows is unavailable. No screenshot, image clipboard, PDF editing/OCR/text-extraction substitute/export is implemented. Fonts, size and Korean IME remain terminal/client settings.

The terminal must be an interactive POSIX UTF-8 VT100-compatible TTY; 80×24 cells or larger is recommended. Ctrl+S/Ctrl+Q raw input and terminal restoration are application-owned. Use F6/F8/F10 if the client intercepts keys. Uncatchable termination or power loss cannot guarantee restoration.

## ChatGPT connection

Options → Continue with ChatGPT displays the official authorization URL for the user to open in their browser. No browser is launched by the TUI. For a browser on another computer, route the loopback callback with `ssh -t -L 1455:127.0.0.1:1455 samryong@sam-pi` (use a reachable host; callback port is configurable). The explicit private authorization-link file option supports manual retrieval; do not share the URL or credentials. Model choices depend on the account catalog and plan authorization. No API-key billing fallback is introduced. Login and live requests were not attempted during this implementation.

## Verification boundary

The user already observed RGB Sixel output and a `mutool`-rendered sample PDF PNG displayed successfully through img2sixel inside mlterm-fb on the physical Pi. Those are **external pipeline hardware observations**, not Melon Dice integration tests. Melon Dice installation, Python dependencies, PyMuPDF rendering, positioning, redraws, zoom/pan, dialogs, switching and restoration still require user verification. Development used source review and non-interactive static analysis only; no program, graphics probe, conversion experiment or runtime tests were run. See [DEVELOPMENT_REPORT.md](DEVELOPMENT_REPORT.md) for actual checks and the manual checklist.
