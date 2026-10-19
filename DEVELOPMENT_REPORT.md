# Melon Dice 개발 보고서

기록일: 2026-10-20. 현재 베타 리비전: **0.3.0**. 이번 범위는 `pdfattach`의 로컬 Git 통합, 사용자 문서, 버전 메타데이터 정리입니다. 새 애플리케이션 기능은 구현하지 않았습니다.

## 이번 문서·버전 변경

- `Melon Dice.txt` 원본을 먼저 읽고 SPEC, README, 이전 개발 보고서, 패키지 메타데이터 및 설치기·bootstrap·런처·CLI·설정·저장소·앱 키 바인딩/렌더 훅·PDF backend/viewer·Kitty/Sixel presenter·터미널 기하·채팅/인증/첨부·편집기 소스를 대조했습니다. 적용 범위의 저장소 및 상위 경로에서 `AGENTS.md`는 발견되지 않았습니다. 원본 `Melon Dice.txt`는 기존부터 Git 제외 대상이며 추가하지 않았습니다.
- README를 한국어 실사용 안내로 재작성했습니다. 소개·베타 상태, 기능, 환경, Pi 설치, 실행·업데이트, 조작, 설정, 문제·한계, 라이선스, 간단한 버전 이력 순서입니다. 개발 컴퓨터의 고정 경로/IP와 rsync·pdfattach 기반 배포 절차, 미커밋 전달 안내를 제거했습니다.
- `https://github.com/samdragon2/MelonDice.git`의 `main` clone, Pi의 시스템 도구·Python 3.10+/venv/pip, 일회 설치와 PATH/새 로그인, 종료 후 pull 및 설치기 재실행을 안내했습니다. 별도 설치 환경 때문에 Git pull만으로 앱이 갱신되지 않음을 명시했습니다. 원격 main 게시 전 설치기 부재 가능성도 구분했습니다.
- 새 터미널 준비와 앱 설치를 구별하고, 기존 정상 mlterm 재빌드가 불필요함을 적었습니다. mlterm 3.9.5 공식 framebuffer/빌드 안내 및 소스 옵션을 읽고 `--with-gui=fb`, 로컬 prefix 빌드 예시, 글꼴/fontconfig, 별도 `libsixel-bin`을 안내했습니다. 이 빌드를 실행하거나 Pi의 OS·장치 권한을 바꾸지 않았습니다.
- 일반 런처의 콘솔/기존 터미널/SSH 경로를 구현 의도로 설명했습니다. 실제 코드의 고정 mlterm 인수(`--aafont=true --fontsize=24 --fg=white --bg=black`)를 확인하여 기존 사용자 인수를 자동 보존한다는 오래된 README 주장을 제거했습니다.
- Kitty/Sixel/off/auto, 측정한 문자 셀 기하, CLI 우선순위, XDG 설정·앱 데이터와 설치 환경 위치, 사용자 지정 data-dir의 별도 설정, 브라우저 인증·SSH callback 한계, 주요 단축키를 소스와 대조했습니다. 화면 캡처는 앱 외부 작업이며 QR/직접 ID·비밀번호/휴대 인증 개선/UI 숨기기를 구현 기능으로 소개하지 않았습니다.
- `pyproject.toml`, `src/melondice/__init__.py`, README 및 SPEC의 현재 버전을 **0.3.0**으로 맞췄습니다. CLI `--version`과 Information은 해당 `__version__`을 참조하므로 소스 수준에서 일관됩니다. 출력은 실행하지 않았습니다. SPEC의 런처 설명과 검증 경계도 최신 관찰에 맞췄습니다.

## 버전 선택 근거

기존 Git 이력에서 프로젝트 버전은 **0.2.0**으로 확인됩니다. 원래 TUI 이후 Sixel 지원, 페이지 이동·이전 표시 유지, 설치기·일반 런처 작업이 이 번호 아래 축적되었습니다. 이번 main 통합의 사용자 영향 범위를 구별하기 위해 X를 2에서 3으로 올려 **0.3.0**을 선택했습니다. 베타의 정확한 `0.X.0` 형식을 유지하며 버전을 낮추지 않았습니다. README의 실제 과거 번호 0.2.0은 유지했고 새 과거 버전·릴리스 날짜·게시된 릴리스는 만들지 않았습니다. 태그나 GitHub 게시를 의미하지 않습니다.

## 기존 구현의 개발 이력

다음은 통합할 기존 커밋·이전 보고서의 기록이며 이번 작업에서 기능을 새로 구현한 내역이 아닙니다.

| 커밋 | 내용 |
| --- | --- |
| `d0b9234` | 0.2.0 터미널 TUI 기반: Home/ChatGPT/PDF/편집기, retained sessions, 내부 텍스트 클립보드, 설정·복구·인증 어댑터 |
| `9c276f4` | mlterm-fb용 Sixel PDF presenter, 외부 img2sixel encoding, 그래픽 선택 및 셀 기하·설정 확장 |
| `35fc825` | PDF 헤더 초기화 문제 수정; 지원하지 않는 Label height 대신 고정 높이 Window 사용 |
| `b0e570f` | `<`/`>` 및 PageUp/PageDown 이동, Displayed/Requested 분리, 같은 표시 기하에서 이전 화면 유지; 설치기·bootstrap·일반 런처도 이 시점의 트리에 포함 |

PDF 상태는 요청·native 작업·대체 raster/encoding·실제 표시 프레임을 분리합니다. 최신 요청만 수락하고 오래된 native/encoding 결과를 거부하며 표시 프레임과 필요한 대체 프레임을 유지합니다. 같은 영역의 Sixel 교체는 완성된 출력과 picture-cell 지우기를 한 flush에 묶습니다. 실패·취소 시 안전한 이전 그림을 남기고 상태를 그림 밖에 표시합니다. 메뉴·앱 전환·새 문서·geometry/damage 변경은 지우기·재렌더링 경로를 사용합니다. 완전한 무깜박임이나 원자적 Sixel 교체를 보장하지 않습니다.

기존 설치기는 사용자 전용 환경을 준비하고 의존성 설치/검사가 성공한 뒤 선택합니다. 소유권 기록·잠금으로 관련 없는 실행 파일과 실행 중인 관리 세션을 보호하고 설정·프로필을 보존하도록 구현되어 있습니다. bootstrap은 환경을 찾고 잠금을 유지하며, 런처는 실제 Linux VT·SSH/프로세스 조상·PTY를 구별합니다. 시작 중 pip/업데이트/환경 생성은 하지 않습니다. 이 동작들은 이번 작업에서 실행하지 않았습니다.

이전 보고서는 compileall, 저장소 정적 감사, 기존 Pyflakes 3.4.0 wheel을 이용한 lint, shell 구문 검사, pinned prompt_toolkit 3.0.52 렌더/출력 소스 검토를 통과했다고 기록했습니다. 이는 **이전 작업의 기록**이며 아래의 이번 실제 검사와 구별합니다. 이전 보고서 전체와 세부 구현 diff는 기존 Git 이력에 보존됩니다.

## 사용자 하드웨어 관찰과 검증 경계

**사용자 확인:** 물리 Pi에서 외부 PDF → PNG → img2sixel → mlterm-fb 파이프라인으로 PDF가 표시되었습니다. 이후 Melon Dice 안에서도 PDF 페이지 전환 및 업데이트 중 이전 페이지 유지가 작동했다고 확인했습니다. 알려진 환경은 Pi 5 / Raspberry Pi OS Lite·Debian 13 Trixie aarch64, framebuffer backend mlterm 3.9.5입니다. 이는 개발자의 실행 결과가 아닙니다.

**아직 미확인:** 일반 `melondice` 런처 성공. 최신 보고는 `~/.local/bin/melondice` 파일 누락입니다. PATH 수정만으로 파일이 생성되거나 문제가 해결되었다고 주장하지 않습니다. 설치/repair·자동 mlterm 진입·기존 터미널 유지·콘솔 복귀의 실제 성공, 로그인·추론, 성능·메모리·복원·호환성의 포괄 검증도 확인되지 않았습니다. 휴대 인증 개선과 UI 숨기기는 구현되지 않았습니다.

## 이번에 실제 수행한 검사

아래는 이번 작업에서 실제 통과한 소스 전용 검사입니다. 애플리케이션 모듈을 import하거나 실행하지 않았습니다.

| 검사 | 결과 |
| --- | --- |
| `python3 -X pycache_prefix=/private/tmp/melondice-bytecode -m compileall -q src scripts` | 통과. 시스템 Python 3.9.6으로 구문/bytecode 컴파일만 수행하고 결과는 checkout 밖에 기록했습니다. Python 3.10 런타임 검증은 아닙니다. |
| `/opt/homebrew/bin/python3 -B scripts/static_check.py` | Python 3.14.7에서 통과. 18개 소스 모듈·3개 도구 스크립트를 Python 3.10 grammar로 AST 파싱/코드 객체 컴파일, 심볼·로컬 import·의존성/메타데이터·진입점·JSON 필드·그래픽 모드·필수 문서·공백 정적 감사했습니다. |
| `sh -n scripts/melondice-launcher.sh` | 통과. shell 본문은 실행하지 않았습니다. |
| `/opt/homebrew/bin/python3 -B /private/tmp/melondice-doc-audit.py` | 통과. AST/TOML로 0.3.0 및 기존 0.2.0보다 증가함을 확인, 현재 문서 버전·로컬 Markdown 링크·CLI/설치기 옵션과 스크립트 경로 대조, README의 shell 블록 9개를 `sh -n`으로 구문 검사했습니다. 문서 명령은 실행하지 않았습니다. 일회용 감사 스크립트는 저장소에 추가하지 않았습니다. |
| `git diff --check` 및 최종 diff 검토 | 통과. 변경 범위는 README·개발 보고서·SPEC 및 두 버전 값입니다. |

- 소스 읽기와 Git 상태·커밋·메타데이터·옵션/단축키·설정 경로 대조를 수행했습니다.
- 공식 mlterm 3.9.5 [framebuffer 안내](https://raw.githubusercontent.com/arakiken/mlterm/3.9.5/doc/en/README.fb), [README](https://raw.githubusercontent.com/arakiken/mlterm/3.9.5/README), [configure 소스](https://raw.githubusercontent.com/arakiken/mlterm/3.9.5/configure.in), [Debian libsixel-bin 패키지 안내](https://packages.debian.org/trixie/libsixel-bin)를 읽었습니다. 이는 설치된 바이너리나 빌드의 실행 검사가 아닙니다.

애플리케이션·설치기·bootstrap·런처를 실행하지 않았고 `--help`/`--version`도 실행하지 않았습니다. 패키지 설치, graphics probe, PDF 변환 실험, 로그인·추론, unit/integration/functional/end-to-end 테스트를 수행하지 않았습니다. 화면 미러링·공유·원격 보기·스크린샷을 요청하거나 수행하지 않았습니다. 실제 실행과 런타임 테스트는 사용자만 수행합니다.

## Git 통합 및 게시 상태

시작 시 `pdfattach` HEAD는 `b0e570f`, 로컬 `main`과 로컬에 기록된 `origin/main`은 `d0b9234`였습니다. 작업 트리는 깨끗하여 포함할 기존 미커밋 변경이 없었습니다. `main`은 `pdfattach`의 조상이므로 fast-forward가 가능합니다. 기존 제외 파일인 `.venv`, egg-info, bytecode 및 `Melon Dice.txt`는 추가하지 않습니다.

문서·버전 커밋 후 main에 fast-forward 통합할 예정입니다. 완료 후 이 부분에 실제 커밋·통합 결과와 최종 브랜치를 기록합니다. 원격을 fetch/push하지 않았으므로 origin 추적 ref는 로컬에 이미 저장된 상태만 나타냅니다. GitHub 게시와 main push는 별도 단계입니다.

## 남은 이슈와 사용자 확인 항목

- [ ] 누락된 일반 런처 문제: Pi의 설치 오류·실행 파일 생성·PATH 활성화 후 일반 실행. 성공은 아직 확인되지 않았습니다.
- [ ] 새/기존 mlterm, bare console, SSH에서 실행·종료·콘솔 복귀, 업데이트 잠금·repair·설정 보존.
- [ ] 유효한 geometry 및 글꼴 변경 후 재측정, Kitty/Sixel 별 표시·정리, 창 크기·메뉴·앱 전환·실패·취소 후 복원.
- [ ] 빠른 페이지/확대/패닝 입력과 stale 결과 거부, 그림 경계·클리핑·잔상, 입력 지연·CPU·메모리·장시간 사용. 사용자의 페이지 전환/이전 표시 유지 확인이 이 전체 목록을 검증한 것은 아닙니다.
- [ ] 현재 브라우저 인증과 headless Pi callback, 계정별 모델·권한·실제 요청. QR/직접 비밀번호/휴대 인증 개선/UI 숨기기는 향후 범위이며 이번 작업에서 추가하지 않았습니다.

Sixel의 256색/6픽셀 band·호환 지우기 요구, tmux/screen 이미지 미지원, 128 MiB PDF/12 MP viewport/128 MiB encoding 한계는 유지됩니다. native rasterization은 개별 중단이 불가능하며 오래된 결과를 버리는 방식입니다. 전송은 UI 출력을 잠시 막을 수 있고 비정상 종료·전원 손실은 복원을 보장하지 않습니다. 여러 설치 파일의 게시가 완전히 원자적이지 않아 파일 시스템 오류 후 재설치가 필요할 수 있습니다. 이 한계를 해결하는 새 기능은 추가하지 않았습니다.
