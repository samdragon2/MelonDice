# Melon Dice

**현재 버전: 0.3.0 · 베타 개발 중** — made by SamRyong

Melon Dice는 Python `prompt_toolkit` 기반 터미널 TUI입니다. Home에서 ChatGPT, 원본 레이아웃을 보여 주는 PDF viewer, 텍스트 편집기를 오가며 사용합니다. 주 대상은 Raspberry Pi OS Lite이며, 데스크톱 없이 이미지 표시를 지원하는 터미널 안에서 PDF를 볼 수 있습니다.

베타 버전은 `0.X.0` 형식을 사용합니다. 이 번호는 개발 리비전을 뜻하며 GitHub 게시나 릴리스 태그를 의미하지 않습니다. 설치·런처는 구현되어 있지만, 일반 `melondice` 실행의 성공은 아직 확인되지 않았습니다. 가장 최근 보고는 `~/.local/bin/melondice` 실행 파일이 없다는 문제입니다.

## 주요 기능

- **Home / ChatGPT / PDF viewer / Text editor:** 숫자로 선택하고 Enter로 열며, 앱을 전환해도 실행 중인 세션을 유지합니다.
- **ChatGPT:** 브라우저 인증 안내, 스트리밍 응답, 로컬 대화 기록, 기존 이미지 파일 첨부, 중단·재시도 기능을 제공합니다. 실제 로그인·요청 성공과 계정별 이용 가능 여부는 미검증입니다.
- **읽기 전용 PDF:** PyMuPDF로 원래 페이지 배치·도표·수식을 렌더링합니다. Kitty PNG 또는 Sixel로 표시하며 페이지 이동, 목차, 페이지 지정, 확대·축소, 패닝, 암호 입력을 지원합니다.
- **이전 PDF 화면 유지:** 같은 문서에서 표시 영역과 픽셀 기하가 같으면 다음 페이지·확대·이동 화면을 준비하는 동안 마지막 표시 화면을 유지합니다. `Displayed`와 `Requested`를 구분하며, Sixel의 전송 중 깜박임까지 항상 없어진다고 보장하지 않습니다.
- **텍스트 편집:** UTF-8 파일 열기·저장·다른 이름으로 저장, 찾기·바꾸기, 실행 취소·다시 실행, 복구용 자동 저장을 지원합니다.
- **공유 내부 텍스트 클립보드:** 앱 사이에서 선택한 텍스트를 복사·잘라내기·붙여넣기합니다. 운영체제 클립보드와 동기화하지 않으며 종료하면 비워집니다.

전환 중 채팅 초안·생성 상태·스크롤, PDF 문서·페이지·배율·이동 위치, 편집기 미저장 내용·커서·실행 취소 상태가 유지됩니다. 앱을 명시적으로 닫으면 해당 세션은 끝납니다. 프로세스 재시작 후 모든 화면 상태를 복원하는 기능과는 구별됩니다.

## 지원 환경과 준비물

| 항목 | 요구 사항 / 확인 범위 |
| --- | --- |
| 주 대상 | Raspberry Pi OS Lite 64-bit, Linux/POSIX |
| 사용자 하드웨어 관찰 | Raspberry Pi 5 / Debian 13 Trixie aarch64, mlterm 3.9.5 framebuffer 빌드와 `img2sixel` |
| Python | Python 3.10 이상, `venv` 및 pip 사용 가능 |
| 시스템 도구 | Git, CA 인증서, POSIX shell. Sixel에는 `img2sixel` (`libsixel-bin`) 필요 |
| 터미널 | 대화형 TTY, UTF-8, VT100 호환 제어, 80열 × 24행 이상 권장 |
| PDF 이미지 | Kitty 또는 Sixel 지원 및 유효한 문자 셀 픽셀 크기 필요 |
| SSH | 대화형 SSH TTY에서 텍스트 UI 사용 가능. PDF는 접속한 컴퓨터의 터미널 능력에 따라 결정 |

설치기는 Python 의존성(`prompt_toolkit`, HTTPX, PyJWT/cryptography, Pillow, PyMuPDF)을 별도 환경에 설치합니다. 호환되는 PyMuPDF aarch64 wheel이 없으면 네이티브 빌드 도구와 해당 의존성이 추가로 필요합니다. `mupdf-tools`는 PyMuPDF를 대신하지 않습니다. 설치·업데이트 및 ChatGPT 연결에는 네트워크가 필요합니다.

**앱 설치와 이미지 지원 터미널 준비는 별도 작업입니다.** Raspberry Pi OS Lite의 기본 Linux 콘솔은 앱의 PDF 이미지를 직접 표시할 수 없습니다. 알려진 작동 조합은 **framebuffer backend로 빌드한 mlterm 3.9.5 + libsixel-bin의 img2sixel**입니다. 일반 X11용 mlterm 설치만으로 이 구성이 준비되지는 않습니다. 다른 터미널·운영체제의 포괄적 호환성은 확인되지 않았습니다.

## Raspberry Pi 설치

아래 명령은 별도 표시가 없으면 모두 **Pi에서** 사용자가 실행합니다. Melon Dice 설치기는 일반 사용자로 실행하며 `sudo`를 사용하지 않습니다. 시스템 패키지를 준비하는 명령만 관리자 권한을 사용합니다.

### 1. 시스템 도구 준비

```sh
sudo apt update
sudo apt install git python3 python3-venv python3-pip ca-certificates libsixel-bin
```

OS가 제공하는 Python이 3.10 이상이어야 합니다. Melon Dice 설치기는 시스템 패키지나 mlterm을 설치하거나 OS 화면 설정을 바꾸지 않습니다.

### 2. 이미지 지원 터미널 준비

**이미 작동하는 mlterm-fb가 있으면 재빌드하지 말고 3단계로 이동합니다.** 기본 예상 경로는 `$HOME/.local/bin/mlterm-fb`입니다. 다른 위치의 실행 파일은 설치 시 `--mlterm-fb`로 지정할 수 있습니다.

새로 준비하는 경우 [mlterm 3.9.5 framebuffer 안내](https://raw.githubusercontent.com/arakiken/mlterm/3.9.5/doc/en/README.fb)와 [빌드 옵션·의존성 안내](https://raw.githubusercontent.com/arakiken/mlterm/3.9.5/README)를 따릅니다. framebuffer 빌드에는 `--with-gui=fb`가 필요합니다. TrueType 글꼴에는 FreeType이 필요하며, 런처의 `--aafont=true` 사용을 위해 fontconfig 지원도 준비합니다. `--disable-image`는 Sixel을 끄므로 사용하지 않습니다.

Pi에 C/C++ 컴파일러·make·pkg-config와 필요한 개발 라이브러리를 준비한 뒤, 다음은 사용자 로컬 설치 경로를 쓰는 빌드 예시입니다. 아래 절차는 공식 소스에 근거한 안내이며 이번 작업에서 빌드·실행 검증하지 않았습니다.

```sh
sudo apt install build-essential pkg-config libfreetype6-dev libfontconfig1-dev libpng-dev fonts-dejavu-core fonts-noto-cjk
git clone --branch 3.9.5 --depth 1 https://github.com/arakiken/mlterm.git "$HOME/mlterm-3.9.5"
cd "$HOME/mlterm-3.9.5"
./configure --prefix="$HOME/.local" --with-gui=fb
make
make install
```

실제 framebuffer·키보드·마우스 장치 접근 권한과 글꼴 설정은 공식 framebuffer 안내의 Linux 항목을 확인합니다. 글꼴은 `~/.mlterm/font-fb`, `--aafont=true` 사용 시 `~/.mlterm/*aafont`와 fontconfig 설정을 참고합니다. OS·입력기 설정은 Melon Dice가 대신하지 않습니다.

### 3. main 소스를 받아 한 번 설치

새 소스 디렉터리를 만드는 경우 **Pi에서** 실행합니다.

```sh
git clone --branch main https://github.com/samdragon2/MelonDice.git "$HOME/MelonDice"
cd "$HOME/MelonDice"
python3 scripts/install.py --profile pi
```

이 안내는 해당 리비전이 원격 `main`에 게시된 뒤 적용됩니다. 이번 로컬 통합 작업은 GitHub에 push하지 않으므로, 원격 `main` 게시 전에는 이 안내의 설치기가 아직 없을 수 있습니다.

설치기는 `~/.local/bin/melondice` 실행 파일과 `~/.local/share/melondice` 아래 전용 Python 환경을 만듭니다. 직접 가상환경을 활성화할 필요는 없습니다. Pi 프로필은 기존 `mlterm-fb` 실행 파일과, 저장된 모드가 Sixel/auto이면 PATH의 `img2sixel`을 요구합니다.

터미널이 다른 위치에 있는 경우 실제 경로로 바꿔 한 번 지정합니다.

```sh
python3 scripts/install.py --profile pi --mlterm-fb "$HOME/terminal/bin/mlterm-fb"
```

새 Pi 설정에는 `pdf_graphics: sixel`을 저장합니다. 기존 그래픽 모드와 다른 설정은 보존하며, 기존 모드를 의도적으로 바꿀 때만 다음과 같이 지정합니다.

```sh
python3 scripts/install.py --profile pi --pdf-graphics sixel
```

`--profile auto`는 첫 설치에서 Pi 하드웨어를 감지하며 기본값입니다. 업데이트에서는 기존 프로필과 mlterm 경로를 보존합니다. 기존 터미널에서만 직접 실행하려면 `--profile terminal`을 사용합니다.

### 4. PATH 적용

설치 후 **Pi에서 새 로그인/터미널을 열거나**, 현재 Bash/Zsh/sh 세션에서 다음을 실행합니다.

```sh
export PATH="$HOME/.local/bin:$PATH"
```

설치기가 부모 shell의 PATH를 바꿀 수는 없습니다. 지원하는 shell의 시작 파일에는 반복 설치해도 중복되지 않는 PATH 블록을 기록합니다. 심볼릭 링크로 관리하는 dotfile이나 지원하지 않는 shell은 PATH를 직접 설정한 뒤 `python3 scripts/install.py --profile pi --no-path-setup`을 사용합니다. 기존의 다른 실행 파일 또는 수정된 런처와 충돌하면 덮어쓰지 않고 중단합니다.

## 평소 실행과 업데이트

설치 및 PATH 적용 후 **Pi에서** 실행합니다.

```sh
melondice
```

런처에 구현된 실행 경로는 다음과 같습니다. 실제 일반 런처 성공은 아직 미확인이므로 문제 발생 시 아래 해결 안내를 참고합니다.

- **Pi에 직접 연결한 기본 Linux 콘솔:** Pi 프로필은 기존 mlterm-fb를 열고 그 자식으로 앱을 실행하도록 구현되어 있습니다. 정상 종료 시 전용 터미널이 닫히고 원래 콘솔로 돌아가는 동작이 의도되어 있으나 미검증입니다.
- **이미 열린 mlterm-fb 또는 다른 터미널:** 현재 터미널에서 바로 실행하며 중첩 framebuffer 터미널을 열지 않도록 구현되어 있습니다. 기존 터미널은 앱 종료 후 유지하는 경로입니다.
- **SSH:** 접속한 터미널에서 실행하며 Pi의 로컬 framebuffer 터미널을 열지 않습니다. 원격 클라이언트에 맞는 `--pdf-graphics`를 선택합니다. Pi에 저장된 Sixel 설정만으로 SSH 클라이언트의 지원이 보장되지는 않습니다.

Pi 런처는 mlterm에 `--aafont=true --fontsize=24 --fg=white --bg=black`을 전달합니다. 이는 현재 구현의 고정 시작 인수이며 사용자별 기존 시작 인수를 자동으로 가져오지 않습니다. 일반 실행은 패키지 설치·업데이트를 수행하지 않으며 소스 디렉터리도 필요하지 않습니다.

업데이트할 때는 **앱과 런처가 연 전용 터미널을 모두 닫은 뒤 Pi의 소스 디렉터리에서** 실행합니다.

```sh
cd "$HOME/MelonDice"
git switch main
git pull --ff-only origin main
python3 scripts/install.py
```

그다음 다시 `melondice`로 실행합니다. **`git pull`만으로는 별도로 설치된 앱 환경이 갱신되지 않습니다. 반드시 설치기를 다시 실행합니다.** 로컬 수정이나 분기 차이로 Git이 중단하면 변경을 보존하고 먼저 해결합니다. 설치기는 설정·데이터·기존 프로필을 보존하며 실행 중인 관리 세션이 있으면 업데이트를 거부합니다. 패키지 설치 실패 시 이전 선택 환경을 유지하지만, 여러 설정·런처 파일 전체가 하나의 원자적 트랜잭션은 아니므로 파일 권한·디스크 문제를 고친 뒤 재실행이 필요할 수 있습니다.

## 주요 조작

Home에서 `1` ChatGPT, `2` PDF viewer, `3` Text editor를 누르고 Enter로 엽니다. 마지막으로 누른 유효한 번호가 선택됩니다. PDF를 보려면 `2` → Enter → F3 → 파일 선택 순서로 진행합니다.

| 공통 키 | 동작 |
| --- | --- |
| F1 | 상태를 유지하며 Home으로 이동 |
| Alt+Tab / F6 | ChatGPT → PDF → Editor 전환; Home에서는 최근 앱으로 복귀 |
| F2 / Ctrl+O | Information / Options |
| Ctrl+Q / F10 | 현재 앱 닫기; Home에서는 Melon Dice 종료 |
| Ctrl+C / Ctrl+X / Ctrl+V | 선택한 텍스트 복사 / 잘라내기 / 내부 클립보드 붙여넣기 |
| Shift+방향키 / Ctrl+Space / Alt+A | 텍스트 선택; 뒤 두 키는 선택 시작·해제 후 방향키 사용 |
| Esc | 일반 메뉴 취소, 선택 해제, 생성·PDF 업데이트 중단 |

미저장 편집 내용·대화는 Save / Discard / Cancel 결정이 필요합니다. Alt+Tab이 OS에서 가로채지면 F6, 저장·닫기 키가 전달되지 않으면 F8/F10을 사용합니다. 마우스 선택은 터미널의 mouse reporting에 따라 달라집니다.

| 화면 | 주요 키 |
| --- | --- |
| PDF | **`<` 이전 / `>` 다음** (보통 Shift+, / Shift+.); PageUp/PageDown도 선택적으로 사용 가능 |
| PDF | `G` 페이지 지정, `+`/`-` 확대·축소(25–400%), 방향키 패닝, F3 열기·최근 파일, F4 목차, Esc 대기 중 업데이트 취소 |
| ChatGPT | Enter/F12 전송, Ctrl+J 줄바꿈, Ctrl+N 새 대화, F3 로컬 기록, F4 기존 이미지 첨부, F5 첨부 제거, F9 재시도, Alt+U 사용량 안내 |
| ChatGPT | PageUp/PageDown 대화 스크롤, Tab 입력창/대화창 전환, Esc 생성 중단 |
| Editor | Ctrl+S/F8 저장, F7/Alt+S 다른 이름으로 저장, F3 열기, Ctrl+N 새 문서, Ctrl+F 찾기·바꾸기, Ctrl+Z/Y 실행 취소·다시 실행, F9 복구 |

PDF 이동 키는 문서가 열린 PDF 표시 영역에 포커스가 있고 대화상자가 없을 때만 작동합니다. 처음·끝 페이지를 넘지 않으며 다른 입력창의 `<`/`>` 입력을 가로채지 않습니다. PDF 자체의 텍스트 복사·붙여넣기는 지원하지 않습니다.

## 설정

Ctrl+O의 Options에서 계정·모델, 문서 기본 디렉터리, dark/light 테마, 마우스, PDF 그래픽·셀 크기, 공통 단축키, Escape timeout, 대화 저장, 편집기 복구 간격, 인증 callback 포트를 설정합니다. 일반 설정은 저장 즉시 반영하며 **PDF 모드·셀 픽셀 변경은 앱 재시작 후 적용**합니다. 단축키 편집은 Save로 확정합니다.

### 파일 위치와 실행 옵션

| 위치 | 내용 |
| --- | --- |
| `$XDG_CONFIG_HOME/melondice/config.json` 또는 `~/.config/melondice/config.json` | 앱 설정; XDG_CONFIG_HOME 미설정 시 후자 사용 |
| 위 설정 디렉터리 | 계정 인증 정보, 호스트 식별자, 대화·첨부 기록, 최근 PDF, 편집기 복구, 잠금 파일 |
| `~/.local/share/melondice` | 설치기 관리 환경, bootstrap, 런처 설정·설치 잠금; 수동 이동 금지 |
| `~/.local/bin/melondice` | 사용자 실행 런처 |

설정 예시는 [config.example.json](config.example.json)을 참고합니다. 예시의 문서 경로는 자신의 실제 경로로 바꿉니다. 데이터는 사용자 전용 권한으로 저장하지만 암호화·OS keyring 보관은 구현되어 있지 않습니다. 인증 정보·인증 링크를 Git에 넣거나 공유하지 않습니다.

실행 옵션은 **설치된 Pi 또는 해당 컴퓨터의 터미널에서** 사용합니다. CLI 그래픽·셀 크기 옵션은 그 실행에 한해 저장값보다 우선합니다.

| 옵션 | 용도 |
| --- | --- |
| `--help` / `--version` | 도움말 / 버전 출력 |
| `--pdf-graphics auto\|kitty\|sixel\|off` | 이번 실행의 PDF 그래픽 모드 |
| `--pdf-cell-pixels WIDTHxHEIGHT` | 독립적으로 측정한 문자 셀 픽셀 크기 |
| `--data-dir PATH` | 기본값 대신 사용할 비공개 설정·기록 디렉터리; 예: `melondice --data-dir "$HOME/melondice-data"` |

설치기는 기본 XDG 설정만 관리합니다. `--data-dir`로 다른 디렉터리를 사용하면 그곳의 그래픽 설정도 Options 등으로 별도 설정합니다.

### PDF 그래픽 모드

| 모드 | 동작 |
| --- | --- |
| `auto` | Kitty PNG 지원의 긍정 응답을 우선 사용; 없으면 Sixel 기능 광고와 `img2sixel`이 있을 때 Sixel 선택 |
| `kitty` | Kitty PNG의 긍정 응답 필요; Sixel로 자동 전환하지 않음 |
| `sixel` | 사용자가 고른 Sixel 터미널을 신뢰; `img2sixel`과 셀 픽셀 정보 필요. mlterm-fb에 의도된 모드 |
| `off` | 이미지·그래픽 질의 비활성화; 텍스트 UI와 PDF 파일·메타데이터·목차 조작 유지 |

원래 기본값·설정 예시는 `auto`, 새 Pi 설치 설정은 `sixel`입니다. 터미널 이름이나 `TERM=xterm`만으로 지원을 판정하지 않습니다. tmux/screen의 이미지 통과는 지원하지 않으므로 바깥에서 사용합니다. Sixel은 256색 양자화로 사진·그라데이션의 색 정밀도가 낮아질 수 있습니다.

### 픽셀 크기와 글꼴

앱은 PDF 진입·터미널 셀 격자 변경 시 문자 셀/텍스트 영역 픽셀 정보를 질의하고 TTY 정보도 확인합니다. **유효한 값이 없으면 PDF 이미지가 표시되지 않습니다.** `--fontsize=24`는 문자 셀 크기가 아닙니다. 모니터 전체 해상도를 그대로 넣지 않습니다.

터미널의 실제 사용 가능한 텍스트 영역 너비·높이를 열·행 수로 나누거나 신뢰할 수 있는 셀 지표를 사용해 **가로·세로 픽셀 수를 따로 측정**합니다. 허용 범위는 가로 1–256, 세로 1–512입니다. 다음은 템플릿이며 `WIDTHxHEIGHT`를 측정값으로 바꿉니다.

```text
melondice --pdf-cell-pixels WIDTHxHEIGHT
```

반복 실행에는 Options의 셀 픽셀 항목이나 `config.json`의 `pdf_cell_pixels`에 측정값을 저장합니다. 빈 문자열은 자동 질의를 뜻합니다. 잘못된 값은 그림 위치·크기를 어긋나게 하므로 추측하지 않습니다. 글꼴·셀 크기를 바꾸면 override를 다시 측정하고 앱을 재시작합니다.

글꼴 종류·크기·한글 입력기는 터미널/클라이언트 설정입니다. Melon Dice에는 폰트 크기 조절 기능이 없습니다. 전용 Pi 런처는 위에 적힌 24 크기 인수를 사용하므로 다른 시작 크기가 필요하면 원하는 설정으로 연 기존 mlterm-fb에서 앱을 실행합니다.

### ChatGPT 브라우저 인증

Options → ChatGPT account → Continue with ChatGPT에서 표시한 인증 URL을 사용자가 브라우저에서 열고 권한을 부여합니다. TUI가 브라우저를 자동 실행하지는 않습니다. 인증 후 계정에서 사용 가능한 모델을 새로 불러와 선택합니다. 계정·워크스페이스·권한·사용량과 서비스의 허용 여부에 따라 실패할 수 있으며, 로그인·추론 성공을 이 문서가 보장하지 않습니다. API key 과금으로 자동 대체하는 기능은 없습니다.

이미지 첨부는 현재 코드에서 인증·계정 카탈로그와 `gpt-6.1-sol` 허용 목록을 통과해야 합니다. PNG/JPEG/WEBP/비애니메이션 GIF를 파일당 8 MiB·25 MP 이하, 대기 첨부 4개·합계 16 MiB 이하로 받습니다. PDF 파일을 채팅에 직접 첨부하는 기능은 없습니다.

화면 없는 Pi에서는 브라우저가 있는 다른 컴퓨터와 callback 연결이 필요합니다. **브라우저를 사용할 컴퓨터에서**, 실제 Pi 사용자·호스트로 바꿔 연결합니다.

```sh
ssh -t -L 1455:127.0.0.1:1455 USER@PI_HOST
```

그 SSH 세션에서 앱을 실행해 인증을 시작하고, 같은 컴퓨터의 브라우저에서 URL을 엽니다. 기본 callback 포트는 1455이며 Options에서 바꾸면 포워딩 양쪽 포트도 맞춥니다. 별도로 Pi 로컬 화면에서 앱을 쓰는 경우에도 브라우저 컴퓨터의 SSH 포워딩 연결을 유지해야 합니다. callback 포트를 인터넷에 공개할 필요는 없습니다.

내부 Ctrl+C는 브라우저 컴퓨터의 클립보드로 복사하지 않습니다. 긴 URL 전달이 어려우면 인증 화면의 **Save link to private file**을 명시적으로 선택해 데이터 디렉터리의 `oauth-authorization-url.txt`를 두 번째 SSH 세션에서 읽을 수 있습니다. 이 파일은 시도 종료·취소 시 제거됩니다. 링크·토큰은 비공개로 취급합니다. 이 수동 절차의 불편함은 남아 있으며 **휴대 가능한 인증 개선, QR 인증, 앱 안의 ID/비밀번호 직접 로그인, UI 숨기기는 구현되지 않았습니다.**

## 자주 겪는 문제와 현재 한계

| 증상 | 확인·조치 |
| --- | --- |
| `melondice: command not found` | Pi에서 `command -v melondice`, `ls -l "$HOME/.local/bin/melondice"`로 PATH와 파일 존재를 구분합니다. 파일이 있으면 새 로그인 또는 위 PATH export를 적용합니다. |
| `~/.local/bin/melondice`가 없음 | **최근 사용자 보고이며 해결 성공 미확인입니다.** 소스의 `scripts/install.py` 존재와 설치 오류를 확인하고, 전제 조건을 해결한 뒤 `python3 scripts/install.py --profile pi`를 다시 실행합니다. `git pull`만 하거나 PATH만 바꾸어도 없는 파일은 생성되지 않습니다. |
| `scripts/install.py`가 없음 | 체크아웃이 이 리비전의 `main`인지 확인합니다. 원격 게시 전이면 게시가 먼저 필요합니다. |
| mlterm-fb 없음 / 실행 불가 | framebuffer 빌드를 별도로 준비하거나 실제 경로를 설치기의 `--mlterm-fb PATH`로 지정합니다. 앱 설치기는 터미널을 빌드하지 않습니다. |
| img2sixel 없음 | Pi에 `libsixel-bin`을 준비하고 `command -v img2sixel`로 PATH를 확인한 뒤 재시작합니다. |
| pixel geometry unavailable | 위 측정 절차에 따라 `--pdf-cell-pixels` 또는 Options를 설정합니다. 글꼴 크기 숫자를 대입하지 않습니다. |
| 기본 콘솔에서 글자만 표시됨 | 기본 콘솔 자체에는 PDF 이미지 프로토콜이 없습니다. mlterm-fb 안에서 실행해야 합니다. 런처의 자동 진입 경로는 아직 사용자 검증이 필요합니다. |
| SSH에서 PDF가 안 보임 | 로컬 Pi 화면과 별개로 SSH 클라이언트 터미널의 Kitty/Sixel 지원·기하를 확인합니다. 텍스트만 쓰려면 `melondice --pdf-graphics off`를 사용합니다. |
| 터미널 모드/그림 잔상이 이상함 | 복원·호환성은 포괄 검증되지 않았습니다. 비정상 종료·전원 중단은 복원을 보장하지 않습니다. 정상 종료 후 새 터미널에서 다시 시작합니다. |
| PDF 업데이트 취소·실패 | 안전한 경우 이전 그림을 유지합니다. 페이지·배율·패닝을 바꾸어 다시 요청합니다. native worker 실패 안내는 PDF viewer를 닫았다 다시 엽니다. |
| 설치/업데이트 잠금 오류 | 앱 및 전용 터미널·다른 설치기가 종료되었는지 확인합니다. 관리 환경·잠금 파일을 임의로 삭제하지 않습니다. |

사용자가 확인한 것은 **외부 PDF → PNG → img2sixel → mlterm-fb 파이프라인의 실제 Pi 표시**, 그리고 이후 **Melon Dice 안에서 PDF 페이지 전환과 업데이트 중 이전 페이지 유지가 작동한 것**입니다. 일반 `melondice` 런처, 인증 개선·UI 숨기기, 성능·메모리·복원·호환성의 포괄 검증은 확인되지 않았습니다. 이번 문서 작업은 소스·구문·정적 검사만 수행합니다.

같은 문서·같은 표시 기하에서 이전 그림을 유지해도 Sixel 전송은 모든 터미널에서 원자적으로 교체되지 않으며 깜박임이 남을 수 있습니다. 메뉴·앱 전환·문서 교체·창 크기 변경 때는 그림을 지우고 재렌더링할 수 있습니다. 느린 터미널 전송은 입력을 잠시 지연시킬 수 있습니다.

PDF는 128 MiB 이하, 렌더링 viewport는 12 MP 및 한 변 16384픽셀 이하로 제한됩니다. Sixel 변환은 30초·인코딩 출력 128 MiB 제한이 있습니다. PDF 편집·OCR·검색·텍스트 선택/복사·내보내기는 지원하지 않습니다. 편집기 파일은 UTF-8/BOM 일반 텍스트 8 MiB 이하입니다. **스크린샷은 앱 밖에서 수행하는 작업이며 앱에는 화면 캡처·이미지 클립보드 기능이 없습니다.**

## 라이선스와 관련 문서

Melon Dice는 [GNU AGPL-3.0-or-later](LICENSE)입니다. 구성 요소별 조건은 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)를 참고합니다.

- [SPEC.md](SPEC.md): 현재 구현 명세와 경계
- [DEVELOPMENT_REPORT.md](DEVELOPMENT_REPORT.md): 개발 이력, 실제 정적 검사, 사용자 관찰, 미해결 항목 및 Git 통합 결과
- [config.example.json](config.example.json): 설정 예시

## 간단한 버전 이력

버전은 저장소에서 확인한 개발 번호입니다. 게시된 릴리스나 태그를 뜻하지 않습니다.

### 0.3.0

- PDF Sixel 표시와 Kitty 선택 경로를 통합하고 `<`/`>` 페이지 이동 및 PageUp/PageDown 별칭을 제공합니다.
- 같은 표시 기하의 업데이트 중 이전 페이지를 유지하고 Displayed/Requested를 구분합니다. 사용자가 앱 안의 페이지 전환·이전 페이지 유지를 확인했으며, 모든 Sixel 출력의 무깜박임을 보장하지 않습니다.
- 일회 설치기·일반 `melondice` 런처와 콘솔/기존 터미널 분기를 포함합니다. 최신 보고는 런처 파일 누락이며 일반 실행 성공은 미확인입니다.
- 한국어 사용자 안내와 main 기반 설치·재설치 업데이트 절차를 정리했습니다.

### 0.2.0

- Home·ChatGPT·원본 레이아웃 PDF·텍스트 편집기를 갖춘 터미널 TUI와 세션 유지, 내부 텍스트 클립보드 기반을 도입했습니다.
- 이후 pdfattach 작업도 이 번호 아래 개발되었으며, 위 0.3.0 항목은 이번 통합 범위를 묶은 것입니다.
