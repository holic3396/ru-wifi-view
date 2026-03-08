from __future__ import annotations

import platform
import subprocess
from abc import ABC, abstractmethod
from datetime import datetime


class BaseNotifier(ABC):
    @abstractmethod
    def notify(self, title: str, message: str) -> None:
        raise NotImplementedError


class NullNotifier(BaseNotifier):
    def notify(self, title: str, message: str) -> None:
        _ = (title, message)


class ConsoleNotifier(BaseNotifier):
    def notify(self, title: str, message: str) -> None:
        now = datetime.now().strftime("%H:%M:%S")
        print(f"[{now}] {title} | {message}")


class MacDesktopNotifier(BaseNotifier):
    def notify(self, title: str, message: str) -> None:
        script = f'display notification "{_escape(message)}" with title "{_escape(title)}"'
        subprocess.run(["osascript", "-e", script], check=False)


class WindowsToastNotifier(BaseNotifier):
    """PowerShell을 이용한 Windows 알림(간이)."""

    def notify(self, title: str, message: str) -> None:
        # BurntToast 모듈이 있으면 우선 사용, 없으면 콘솔 대체 안내만 출력
        ps_script = (
            "$ErrorActionPreference='SilentlyContinue';"
            "if (Get-Module -ListAvailable -Name BurntToast) {"
            f"Import-Module BurntToast; New-BurntToastNotification -Text '{_escape_ps(title)}','{_escape_ps(message)}' | Out-Null"
            "} else {"
            f"Write-Host '[ToastFallback] {_escape_ps(title)} | {_escape_ps(message)}'"
            "}"
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
            check=False,
        )


class CompositeNotifier(BaseNotifier):
    def __init__(self, *notifiers: BaseNotifier) -> None:
        self._notifiers = notifiers

    def notify(self, title: str, message: str) -> None:
        for notifier in self._notifiers:
            notifier.notify(title, message)


def _escape(text: str) -> str:
    return text.replace('"', "\\\"")


def _escape_ps(text: str) -> str:
    return text.replace("'", "''")


def build_notifier(mode: str) -> BaseNotifier:
    mode = mode.lower()
    system = platform.system()

    if mode == "none":
        return NullNotifier()
    if mode == "console":
        return ConsoleNotifier()
    if mode == "desktop":
        if system != "Darwin":
            return ConsoleNotifier()
        return MacDesktopNotifier()
    if mode == "toast":
        if system != "Windows":
            return ConsoleNotifier()
        return WindowsToastNotifier()
    if mode == "both":
        notifiers: list[BaseNotifier] = [ConsoleNotifier()]
        if system == "Darwin":
            notifiers.append(MacDesktopNotifier())
        if system == "Windows":
            notifiers.append(WindowsToastNotifier())
        return CompositeNotifier(*notifiers)
    raise ValueError(f"Unsupported notifier mode: {mode}")
