#!/usr/bin/env python3
"""노트북 WiFi(RSSI) 기반 존재/움직임 감지 모니터 실행 스크립트."""

from __future__ import annotations

import argparse
import logging
import platform
import sys
import time
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

from ru_wifi_view.collector import (
    MacOSWifiCollector,
    SimulatedWifiCollector,
    WindowsWifiCollector,
)
from ru_wifi_view.detector import DetectorConfig, PresenceMotionDetector
from ru_wifi_view.monitor import MonitorConfig, PresenceMonitor
from ru_wifi_view.notifier import build_notifier


logger = logging.getLogger("run_monitor")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="일반 노트북 WiFi(RSSI) 기반 사람 존재/움직임 감지 모니터"
    )
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
        "--sample-rate",
        type=float,
        default=10.0,
        help="샘플링 주기(Hz)",
    )
    parser.add_argument(
        "--window-seconds",
        type=float,
        default=15.0,
        help="감지 판정 윈도우 길이(초)",
    )
    parser.add_argument(
        "--tick-seconds",
        type=float,
        default=1.0,
        help="상태 갱신 주기(초)",
    )
    parser.add_argument(
        "--run-seconds",
        type=float,
        default=None,
        help="지정 시 해당 시간(초) 후 종료",
    )
    parser.add_argument(
        "--cooldown-sec",
        type=float,
        default=12.0,
        help="상태 알림 쿨다운(초)",
    )

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
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="로그 레벨",
    )
    return parser.parse_args()


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def choose_collector(mode: str, sample_rate_hz: float, windows_interface: str | None):
    system = platform.system()

    if mode == "simulated":
        return SimulatedWifiCollector(sample_rate_hz=sample_rate_hz), "simulated"

    if mode == "mac":
        if system != "Darwin":
            raise RuntimeError("--mode mac 는 macOS에서만 사용할 수 있습니다.")
        return MacOSWifiCollector(sample_rate_hz=sample_rate_hz), "mac"

    if mode == "windows":
        if system != "Windows":
            raise RuntimeError("--mode windows 는 Windows에서만 사용할 수 있습니다.")
        return (
            WindowsWifiCollector(
                sample_rate_hz=sample_rate_hz,
                interface_name=windows_interface,
            ),
            "windows",
        )

    # auto
    if system == "Darwin":
        try:
            mac_collector = MacOSWifiCollector(sample_rate_hz=sample_rate_hz)
            # 간단 프리플라이트: 실제로 샘플이 들어오는지 확인
            mac_collector.start()
            time.sleep(0.8)
            ok = len(mac_collector.get_samples(3)) > 0
            mac_collector.stop()
            if ok:
                logger.info("auto 모드: macOS WiFi 수집기 선택")
                return MacOSWifiCollector(sample_rate_hz=sample_rate_hz), "mac"
            logger.warning("macOS WiFi 샘플이 비어 있어 시뮬레이션으로 폴백")
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("macOS 수집기 초기화 실패, 시뮬레이션 폴백: %s", exc)

    if system == "Windows":
        try:
            win_collector = WindowsWifiCollector(
                sample_rate_hz=sample_rate_hz,
                interface_name=windows_interface,
            )
            win_collector.start()
            time.sleep(1.5)
            ok = len(win_collector.get_samples(2)) > 0
            win_collector.stop()
            if ok:
                logger.info("auto 모드: Windows WiFi 수집기 선택")
                return (
                    WindowsWifiCollector(
                        sample_rate_hz=sample_rate_hz,
                        interface_name=windows_interface,
                    ),
                    "windows",
                )
            logger.warning("Windows WiFi 샘플이 비어 있어 시뮬레이션으로 폴백")
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Windows 수집기 초기화 실패, 시뮬레이션 폴백: %s", exc)

    logger.info("auto 모드: 시뮬레이션 수집기 선택")
    return SimulatedWifiCollector(sample_rate_hz=sample_rate_hz), "simulated"


def main() -> int:
    args = parse_args()
    setup_logging(args.log_level)

    collector, selected_mode = choose_collector(
        args.mode,
        args.sample_rate,
        args.windows_interface,
    )
    detector = PresenceMotionDetector(
        config=DetectorConfig(
            presence_variance_threshold=args.presence_variance_threshold,
            motion_delta_threshold=args.motion_delta_threshold,
            motion_band_threshold=args.motion_band_threshold,
            min_samples=args.min_samples,
        )
    )
    notifier = build_notifier(args.notify)
    monitor = PresenceMonitor(
        collector=collector,
        detector=detector,
        notifier=notifier,
        config=MonitorConfig(
            window_seconds=args.window_seconds,
            tick_seconds=args.tick_seconds,
            cooldown_sec=args.cooldown_sec,
            run_seconds=args.run_seconds,
        ),
    )

    print("\n=== RU-wifi-view Monitor ===")
    print(f"mode={args.mode} (selected={selected_mode}), notify={args.notify}")
    print(
        "thresholds: "
        f"presence_var={args.presence_variance_threshold}, "
        f"motion_delta={args.motion_delta_threshold}, "
        f"motion_band={args.motion_band_threshold}"
    )
    print("Ctrl+C 로 종료\n")

    try:
        monitor.run()
    except KeyboardInterrupt:
        print("\n중단 요청을 받아 종료합니다.")
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("모니터 실행 실패: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
