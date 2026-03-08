from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import List

from .types import DetectionFeatures, DetectionResult, MotionState, WifiSample


@dataclass
class DetectorConfig:
    """존재/움직임 판정 임계치 설정."""

    presence_variance_threshold: float = 0.9
    motion_delta_threshold: float = 0.9
    motion_band_threshold: float = 8.0
    min_samples: int = 20


class PresenceMotionDetector:
    """RSSI 시계열 기반의 단순 존재/움직임 감지기."""

    def __init__(self, config: DetectorConfig | None = None) -> None:
        self.config = config or DetectorConfig()

    def detect(self, samples: List[WifiSample]) -> DetectionResult:
        if len(samples) < self.config.min_samples:
            features = DetectionFeatures(sample_count=len(samples))
            return DetectionResult(
                state=MotionState.ABSENT,
                confidence=0.15,
                features=features,
                reasons=[
                    f"샘플 부족: {len(samples)} < {self.config.min_samples}",
                ],
            )

        features = self._extract_features(samples)

        presence = features.variance >= self.config.presence_variance_threshold
        active = (
            features.short_term_delta >= self.config.motion_delta_threshold
            or features.motion_band_power >= self.config.motion_band_threshold
        )

        if not presence:
            state = MotionState.ABSENT
        elif active:
            state = MotionState.ACTIVE
        else:
            state = MotionState.PRESENT_STILL

        reasons = [
            f"variance={features.variance:.3f} (th={self.config.presence_variance_threshold})",
            f"short_delta={features.short_term_delta:.3f} (th={self.config.motion_delta_threshold})",
            f"motion_band={features.motion_band_power:.3f} (th={self.config.motion_band_threshold})",
            f"dominant_freq={features.dominant_freq_hz:.2f}Hz",
        ]

        confidence = self._confidence(state, features)

        return DetectionResult(
            state=state,
            confidence=confidence,
            features=features,
            reasons=reasons,
        )

    def _extract_features(self, samples: List[WifiSample]) -> DetectionFeatures:
        rssi = [s.rssi_dbm for s in samples]
        timestamps = [s.timestamp for s in samples]

        mean_rssi = statistics.mean(rssi)
        variance = statistics.variance(rssi) if len(rssi) > 1 else 0.0
        std_dev = math.sqrt(max(variance, 0.0))

        # 단기 변화량: 최근 2초 구간의 평균 절대 변화량
        recent_count = self._count_in_recent_window(timestamps, seconds=2.0)
        recent = rssi[-recent_count:] if recent_count > 1 else rssi[-2:]
        diffs = [abs(recent[i] - recent[i - 1]) for i in range(1, len(recent))]
        short_term_delta = statistics.mean(diffs) if diffs else 0.0

        dominant_freq, motion_band_power = self._spectral_features(rssi, timestamps)

        return DetectionFeatures(
            sample_count=len(samples),
            mean_rssi=mean_rssi,
            variance=variance,
            std_dev=std_dev,
            short_term_delta=short_term_delta,
            motion_band_power=motion_band_power,
            dominant_freq_hz=dominant_freq,
        )

    @staticmethod
    def _count_in_recent_window(timestamps: List[float], seconds: float) -> int:
        if not timestamps:
            return 0
        cutoff = timestamps[-1] - seconds
        count = 0
        for ts in reversed(timestamps):
            if ts >= cutoff:
                count += 1
            else:
                break
        return max(1, count)

    @staticmethod
    def _estimate_sample_rate(timestamps: List[float]) -> float:
        if len(timestamps) < 2:
            return 10.0
        deltas = [
            timestamps[i] - timestamps[i - 1]
            for i in range(1, len(timestamps))
            if timestamps[i] > timestamps[i - 1]
        ]
        if not deltas:
            return 10.0
        mean_dt = statistics.mean(deltas)
        if mean_dt <= 0:
            return 10.0
        return max(1.0, min(50.0, 1.0 / mean_dt))

    def _spectral_features(self, rssi: List[float], timestamps: List[float]) -> tuple[float, float]:
        """Naive DFT 기반 dominant 주파수/움직임 대역 파워(0.5~3Hz)."""
        n = len(rssi)
        if n < 8:
            return 0.0, 0.0

        sample_rate = self._estimate_sample_rate(timestamps)
        demeaned = [x - statistics.mean(rssi) for x in rssi]

        half = n // 2
        max_power = -1.0
        dom_freq = 0.0
        motion_band_power = 0.0

        for k in range(1, half + 1):
            freq = (k * sample_rate) / n
            angle = -2.0 * math.pi * k / n
            re = 0.0
            im = 0.0
            for t, x in enumerate(demeaned):
                re += x * math.cos(angle * t)
                im += x * math.sin(angle * t)
            power = (re * re + im * im) / n

            if power > max_power:
                max_power = power
                dom_freq = freq

            if 0.5 <= freq <= 3.0:
                motion_band_power += power

        return dom_freq, motion_band_power

    def _confidence(self, state: MotionState, features: DetectionFeatures) -> float:
        if state == MotionState.ABSENT:
            var_score = 1.0 - min(
                1.0,
                features.variance / max(self.config.presence_variance_threshold, 1e-6),
            )
            conf = 0.55 + 0.40 * var_score
            return max(0.05, min(0.99, conf))

        presence_score = min(
            1.0,
            features.variance / max(self.config.presence_variance_threshold, 1e-6),
        )
        motion_score = min(
            1.0,
            max(
                features.short_term_delta / max(self.config.motion_delta_threshold, 1e-6),
                features.motion_band_power / max(self.config.motion_band_threshold, 1e-6),
            ),
        )

        if state == MotionState.ACTIVE:
            conf = 0.45 + 0.30 * presence_score + 0.25 * motion_score
        else:  # PRESENT_STILL
            still_bonus = 1.0 - motion_score
            conf = 0.45 + 0.40 * presence_score + 0.15 * still_bonus

        return max(0.05, min(0.99, conf))
