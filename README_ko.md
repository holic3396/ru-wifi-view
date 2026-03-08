# RU-wifi-view

[Read this in English (README.md)](./README.md)

RU-wifi-view는 노트북 Wi-Fi RSSI 신호를 활용해 사람의 존재/움직임을 추정하는 모니터링 도구입니다.
GUI 및 CLI 모드, 이벤트 이력 저장, 기본 알림 기능을 제공합니다.

> **참고/기반 고지**
> 본 프로젝트는 **[RuView](https://github.com/ruvnet/RuView)** 를 참고하고 학습하여 개발되었습니다.

## 주요 기능

- Wi-Fi RSSI 기반 상태 추정:
  - `absent` (부재)
  - `present_still` (존재/정지)
  - `active` (존재/움직임)
- PySide6 데스크톱 GUI
- SQLite 기반 이벤트/이력 저장
- 최근 24시간 1시간 단위 감지 횟수 조회
- 알림 모드:
  - `none`
  - `console`
  - `desktop` (macOS)
  - `toast` (Windows)
  - `both`
- 수집 모드:
  - `auto`
  - `mac`
  - `windows`
  - `simulated`

## 프로젝트 구조

```text
scripts/run_gui.py
scripts/run_monitor.py
src/ru_wifi_view/
  collector.py
  detector.py
  gui_app.py
  monitor.py
  notifier.py
  storage.py
  types.py
  mac_wifi_probe.swift
scripts/build_windows.ps1
scripts/run_windows.bat
requirements.txt
```

## 요구사항

- Python 3.10+
- macOS(CoreWLAN 수집기) 또는 Windows(netsh 수집기)

의존성 설치:

```bash
python3 -m pip install -r requirements.txt
```

## 빠른 시작

### GUI 실행 (권장)

```bash
python3 scripts/run_gui.py --mode auto --notify console
```

Windows 예시:

```powershell
python scripts/run_gui.py --mode auto --notify toast
```

또는:

```powershell
scripts\\run_windows.bat
```

### CLI 실행

시뮬레이션 모드:

```bash
python3 scripts/run_monitor.py --mode simulated --notify console
```

macOS 모드:

```bash
python3 scripts/run_monitor.py --mode mac --notify both
```

Windows 모드:

```powershell
python scripts/run_monitor.py --mode windows --notify toast
```

## 자주 쓰는 옵션

- `--mode`: `auto | mac | windows | simulated`
- `--notify`: `none | console | desktop | toast | both`
- `--presence-variance-threshold`
- `--motion-delta-threshold`
- `--motion-band-threshold`
- `--cooldown-sec`

## 빌드

### Windows 실행 파일

```powershell
./scripts/build_windows.ps1
```

산출물:

```text
dist/RUWifiViewMonitor.exe
```

### macOS 앱 (예시)

```bash
python3 -m PyInstaller --clean --noconfirm --windowed --name RUWifiViewMonitor --paths src --add-data 'src/ru_wifi_view/mac_wifi_probe.swift:ru_wifi_view' scripts/run_gui.py
```

## CI/CD (GitHub Actions)

이 저장소에는 아래 2개의 워크플로가 포함되어 있습니다.

- **CI Build** (`.github/workflows/ci.yml`)
  - 트리거: `push`, `pull_request`, 수동 실행(`workflow_dispatch`)
  - 빌드 산출물:
    - Windows: `RUWifiViewMonitor-windows.exe`
    - macOS: `RUWifiViewMonitor-macOS.zip`
  - 산출물은 Actions Artifact로 업로드됩니다.

- **Release** (`.github/workflows/release.yml`)
  - 트리거:
    - 태그 푸시: `v*` (예: `v1.0.0`)
    - 수동 실행(`workflow_dispatch`) + `tag` 입력
  - Windows/macOS 산출물 빌드 후 GitHub Release를 생성하고 파일을 첨부합니다.

### 릴리즈 사용 방법

태그 기반 자동 릴리즈:

```bash
git tag v1.0.0
git push origin v1.0.0
```

또는 **Actions → Release → Run workflow** 에서 태그(`v1.0.0` 등)를 입력해 수동 실행할 수 있습니다.

> 별도의 Personal Access Token 없이 기본 `GITHUB_TOKEN`으로 동작합니다.

## 참고 사항

- RSSI 기반의 **거친 추정** 도구입니다.
- 카메라/CSI 급 정밀 센싱을 대체하지 않습니다.
- 카메라 데이터가 필요하지 않아 프라이버시 측면에서 상대적으로 단순합니다.

## 라이선스

이 프로젝트는 **MIT License**를 따릅니다.
자세한 내용은 [LICENSE](./LICENSE)를 참고하세요.
