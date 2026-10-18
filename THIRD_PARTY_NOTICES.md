# Licensing and components

Melon Dice: copyright 2026 SamRyong, **GNU AGPL version 3 or later**. Full terms are in [LICENSE](LICENSE). ChatGPT/OpenAI names identify the official integration; no endorsement or affiliation is claimed.

| Component | Role | Upstream license / reference |
| --- | --- | --- |
| Python | Runtime and POSIX terminal/process support | [PSF](https://docs.python.org/3/license.html) |
| prompt_toolkit | Terminal layout, buffers, selection, input, mouse, alternate screen | [BSD-3-Clause](https://github.com/prompt-toolkit/python-prompt-toolkit/blob/3.0.52/LICENSE) |
| wcwidth | Terminal character widths (prompt_toolkit dependency) | [MIT](https://github.com/jquast/wcwidth/blob/master/LICENSE) |
| HTTPX | Async HTTPS and streaming | [BSD-3-Clause](https://github.com/encode/httpx/blob/master/LICENSE.md) |
| PyJWT | JWT identity validation | [MIT](https://github.com/jpadilla/pyjwt/blob/master/LICENSE) |
| cryptography | Signature primitives | [Apache-2.0 OR BSD-3-Clause](https://cryptography.io/en/latest/faq/#what-license-is-cryptography-distributed-under) |
| Pillow | Attachment validation and in-memory PDF viewport PNG encoding | [HPND/Pillow terms](https://pillow.readthedocs.io/en/stable/about.html#license) |
| PyMuPDF / MuPDF | PDF parsing and original-layout rasterization | [AGPL-3.0 or commercial](https://pymupdf.readthedocs.io/en/latest/about.html) |

Dependencies are installed separately and retain their own/transitive license files. Bundled redistribution must include the required notices/source. The project retains an AGPL-compatible license because of its PDF backend. No GUI toolkit, terminal emulator, font, browser, or dependency binary is bundled. The Kitty graphics protocol is implemented as a terminal transport; it does not embed the Kitty application.
