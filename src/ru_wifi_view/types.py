from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List


class MotionState(str, Enum):
    ABSENT = "absent"
    PRESENT_STILL = "present_still"
    ACTIVE = "active"


@dataclass(frozen=True)
class WifiSample:
    timestamp: float
    rssi_dbm: float
    noise_dbm: float
    tx_rate_mbps: float
    source: str = "unknown"


@dataclass
class DetectionFeatures:
    sample_count: int = 0
    mean_rssi: float = 0.0
    variance: float = 0.0
    std_dev: float = 0.0
    short_term_delta: float = 0.0
    motion_band_power: float = 0.0
    dominant_freq_hz: float = 0.0


@dataclass
class DetectionResult:
    state: MotionState
    confidence: float
    features: DetectionFeatures = field(default_factory=DetectionFeatures)
    reasons: List[str] = field(default_factory=list)
