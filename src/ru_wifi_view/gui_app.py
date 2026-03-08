from __future__ import annotations

import platform
import time
from datetime import datetime

from PySide6.QtCore import QObject, QThread, Qt, Signal, Slot
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .collector import BaseCollector, MacOSWifiCollector, SimulatedWifiCollector, WindowsWifiCollector
from .detector import DetectorConfig, PresenceMotionDetector
from .notifier import BaseNotifier, build_notifier
from .storage import MonitoringStorage
from .types import MotionState


def _state_label(state: str) -> str:
    labels = {
        "absent": "부재",
        "present_still": "존재(정지)",
        "active": "존재(움직임)",
    }
    return labels.get(state, state)


def _transition_message(prev_state: str, state: str, confidence: float) -> tuple[str, str]:
    if prev_state == MotionState.ABSENT.value and state == MotionState.PRESENT_STILL.value:
        return "사람 감지", f"정지 상태 감지 (신뢰도 {confidence:.2f})"
    if state == MotionState.ACTIVE.value:
        return "움직임 감지", f"움직임 상태 전환 ({prev_state} -> active)"
    if state == MotionState.ABSENT.value:
        return "부재 전환", f"사람 신호 약화/소실 ({prev_state} -> absent)"
    return "상태 변경", f"{prev_state} -> {state}"


class MonitorWorker(QObject):
    """QThread에서 동작하는 감시 루프 워커."""

    status_updated = Signal(dict)
    transition = Signal(dict)
    selected_mode = Signal(str)
    error = Signal(str)
    finished = Signal()

    def __init__(
        self,
        requested_mode: str,
        detector_config: DetectorConfig,
        sample_rate_hz: float,
        window_seconds: float,
        tick_seconds: float,
        windows_interface: str | None = None,
    ) -> None:
        super().__init__()
        self.requested_mode = requested_mode
        self.detector_config = detector_config
        self.sample_rate_hz = sample_rate_hz
        self.window_seconds = window_seconds
        self.tick_seconds = tick_seconds
        self.windows_interface = windows_interface

        self._running = False
        self._last_state: MotionState | None = None

    @Slot()
    def stop(self) -> None:
        self._running = False

    @Slot()
    def run(self) -> None:
        collector: BaseCollector | None = None
        try:
            collector, selected_mode = self._choose_collector()
            self.selected_mode.emit(selected_mode)

            detector = PresenceMotionDetector(config=self.detector_config)
            collector.start()
            self._running = True

            while self._running:
                loop_started = time.monotonic()

                n_needed = max(1, int(collector.sample_rate_hz * self.window_seconds))
                samples = collector.get_samples(n=n_needed)
                result = detector.detect(samples)

                payload = {
                    "timestamp": time.time(),
                    "state": result.state.value,
                    "confidence": float(result.confidence),
                    "sample_count": int(result.features.sample_count),
                    "variance": float(result.features.variance),
                    "short_term_delta": float(result.features.short_term_delta),
                    "motion_band_power": float(result.features.motion_band_power),
                    "mean_rssi": float(result.features.mean_rssi),
                }
                self.status_updated.emit(payload)

                if self._last_state is not None and result.state != self._last_state:
                    self.transition.emit(
                        {
                            "timestamp": payload["timestamp"],
                            "prev_state": self._last_state.value,
                            "state": result.state.value,
                            "confidence": payload["confidence"],
                            "variance": payload["variance"],
                            "short_term_delta": payload["short_term_delta"],
                            "motion_band_power": payload["motion_band_power"],
                        }
                    )

                self._last_state = result.state

                elapsed = time.monotonic() - loop_started
                sleep_seconds = max(0.05, self.tick_seconds - elapsed)
                deadline = time.monotonic() + sleep_seconds
                while self._running and time.monotonic() < deadline:
                    QThread.msleep(50)

        except Exception as exc:  # pylint: disable=broad-except
            self.error.emit(str(exc))
        finally:
            if collector is not None:
                collector.stop()
            self.finished.emit()

    def _choose_collector(self) -> tuple[BaseCollector, str]:
        system = platform.system()
        mode = self.requested_mode

        if mode == "simulated":
            return SimulatedWifiCollector(sample_rate_hz=self.sample_rate_hz), "simulated"

        if mode == "mac":
            if system != "Darwin":
                raise RuntimeError("--mode mac 는 macOS에서만 사용할 수 있습니다.")
            return MacOSWifiCollector(sample_rate_hz=self.sample_rate_hz), "mac"

        if mode == "windows":
            if system != "Windows":
                raise RuntimeError("--mode windows 는 Windows에서만 사용할 수 있습니다.")
            return (
                WindowsWifiCollector(
                    sample_rate_hz=self.sample_rate_hz,
                    interface_name=self.windows_interface,
                ),
                "windows",
            )

        if mode != "auto":
            raise RuntimeError(f"지원하지 않는 모드: {mode}")

        # auto: 플랫폼별 실측 수집기를 우선 시도, 실패 시 simulated 폴백
        if system == "Darwin":
            try:
                preflight = MacOSWifiCollector(sample_rate_hz=self.sample_rate_hz)
                preflight.start()
                time.sleep(0.8)
                ok = len(preflight.get_samples(3)) > 0
                preflight.stop()
                if ok:
                    return MacOSWifiCollector(sample_rate_hz=self.sample_rate_hz), "mac"
            except Exception:  # pylint: disable=broad-except
                pass

        if system == "Windows":
            try:
                preflight = WindowsWifiCollector(
                    sample_rate_hz=self.sample_rate_hz,
                    interface_name=self.windows_interface,
                )
                preflight.start()
                time.sleep(1.5)
                ok = len(preflight.get_samples(2)) > 0
                preflight.stop()
                if ok:
                    return (
                        WindowsWifiCollector(
                            sample_rate_hz=self.sample_rate_hz,
                            interface_name=self.windows_interface,
                        ),
                        "windows",
                    )
            except Exception:  # pylint: disable=broad-except
                pass

        return SimulatedWifiCollector(sample_rate_hz=self.sample_rate_hz), "simulated"


class MainWindow(QMainWindow):
    def __init__(
        self,
        db_path: str = "data/monitor.db",
        default_mode: str = "auto",
        default_notify: str = "console",
        sample_rate_hz: float = 10.0,
        window_seconds: float = 15.0,
        tick_seconds: float = 1.0,
        cooldown_sec: float = 12.0,
        detector_config: DetectorConfig | None = None,
        windows_interface: str | None = None,
    ) -> None:
        super().__init__()
        self.setWindowTitle("RU-wifi-view GUI Monitor")
        self.resize(1100, 760)

        self.storage = MonitoringStorage(db_path=db_path)
        self.notifier: BaseNotifier = build_notifier(default_notify)

        self.default_mode = default_mode
        self.default_notify = default_notify
        self.sample_rate_hz = sample_rate_hz
        self.window_seconds = window_seconds
        self.tick_seconds = tick_seconds
        self.cooldown_sec = cooldown_sec
        self.detector_config = detector_config or DetectorConfig()
        self.windows_interface = windows_interface

        self._worker_thread: QThread | None = None
        self._worker: MonitorWorker | None = None
        self._session_id: int | None = None
        self._last_notify_ts: float = 0.0

        self.mode_combo = QComboBox()
        self.notify_combo = QComboBox()
        self.start_button = QPushButton("감시 시작")
        self.stop_button = QPushButton("감시 중지")

        self.current_mode_value = QLabel("-")
        self.state_value = QLabel("대기")
        self.confidence_value = QLabel("0.00")
        self.samples_value = QLabel("0")
        self.variance_value = QLabel("0.00")
        self.delta_value = QLabel("0.00")
        self.band_value = QLabel("0.00")
        self.mean_rssi_value = QLabel("0.00 dBm")

        self.events_table = QTableWidget(0, 7)
        self.hourly_table = QTableWidget(0, 2)

        self._build_ui()
        self._reload_recent_events()
        self._reload_hourly_counts()

    def _build_ui(self) -> None:
        central = QWidget(self)
        root = QVBoxLayout(central)

        controls_group = QGroupBox("감시 제어")
        controls_layout = QHBoxLayout(controls_group)

        self.mode_combo.addItems(["auto", "mac", "windows", "simulated"])
        self.notify_combo.addItems(["none", "console", "desktop", "toast", "both"])

        mode_idx = self.mode_combo.findText(self.default_mode)
        if mode_idx >= 0:
            self.mode_combo.setCurrentIndex(mode_idx)

        notify_idx = self.notify_combo.findText(self.default_notify)
        if notify_idx >= 0:
            self.notify_combo.setCurrentIndex(notify_idx)

        controls_layout.addWidget(QLabel("수집 모드"))
        controls_layout.addWidget(self.mode_combo)
        controls_layout.addSpacing(12)
        controls_layout.addWidget(QLabel("알림 모드"))
        controls_layout.addWidget(self.notify_combo)
        controls_layout.addSpacing(20)
        controls_layout.addWidget(self.start_button)
        controls_layout.addWidget(self.stop_button)
        controls_layout.addStretch(1)

        self.stop_button.setEnabled(False)
        self.start_button.clicked.connect(self.start_monitoring)
        self.stop_button.clicked.connect(self.stop_monitoring)

        status_group = QGroupBox("실시간 상태")
        status_layout = QFormLayout(status_group)
        status_layout.addRow("선택된 수집기", self.current_mode_value)
        status_layout.addRow("상태", self.state_value)
        status_layout.addRow("신뢰도", self.confidence_value)
        status_layout.addRow("샘플 수", self.samples_value)
        status_layout.addRow("Variance", self.variance_value)
        status_layout.addRow("Short Delta", self.delta_value)
        status_layout.addRow("Motion Band", self.band_value)
        status_layout.addRow("Mean RSSI", self.mean_rssi_value)

        self.events_table.setHorizontalHeaderLabels(
            ["시각", "이전 상태", "현재 상태", "신뢰도", "Variance", "Delta", "Band"]
        )
        self.events_table.horizontalHeader().setStretchLastSection(True)

        self.hourly_table.setHorizontalHeaderLabels(["시간(로컬)", "감지 횟수"])
        self.hourly_table.horizontalHeader().setStretchLastSection(True)

        root.addWidget(controls_group)
        root.addWidget(status_group)
        root.addWidget(QLabel("최근 상태 전이 이력"))
        root.addWidget(self.events_table, stretch=2)
        root.addWidget(QLabel("최근 24시간 1시간 단위 감지 횟수"))
        root.addWidget(self.hourly_table, stretch=1)

        self.setCentralWidget(central)

    @Slot()
    def start_monitoring(self) -> None:
        if self._worker_thread is not None:
            return

        mode = self.mode_combo.currentText()
        notify_mode = self.notify_combo.currentText()

        try:
            self.notifier = build_notifier(notify_mode)
        except Exception as exc:  # pylint: disable=broad-except
            QMessageBox.critical(self, "알림 초기화 실패", str(exc))
            return

        self._session_id = self.storage.start_session(mode=mode)

        self._worker = MonitorWorker(
            requested_mode=mode,
            detector_config=self.detector_config,
            sample_rate_hz=self.sample_rate_hz,
            window_seconds=self.window_seconds,
            tick_seconds=self.tick_seconds,
            windows_interface=self.windows_interface,
        )
        self._worker_thread = QThread(self)
        self._worker.moveToThread(self._worker_thread)

        self._worker_thread.started.connect(self._worker.run)
        self._worker.status_updated.connect(self._on_status_updated)
        self._worker.transition.connect(self._on_transition)
        self._worker.selected_mode.connect(self._on_selected_mode)
        self._worker.error.connect(self._on_worker_error)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.finished.connect(self._worker_thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)

        self._worker_thread.finished.connect(self._on_worker_thread_finished)
        self._worker_thread.finished.connect(self._worker_thread.deleteLater)

        self._worker_thread.start()

        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.mode_combo.setEnabled(False)
        self.notify_combo.setEnabled(False)
        self.state_value.setText("초기화 중...")
        self._last_notify_ts = 0.0

    @Slot()
    def stop_monitoring(self) -> None:
        if self._worker is not None:
            self._worker.stop()
            self.state_value.setText("중지 중...")

    @Slot(dict)
    def _on_status_updated(self, payload: dict) -> None:
        self.state_value.setText(_state_label(str(payload.get("state", "-"))))
        self.confidence_value.setText(f"{float(payload.get('confidence', 0.0)):.2f}")
        self.samples_value.setText(str(int(payload.get("sample_count", 0))))
        self.variance_value.setText(f"{float(payload.get('variance', 0.0)):.3f}")
        self.delta_value.setText(f"{float(payload.get('short_term_delta', 0.0)):.3f}")
        self.band_value.setText(f"{float(payload.get('motion_band_power', 0.0)):.3f}")
        self.mean_rssi_value.setText(f"{float(payload.get('mean_rssi', 0.0)):.2f} dBm")

    @Slot(dict)
    def _on_transition(self, payload: dict) -> None:
        timestamp = float(payload.get("timestamp", time.time()))
        prev_state = str(payload.get("prev_state", "unknown"))
        state = str(payload.get("state", "unknown"))
        confidence = float(payload.get("confidence", 0.0))
        variance = float(payload.get("variance", 0.0))
        short_term_delta = float(payload.get("short_term_delta", 0.0))
        motion_band_power = float(payload.get("motion_band_power", 0.0))

        self.storage.add_event(
            session_id=self._session_id,
            timestamp=timestamp,
            prev_state=prev_state,
            state=state,
            confidence=confidence,
            variance=variance,
            short_term_delta=short_term_delta,
            motion_band_power=motion_band_power,
        )
        self._reload_recent_events()
        self._reload_hourly_counts()

        if timestamp - self._last_notify_ts < self.cooldown_sec:
            return

        title, message = _transition_message(prev_state=prev_state, state=state, confidence=confidence)
        try:
            self.notifier.notify(title, message)
            self._last_notify_ts = timestamp
        except Exception:  # pylint: disable=broad-except
            pass

    @Slot(str)
    def _on_selected_mode(self, mode: str) -> None:
        self.current_mode_value.setText(mode)
        if self._session_id is not None:
            self.storage.update_session_mode(self._session_id, mode)

    @Slot(str)
    def _on_worker_error(self, message: str) -> None:
        QMessageBox.warning(self, "모니터 오류", message)

    @Slot()
    def _on_worker_finished(self) -> None:
        if self._session_id is not None:
            self.storage.end_session(self._session_id)
            self._session_id = None

    @Slot()
    def _on_worker_thread_finished(self) -> None:
        self._worker = None
        self._worker_thread = None

        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.mode_combo.setEnabled(True)
        self.notify_combo.setEnabled(True)
        self.state_value.setText("대기")

    def _reload_recent_events(self) -> None:
        events = self.storage.get_recent_events(limit=80)
        self.events_table.setRowCount(len(events))

        for row, event in enumerate(events):
            values = [
                datetime.fromtimestamp(event.timestamp).strftime("%Y-%m-%d %H:%M:%S"),
                _state_label(event.prev_state),
                _state_label(event.state),
                f"{event.confidence:.2f}",
                f"{event.variance:.3f}",
                f"{event.short_term_delta:.3f}",
                f"{event.motion_band_power:.3f}",
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.events_table.setItem(row, col, item)

    def _reload_hourly_counts(self) -> None:
        rows = self.storage.get_hourly_detection_counts(hours=24)
        self.hourly_table.setRowCount(len(rows))

        for row, item_data in enumerate(rows):
            values = [item_data.hour_start, str(item_data.total)]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.hourly_table.setItem(row, col, item)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 (Qt 시그니처)
        if self._worker is not None:
            self._worker.stop()

        if self._worker_thread is not None:
            self._worker_thread.quit()
            self._worker_thread.wait(2000)

        if self._session_id is not None:
            self.storage.end_session(self._session_id)
            self._session_id = None

        self.storage.close()
        super().closeEvent(event)


def run_gui_app(
    db_path: str = "data/monitor.db",
    default_mode: str = "auto",
    default_notify: str = "console",
    sample_rate_hz: float = 10.0,
    window_seconds: float = 15.0,
    tick_seconds: float = 1.0,
    cooldown_sec: float = 12.0,
    detector_config: DetectorConfig | None = None,
    windows_interface: str | None = None,
) -> int:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    window = MainWindow(
        db_path=db_path,
        default_mode=default_mode,
        default_notify=default_notify,
        sample_rate_hz=sample_rate_hz,
        window_seconds=window_seconds,
        tick_seconds=tick_seconds,
        cooldown_sec=cooldown_sec,
        detector_config=detector_config,
        windows_interface=windows_interface,
    )
    window.show()
    return int(app.exec())
