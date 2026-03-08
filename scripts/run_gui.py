#!/usr/bin/env python3
"""PySide6 GUI 기반 RU-wifi-view 모니터 실행 스크립트."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent


def _resolve_project_root() -> Path:
    """src 디렉터리를 기준으로 프로젝트 루트를 탐색한다."""
    candidates = [SCRIPT_DIR, SCRIPT_DIR.parent]
    for candidate in candidates:
        if (candidate / "src").is_dir():
            return candidate
    return SCRIPT_DIR


PROJECT_ROOT = _resolve_project_root()
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from ru_wifi_view.detector import DetectorConfig


def _default_db_path() -> str:
    """GUI 실행 기본 SQLite 경로를 OS별 사용자 쓰기 가능한 위치로 반환."""
    if sys.platform == "darwin":
        return str(Path.home() / "Library" / "Application Support" / "RUWifiView" / "monitor.db")

    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else (Path.home() / "AppData" / "Roaming")
        return str(base / "RUWifiView" / "monitor.db")

    # linux/other
    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    if xdg_data_home:
        return str(Path(xdg_data_home) / "ru_wifi_view" / "monitor.db")
    return str(Path.home() / ".local" / "share" / "ru_wifi_view" / "monitor.db")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="RU-wifi-view GUI 모니터")
    parser.add_argument(
        "--mode",
        choices=["auto", "mac", "windows", "simulated"],
        default="auto",
        help="데이터 수집 모드",
    )
    parser.add_argument(
        "--notify",
        choices=["none", "console", "desktop", "toast", "both"],
        default="console",
        help="알림 방식",
    )
    parser.add_argument(
        "--windows-interface",
        default=None,
        help="Windows netsh 인터페이스 이름(예: Wi-Fi)",
    )

    parser.add_argument(
        "--db-path",
        default=None,
        help="SQLite DB 파일 경로(미지정 시 OS별 사용자 데이터 경로)",
    )

    parser.add_argument("--sample-rate", type=float, default=10.0, help="샘플링 주기(Hz)")
    parser.add_argument("--window-seconds", type=float, default=15.0, help="판정 윈도우 길이(초)")
    parser.add_argument("--tick-seconds", type=float, default=1.0, help="UI 갱신 주기(초)")
    parser.add_argument("--cooldown-sec", type=float, default=12.0, help="알림 쿨다운(초)")

    parser.add_argument(
        "--presence-variance-threshold",
        type=float,
        default=0.9,
        help="존재 판정 RSSI 분산 임계치",
    )
    parser.add_argument(
        "--motion-delta-threshold",
        type=float,
        default=0.9,
        help="움직임 판정 단기 변화량 임계치",
    )
    parser.add_argument(
        "--motion-band-threshold",
        type=float,
        default=8.0,
        help="움직임 대역(0.5~3Hz) 파워 임계치",
    )
    parser.add_argument(
        "--min-samples",
        type=int,
        default=20,
        help="유효 판정을 위한 최소 샘플 수",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.db_path:
        db_path = args.db_path
    else:
        # Finder 실행(.app)에서는 작업 디렉터리가 '/' 인 경우가 많아
        # 상대 경로(data/monitor.db) 사용 시 쓰기 실패가 발생할 수 있다.
        # 따라서 기본값은 사용자 writable 경로를 사용한다.
        db_path = _default_db_path()

    try:
        from ru_wifi_view.gui_app import run_gui_app
    except Exception as exc:  # pylint: disable=broad-except
        print("PySide6 GUI 모듈을 불러오지 못했습니다.")
        print("`pip install -r requirements.txt` 로 의존성을 설치한 뒤 다시 실행해 주세요.")
        print(f"원인: {exc}")
        return 1

    detector_config = DetectorConfig(
        presence_variance_threshold=args.presence_variance_threshold,
        motion_delta_threshold=args.motion_delta_threshold,
        motion_band_threshold=args.motion_band_threshold,
        min_samples=args.min_samples,
    )

    return run_gui_app(
        db_path=db_path,
        default_mode=args.mode,
        default_notify=args.notify,
        sample_rate_hz=args.sample_rate,
        window_seconds=args.window_seconds,
        tick_seconds=args.tick_seconds,
        cooldown_sec=args.cooldown_sec,
        detector_config=detector_config,
        windows_interface=args.windows_interface,
    )


if __name__ == "__main__":
    raise SystemExit(main())
