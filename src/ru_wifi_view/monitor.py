from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

from .collector import BaseCollector
from .detector import PresenceMotionDetector
from .notifier import BaseNotifier
from .types import DetectionResult, MotionState


@dataclass
class MonitorConfig:
    window_seconds: float = 15.0
    tick_seconds: float = 1.0
    cooldown_sec: float = 12.0
    run_seconds: float | None = None


class PresenceMonitor:
    def __init__(
        self,
        collector: BaseCollector,
        detector: PresenceMotionDetector,
        notifier: BaseNotifier,
        config: MonitorConfig | None = None,
    ) -> None:
        self.collector = collector
        self.detector = detector
        self.notifier = notifier
        self.config = config or MonitorConfig()

        self._last_state: Optional[MotionState] = None
        self._last_notify_ts: float = 0.0

    def run(self) -> None:
        self.collector.start()
        started = time.time()

        try:
            while True:
                now = time.time()
                if self.config.run_seconds is not None and now - started >= self.config.run_seconds:
                    break

                self._tick(now)
                time.sleep(max(0.05, self.config.tick_seconds))
        finally:
            self.collector.stop()

    def _tick(self, now: float) -> None:
        n_needed = max(1, int(self.collector.sample_rate_hz * self.config.window_seconds))
        samples = self.collector.get_samples(n=n_needed)
        result = self.detector.detect(samples)
        self._print_status(result)
        self._handle_transition(result, now)

    def _print_status(self, result: DetectionResult) -> None:
        f = result.features
        print(
            f"state={result.state.value:<13} conf={result.confidence:.2f} "
            f"n={f.sample_count:>3} var={f.variance:>5.2f} "
            f"delta={f.short_term_delta:>4.2f} band={f.motion_band_power:>6.2f} "
            f"mean={f.mean_rssi:>6.2f}dBm"
        )

    def _handle_transition(self, result: DetectionResult, now: float) -> None:
        if self._last_state is None:
            self._last_state = result.state
            return

        if result.state == self._last_state:
            return

        if now - self._last_notify_ts < self.config.cooldown_sec:
            self._last_state = result.state
            return

        title, msg = self._message_for_transition(self._last_state, result.state, result)
        self.notifier.notify(title, msg)
        self._last_notify_ts = now
        self._last_state = result.state

    @staticmethod
    def _message_for_transition(
        prev: MotionState,
        cur: MotionState,
        result: DetectionResult,
    ) -> tuple[str, str]:
        if prev == MotionState.ABSENT and cur == MotionState.PRESENT_STILL:
            return "사람 감지", f"정지 상태 감지 (신뢰도 {result.confidence:.2f})"
        if cur == MotionState.ACTIVE:
            return "움직임 감지", f"움직임 상태 전환 ({prev.value} -> active)"
        if cur == MotionState.ABSENT:
            return "부재 전환", f"사람 신호 약화/소실 ({prev.value} -> absent)"
        return "상태 변경", f"{prev.value} -> {cur.value}"
