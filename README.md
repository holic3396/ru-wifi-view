# RU-wifi-view

[Read this in Korean (README_ko.md)](./README_ko.md)

RU-wifi-view is a lightweight human presence/motion monitor based on laptop Wi-Fi RSSI signals.
It provides both GUI and CLI modes, event history storage, and basic notifications.

> **Acknowledgement**
> This project was developed by referencing and learning from **[RuView](https://github.com/ruvnet/RuView)**.

## Features

- Presence/motion state estimation from Wi-Fi RSSI:
  - `absent`
  - `present_still`
  - `active`
- PySide6 desktop GUI
- Event/history storage with SQLite
- Hourly detection count view (last 24h)
- Notification modes:
  - `none`
  - `console`
  - `desktop` (macOS)
  - `toast` (Windows)
  - `both`
- Multi-mode collectors:
  - `auto`
  - `mac`
  - `windows`
  - `simulated`

## Project Structure

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

## Requirements

- Python 3.10+
- macOS (for CoreWLAN-based collector) or Windows (for netsh-based collector)

Install dependencies:

```bash
python3 -m pip install -r requirements.txt
```

## Quick Start

### GUI (recommended)

```bash
python3 scripts/run_gui.py --mode auto --notify console
```

Windows example:

```powershell
python scripts/run_gui.py --mode auto --notify toast
```

Or:

```powershell
scripts\\run_windows.bat
```

### CLI

Simulated mode:

```bash
python3 scripts/run_monitor.py --mode simulated --notify console
```

macOS mode:

```bash
python3 scripts/run_monitor.py --mode mac --notify both
```

Windows mode:

```powershell
python scripts/run_monitor.py --mode windows --notify toast
```

## Common Options

- `--mode`: `auto | mac | windows | simulated`
- `--notify`: `none | console | desktop | toast | both`
- `--presence-variance-threshold`
- `--motion-delta-threshold`
- `--motion-band-threshold`
- `--cooldown-sec`

## Build

### Windows executable

```powershell
./scripts/build_windows.ps1
```

Output:

```text
dist/RUWifiViewMonitor.exe
```

### macOS app (example)

```bash
python3 -m PyInstaller --clean --noconfirm --windowed --name RUWifiViewMonitor --paths src --add-data 'src/ru_wifi_view/mac_wifi_probe.swift:ru_wifi_view' scripts/run_gui.py
```

## CI/CD (GitHub Actions)

This repository includes two workflows:

- **CI Build** (`.github/workflows/ci.yml`)
  - Trigger: `push`, `pull_request`, manual (`workflow_dispatch`)
  - Builds:
    - Windows: `RUWifiViewMonitor-windows.exe`
    - macOS: `RUWifiViewMonitor-macOS.zip`
  - Outputs are uploaded as workflow artifacts.

- **Release** (`.github/workflows/release.yml`)
  - Trigger:
    - Tag push: `v*` (e.g. `v1.0.0`)
    - Manual run (`workflow_dispatch`) with `tag` input
  - Builds Windows/macOS artifacts and publishes a GitHub Release with both files attached.

### Release usage

Automatic release by tag:

```bash
git tag v1.0.0
git push origin v1.0.0
```

Or run **Actions → Release → Run workflow** and provide a tag name (e.g. `v1.0.0`).

> No additional personal token is required for this setup. It uses the default `GITHUB_TOKEN`.

## Notes

- This is a **coarse signal-based detector** using RSSI only.
- It is not a replacement for camera/CSI-grade sensing.
- For privacy, this repository does not require camera data.

## License

This project is licensed under the **MIT License**.
See [LICENSE](./LICENSE) for details.
