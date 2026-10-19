# Melon Dice

Melon Dice 0.2.0, by SamRyong, is a Python 3.10+ prompt_toolkit TUI with ChatGPT, an original-layout PDF viewer, and a text editor. It runs inside the launching terminal, including Raspberry Pi OS Lite and ordinary interactive SSH. No desktop, graphical window, X11, Wayland, or browser frontend is required.

## One-time installation on the Pi

Copy the project source to the Pi first. These checkout changes are uncommitted and have not been pushed. For example, run this **on the development computer**, adjusting the hostname/directory as needed:

```sh
rsync -av --exclude='.git' --exclude='.venv' --exclude='__pycache__' /Users/samryong/MelonDice/ samryong@sam-pi:~/MelonDice/
```

Then run **on the Pi**, as your regular user without sudo:

```sh
cd "$HOME/MelonDice"
python3 scripts/install.py --profile pi
```

The installer creates the private application environment, installs the project and Python dependencies, checks package dependency consistency, and installs the executable **`~/.local/bin/melondice`**. The environment is internal: no activation or environment path is needed to launch. Installation may download packages. It requires Python 3.10+ with venv/pip support and CA certificates; Debian's `python3-venv` package may be needed. A compatible PyMuPDF aarch64 wheel or native build is required; `mupdf-tools` does not replace the Python dependency. Missing prerequisites are reported; the installer does not install system packages or use sudo.

The Pi profile uses the existing **`$HOME/.local/bin/mlterm-fb`** framebuffer build and requires it to be executable. Sixel uses `img2sixel` on PATH (Debian `libsixel-bin`), already installed according to the user. No mlterm reinstallation or OS display changes are needed. If the existing terminal is elsewhere, specify `--mlterm-fb /actual/path/mlterm-fb` once during installation. With no profile option, first installation detects a Raspberry Pi through its device-tree model; `--profile pi` makes that choice explicit. Later updates preserve the selected profile and terminal path unless explicitly overridden. `--profile terminal` installs for direct use in the current terminal without automatic framebuffer startup.

A new Pi configuration saves `pdf_graphics: sixel`. Existing saved values, including `auto`, `kitty` and `off`, and all other configuration are preserved. To deliberately change an existing preference once, use `python3 scripts/install.py --profile pi --pdf-graphics sixel`, or change PDF graphics in Options and restart. Command-line overrides such as `melondice --pdf-graphics off` remain available for a single run. No repeated graphics option is needed for ordinary launch.

The installer adds one managed PATH block to the appropriate shell files: Bash's active login file and `.bashrc`, Zsh's `.zprofile`/`.zshrc` (honoring ZDOTDIR), or `.profile` for sh/dash/ksh. Reinstallation replaces that block; it does not append duplicate blocks, and the block does not repeatedly prepend an already-leading local bin directory. **Open a new terminal/login after installation**, or make the launcher available in the current bash/zsh/sh session with:

```sh
export PATH="$HOME/.local/bin:$PATH"
```

The installer cannot change its parent shell's PATH. Symlinked shell files are left alone with a clear refusal; for managed dotfiles or other shells, set PATH yourself and use `--no-path-setup`. Existing unrelated or modified executables at `~/.local/bin/melondice` are never overwritten; a collision stops installation and identifies the file for you to resolve.

## Subsequent launch

Type only:

```sh
melondice
```

- **Directly connected bare Linux console on the Pi:** the launcher starts the installed mlterm-fb with the user's existing working font/color arguments and runs Melon Dice as its child command. Normal application exit closes that dedicated terminal session and returns to the original console.
- **Already inside mlterm-fb:** run directly in that terminal, without nesting. An existing terminal stays open when the app exits.
- **SSH:** run in the SSH terminal; never start a local framebuffer terminal. Use an interactive SSH TTY. PDF presentation still depends on the remote client's terminal; a saved Pi Sixel setting does not establish remote-client Sixel support. Use an explicit graphics override when appropriate.
- **Other existing terminal/PTY:** run directly. TERM alone never triggers framebuffer startup.

Routing uses Linux device identity and the controlling foreground terminal, SSH environment/process ancestry, the configured mlterm executable's ancestry, and a launcher-owned session marker. The marker prevents recursion in the dedicated mlterm child; it is not a variable the user needs to set. Normal startup reads the installed environment/settings, checks dependencies and starts the app. It does not invoke pip, download updates, recreate an environment or require the source checkout. Missing installed Python, bootstrap/environment/settings, terminal paths and Python packages produce repair guidance.

Inside the app, choose `2`, Enter, then F3 to open a PDF. The user's sample is `/home/samryong/melondice-pdf-test/test.pdf`. The application itself does not open framebuffer/DRM devices; the Pi launcher delegates terminal presentation to the existing mlterm-fb. The bare Linux console remains unable to display PDF graphics without that terminal.

## Updates

Close Melon Dice, copy updated source to the Pi, then run:

```sh
cd "$HOME/MelonDice"
python3 scripts/install.py
```

Then continue using `melondice`. Updates preserve application data/configuration and saved launch preferences. The installer stages a new private environment, publishes it only after package installation/checking succeeds, and removes old environments bearing its ownership marker while no managed application session is running. Installation locks refuse updates while a managed app/dedicated terminal is active; the default data-directory lock also protects an existing ordinary app session. A package-installation failure leaves the previous environment selected. Installation is not fully transactional across shell/config/launcher files; if later filesystem publication fails, correct the reported path/permission issue and rerun the installer.

Internal installation files live under `~/.local/share/melondice`; private application data/configuration remains under `$XDG_CONFIG_HOME/melondice` or `~/.config/melondice`. Do not move the internal environment manually. These are user instructions only: the installer, launcher, package installation and application startup have **not** been executed by the developer.

## Kitty and Sixel presentation

| Mode (`--pdf-graphics` / `pdf_graphics`) | Selection policy |
| --- | --- |
| `auto` (upstream default; new Pi installs save `sixel`) | On entering PDF, send a random-ID Kitty in-band PNG query and Primary Device Attributes query. Select Kitty on a positive matching PNG acknowledgement within 1.5 seconds. Otherwise, at the deadline select Sixel if DA advertises feature 4 and img2sixel is available. No recognized capability yields a clear text explanation. |
| `kitty` | Require the positive matching PNG acknowledgement within 1.5 seconds. Do not fall back to Sixel. |
| `sixel` | Explicitly trust the user's Sixel terminal selection; require img2sixel and valid cell geometry. No Kitty query/acknowledgement or Sixel advertisement is required. This is the intended choice for the experimentally confirmed mlterm-fb setup. |
| `off` | Disable image presentation and capability/geometry queries; retain chat, editing and PDF file/metadata/password/outline controls. |

A terminal name such as `TERM=xterm` never proves Kitty support; terminal names alone do not disable graphics either. The decision is bounded and retained for the session; late replies are filtered but do not switch protocols. tmux/screen image passthrough is not implemented in any mode: launch outside the multiplexer. Unsupported text terminals remain useful for chat/editing; PDF viewing requires a supported image protocol.

Kitty sends PNG bytes and uses an owned image ID for placement/deletion. Sixel sends a palette raster; it has no equivalent image-ID deletion model. Both reuse the existing spawned PyMuPDF viewport renderer, preserving page layout/aspect ratio, zoom and pan. Sixel encoding uses a captured, asynchronous `img2sixel` subprocess with PNG stdin, encoded stdout and captured stderr. It uses 256 colors, no diffusion and low quantizer quality for responsiveness; gradients/photos may lose color fidelity compared with Kitty PNG. It does not resize or distort the raster.

Sixel images are positioned at the reserved text viewport using the cursor origin, with DECSDM mode and cursor saved/restored. The image height is rounded down to a multiple of six pixels (at most five pixels unused) to contain Sixel bands. A text row remains below the viewport for terminals that advance the cursor after a picture. Cleanup erases picture cells using ECH, then repaints the text screen once. This requires a terminal that erases intersecting Sixel graphics when text cells are erased, as mlterm's picture-cell model does. Terminals with incompatible erasure/positioning behavior are unsupported until verified.

For page changes, zoom and pan within the same document and unchanged viewport geometry, the last successfully displayed image stays visible while the next viewport is rasterized and encoded. The fixed two-row heading distinguishes **Displayed** page/zoom/pan from **Requested** page/zoom/pan and shows Loading, Encoding Sixel, cancellation or failure outside the image region. Text in the reserved image region stays unchanged during updates, so prompt_toolkit's ordinary text redraw does not erase the retained Sixel picture cells. A completed PNG or encoding does not count as displayed until presentation has been sent successfully.

Only the displayed frame and one necessary replacement are retained; there is no page-image cache. Rapid input coalesces native work to the latest destination, cancels obsolete encoding where possible and rejects stale completions, including requests that change away and back. Esc cancels the pending update and preserves the valid visible image where safe. Requested metadata remains explicit after cancellation/failure; changing page/zoom/pan requests another update. A converter failure leaves the old image visible and explains the failure outside the viewport, without globally disabling graphics. A failed native worker requires closing and reopening pdfViewer.

For a same-bounds Sixel replacement, picture-cell erasure and the already finished raster are buffered together and flushed once. There is no separate clear-and-flush step before rendering/encoding finishes. Sixel has no universal atomic frame swap: replacement artifacts or flicker during transmission remain possible and need hardware verification. The background pump polls every 50ms and invalidates text only for changes; it does not erase/retransmit an idle image. Full image transmission can still block terminal output briefly, particularly over slow SSH; no Pi performance claim is made.

Dialog overlays, Home/app switches, document replacement and viewer close remove the picture and discard pending replacement resources. Returning restores the PDF session's requested page/zoom/pan by rendering it again; an obsolete hidden picture is not restored. Resize, pixel-geometry changes and terminal damage may clear/repaint before presenting a correctly bounded frame. Cursor/DECSDM restoration and protocol-specific cleanup remain in place.

## Pixel geometry

Graphics need measured **terminal character-cell pixels**, independent of the `--fontsize=24` font request. There is no hard-coded resolution, IP address or inferred font-to-cell conversion.

On first PDF entry and on cell-grid resize, Melon Dice requests `CSI 16 t` (cell pixels) and `CSI 14 t` (text-area pixels), and checks `TIOCGWINSZ` pixel information against the current grid. A direct cell report takes precedence over whole-area/TTY information. Whole-area dimensions must divide exactly by the current grid; zero/invalid/non-integral values are rejected. Replies are accepted for a bounded 1.5-second geometry window. Old pixel geometry is invalidated at resize instead of reused blindly. This follows the [terminal query definitions](https://invisible-island.net/xterm/ctlseqs/ctlseqs.html).

If the terminal does not report valid geometry, the PDF screen requests an explicit override. Set `--pdf-cell-pixels WIDTHxHEIGHT` to the **independently measured** cell width and height. Accepted range: width 1–256 and height 1–512 pixels. For shell use, first assign your actual measurements to `CELL_WIDTH` and `CELL_HEIGHT`, then run:

```sh
melondice --pdf-cell-pixels "${CELL_WIDTH}x${CELL_HEIGHT}"
```

Measure the terminal's usable text area and divide by its column/row count, or use reliable cell metrics from the terminal; physical monitor resolution and font size alone are insufficient. A wrong override can cause misplaced images. If exact measurements are unavailable, leave images disabled until geometry can be established. An override deliberately takes precedence over queries and must be updated after a font/cell-size change. Font changes that leave the same cell grid may require restarting even in automatic geometry mode.

For future launches with no options, save measured geometry in Options. Options provides all four graphics choices and a cell-pixel field; both apply after restart. CLI values override saved settings for that run. Existing `auto` and `off` configs still load. `config.example.json` uses `"pdf_graphics": "auto"` and `"pdf_cell_pixels": ""` (empty means query). Config is stored in `$XDG_CONFIG_HOME/melondice` or `~/.config/melondice`, or the private directory selected by `--data-dir`. Keep credentials/history private.

## Controls and retained sessions

Home: 1 ChatGPT, 2 pdfViewer, 3 Text editor; the latest valid number selects, Enter opens. F1 returns Home; Alt+Tab/F6 cycles retained sessions; F2 shows Information; Ctrl+O opens Options; Ctrl+Q/F10 closes the app, or exits from Home. Unsaved editor/chat work has Save/Discard/Cancel guards. Chat streaming continues when another app is active. PDF page/zoom/pan and editor buffers/undo/selection remain in memory across switches.

PDF: **< Previous / > Next** (usually Shift+comma / Shift+period), with PageUp/PageDown as optional aliases; G go to page, +/− zoom (25–400%), arrows pan, F3 open/recent files, F4 outline, Esc cancel pending acceptance/display work. Page navigation clamps at the first/last page. Literal `<` and `>` and the PDF viewing controls are active only with a document open and the PDF surface focused, without a dialog; they do not capture typing in chat, editor, file paths, searches or password prompts. Password PDFs are supported. The existing renderer limits documents to 128 MiB and viewports to 12 MP / 16384 pixels per dimension. Conversion is limited to 30 seconds, 128 MiB encoded stdout and 64 KiB diagnostic stderr. No page-image files are exported.

Chat: Enter/F12 send, Ctrl+J newline, Esc stop, F3 local history, F4 attach an existing image, F5 remove, F9 retry, Alt+U usage. Editor: Ctrl+S/F8 save, F7/Alt+S Save As, F3 open, Ctrl+N new, Ctrl+F find/replace, Ctrl+Z undo, Ctrl+Y redo, F9 recovery. Ctrl+C/X/V use a shared internal **text** clipboard; Ctrl+Space/Alt+A starts selection where Shift+arrows is unavailable. No screenshot, image clipboard, PDF editing/OCR/text-extraction substitute/export is implemented. Fonts, size and Korean IME remain terminal/client settings.

The terminal must be an interactive POSIX UTF-8 VT100-compatible TTY; 80×24 cells or larger is recommended. Ctrl+S/Ctrl+Q raw input and terminal restoration are application-owned. Use F6/F8/F10 if the client intercepts keys. Uncatchable termination or power loss cannot guarantee restoration.

## ChatGPT connection

Options → Continue with ChatGPT displays the official authorization URL for the user to open in their browser. No browser is launched by the TUI. For a browser on another computer, route the loopback callback with `ssh -t -L 1455:127.0.0.1:1455 samryong@sam-pi` (use a reachable host; callback port is configurable). The explicit private authorization-link file option supports manual retrieval; do not share the URL or credentials. Model choices depend on the account catalog and plan authorization. No API-key billing fallback is introduced. Login and live requests were not attempted during this implementation.

## Verification boundary

The user already observed RGB Sixel output and a `mutool`-rendered sample PDF PNG displayed successfully through img2sixel inside mlterm-fb on the physical Pi. Those are **external pipeline hardware observations**, not Melon Dice integration tests. The new installer/launcher, Melon Dice installation, Python dependencies, PyMuPDF rendering, positioning, redraws, zoom/pan, dialogs, switching and restoration still require user verification. Development used source review and non-interactive static analysis only; no program, graphics probe, conversion experiment or runtime tests were run. See [DEVELOPMENT_REPORT.md](DEVELOPMENT_REPORT.md) for actual checks and the manual checklist.
