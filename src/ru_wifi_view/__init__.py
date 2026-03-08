"""RU-wifi-view: 노트북 WiFi(RSSI) 기반 존재/움직임 감지 MVP 패키지."""

from .types import MotionState, WifiSample, DetectionFeatures, DetectionResult
from .collector import MacOSWifiCollector, SimulatedWifiCollector, WindowsWifiCollector
from .detector import DetectorConfig, PresenceMotionDetector
from .monitor import MonitorConfig, PresenceMonitor
from .storage import HourlyCount, MonitoringStorage, StoredEvent

try:
    from .gui_app import MainWindow, run_gui_app
except ModuleNotFoundError as exc:  # pragma: no cover - PySide6 미설치 환경 호환
    if exc.name and exc.name.startswith("PySide6"):
        MainWindow = None  # type: ignore[assignment]
        run_gui_app = None  # type: ignore[assignment]
    else:
        raise

__all__ = [
    "MotionState",
    "WifiSample",
    "DetectionFeatures",
    "DetectionResult",
    "MacOSWifiCollector",
    "SimulatedWifiCollector",
    "WindowsWifiCollector",
    "DetectorConfig",
    "PresenceMotionDetector",
    "MonitorConfig",
    "PresenceMonitor",
    "StoredEvent",
    "HourlyCount",
    "MonitoringStorage",
    "MainWindow",
    "run_gui_app",
]
