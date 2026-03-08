from __future__ import annotations

import json
import math
import os
import random
import re
import subprocess
import sys
import threading
import time
from abc import ABC, abstractmethod
from collections import deque
from pathlib import Path
from typing import Deque, List, Optional

from .types import WifiSample


class BaseCollector(ABC):
    def __init__(self, sample_rate_hz: float = 10.0, buffer_seconds: int = 120) -> None:
        self.sample_rate_hz = sample_rate_hz
        self._buffer: Deque[WifiSample] = deque(maxlen=max(10, int(sample_rate_hz * buffer_seconds)))
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _loop(self) -> None:
        interval = 1.0 / max(self.sample_rate_hz, 0.1)
        while self._running:
            t0 = time.monotonic()
            sample = self._collect_one()
            if sample is not None:
                with self._lock:
                    self._buffer.append(sample)
            elapsed = time.monotonic() - t0
            time.sleep(max(0.0, interval - elapsed))

    def get_samples(self, n: Optional[int] = None) -> List[WifiSample]:
        with self._lock:
            items = list(self._buffer)
        if n is None:
            return items
        return items[-n:]

    @abstractmethod
    def _collect_one(self) -> Optional[WifiSample]:
        raise NotImplementedError


class SimulatedWifiCollector(BaseCollector):
    def __init__(self, sample_rate_hz: float = 10.0) -> None:
        super().__init__(sample_rate_hz=sample_rate_hz)
        self._start = time.time()
        self._rng = random.Random(42)

    def _collect_one(self) -> Optional[WifiSample]:
        t = time.time() - self._start
        baseline = -55.0
        breathing = 1.2 * math.sin(2 * math.pi * 0.28 * t)
        motion = 0.0
        # 10초 주기로 4초간 움직임 버스트 생성
        if int(t) % 10 < 4:
            motion = 3.0 * math.sin(2 * math.pi * 1.2 * t)
        noise = self._rng.uniform(-0.4, 0.4)
        rssi = baseline + breathing + motion + noise
        return WifiSample(
            timestamp=time.time(),
            rssi_dbm=float(rssi),
            noise_dbm=-92.0,
            tx_rate_mbps=433.0,
            source="simulated",
        )


class MacOSWifiCollector(BaseCollector):
    def __init__(self, sample_rate_hz: float = 10.0) -> None:
        super().__init__(sample_rate_hz=sample_rate_hz)
        base_dir = Path(__file__).resolve().parent
        self._swift_src = str(self._resolve_swift_source(base_dir))
        self._swift_bin = str(self._resolve_swift_binary_path())
        self._proc: Optional[subprocess.Popen] = None

    @staticmethod
    def _resolve_swift_source(base_dir: Path) -> Path:
        candidates: list[Path] = [base_dir / "mac_wifi_probe.swift"]

        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            meipass_path = Path(meipass)
            candidates.extend(
                [
                    meipass_path / "ru_wifi_view" / "mac_wifi_probe.swift",
                    meipass_path / "mac_wifi_probe.swift",
                ]
            )

        exe_path = Path(sys.executable).resolve()
        candidates.extend(
            [
                exe_path.parent / "ru_wifi_view" / "mac_wifi_probe.swift",
                exe_path.parent.parent / "Frameworks" / "ru_wifi_view" / "mac_wifi_probe.swift",
                exe_path.parent.parent / "Resources" / "ru_wifi_view" / "mac_wifi_probe.swift",
            ]
        )

        for candidate in candidates:
            if candidate.exists():
                return candidate

        # 최종 fallback (에러 메시지에 경로가 포함되도록 첫 후보 반환)
        return candidates[0]

    @staticmethod
    def _resolve_swift_binary_path() -> Path:
        if sys.platform == "darwin":
            cache_dir = Path.home() / "Library" / "Caches" / "RUWifiView"
            cache_dir.mkdir(parents=True, exist_ok=True)
            return cache_dir / "mac_wifi_probe"

        # 비-darwin에서는 사용되지 않지만 안전한 fallback 제공
        return Path(__file__).resolve().parent / "mac_wifi_probe"

    def start(self) -> None:
        self._ensure_binary()
        if self._running:
            return
        self._running = True
        self._proc = subprocess.Popen(
            [self._swift_bin],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._proc:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                self._proc.kill()
            self._proc = None
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _ensure_binary(self) -> None:
        if os.path.exists(self._swift_bin):
            return

        if not os.path.exists(self._swift_src):
            raise FileNotFoundError(
                "mac_wifi_probe.swift 를 찾을 수 없습니다: "
                f"{self._swift_src}"
            )

        os.makedirs(os.path.dirname(self._swift_bin), exist_ok=True)
        subprocess.run(
            ["xcrun", "swiftc", "-O", "-o", self._swift_bin, self._swift_src],
            check=True,
        )

    def _read_loop(self) -> None:
        assert self._proc is not None
        while self._running and self._proc and self._proc.poll() is None:
            line = self._proc.stdout.readline()
            if not line:
                continue
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "error" in payload:
                continue
            sample = WifiSample(
                timestamp=float(payload.get("timestamp", time.time())),
                rssi_dbm=float(payload.get("rssi", -80.0)),
                noise_dbm=float(payload.get("noise", -95.0)),
                tx_rate_mbps=float(payload.get("tx_rate", 0.0)),
                source="macos",
            )
            with self._lock:
                self._buffer.append(sample)

    def _collect_one(self) -> Optional[WifiSample]:
        # macOS는 read loop 기반이므로 사용하지 않음
        return None


class WindowsWifiCollector(BaseCollector):
    """Windows `netsh wlan show interfaces` 기반 RSSI 수집기."""

    def __init__(self, sample_rate_hz: float = 2.0, interface_name: str | None = None) -> None:
        # netsh 호출 비용이 크므로 기본 샘플링을 2Hz로 제한
        super().__init__(sample_rate_hz=min(sample_rate_hz, 2.0))
        self.interface_name = interface_name

    def _collect_one(self) -> Optional[WifiSample]:
        try:
            result = subprocess.run(
                ["netsh", "wlan", "show", "interfaces"],
                capture_output=True,
                text=True,
                timeout=4.0,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return None

        text = result.stdout or ""
        if not text.strip():
            return None

        kv = self._parse_key_values(text)

        state = self._pick_value(kv, ["State", "상태", "Status"])
        if state:
            s = state.lower()
            if any(token in s for token in ["disconnected", "not connected", "미연결", "연결 끊김"]):
                return None

        name = self._pick_value(kv, ["Name", "이름"]) or "Wi-Fi"
        if self.interface_name and self.interface_name.lower() not in name.lower():
            # 지정 인터페이스와 다르면 샘플을 버림
            return None

        signal_str = self._pick_value(kv, ["Signal", "신호"])
        signal_pct = self._extract_percent(signal_str) if signal_str else None

        rssi_str = self._pick_value(kv, ["RSSI", "Rssi", "rssi"])
        rssi_dbm = self._extract_float(rssi_str) if rssi_str else None
        if rssi_dbm is None and signal_pct is not None:
            # 0% ~ 100% 를 대략 -90dBm ~ -30dBm으로 선형 매핑
            rssi_dbm = -90.0 + (signal_pct * 0.6)

        if rssi_dbm is None:
            return None

        tx_rate = self._extract_float(
            self._pick_value(
                kv,
                [
                    "Transmit rate (Mbps)",
                    "Receive rate (Mbps)",
                    "송신 속도(Mbps)",
                    "수신 속도(Mbps)",
                    "전송 속도(Mbps)",
                ],
            )
            or "0"
        )

        return WifiSample(
            timestamp=time.time(),
            rssi_dbm=float(rssi_dbm),
            noise_dbm=-95.0,
            tx_rate_mbps=float(tx_rate),
            source=f"windows:{name}",
        )

    @staticmethod
    def _parse_key_values(text: str) -> dict[str, str]:
        kv: dict[str, str] = {}
        for line in text.splitlines():
            if ":" not in line:
                continue
            key, val = line.split(":", 1)
            key = key.strip().lower()
            val = val.strip()
            if key and val:
                kv[key] = val
        return kv

    @staticmethod
    def _pick_value(kv: dict[str, str], candidates: list[str]) -> str | None:
        candidate_l = [c.lower() for c in candidates]
        for key, val in kv.items():
            for cand in candidate_l:
                if key == cand or cand in key:
                    return val
        return None

    @staticmethod
    def _extract_percent(text: str) -> float | None:
        m = re.search(r"(-?\d+(?:\.\d+)?)\s*%", text)
        if not m:
            return None
        try:
            return float(m.group(1))
        except ValueError:
            return None

    @staticmethod
    def _extract_float(text: str) -> float | None:
        m = re.search(r"-?\d+(?:\.\d+)?", text)
        if not m:
            return None
        try:
            return float(m.group(0))
        except ValueError:
            return None
