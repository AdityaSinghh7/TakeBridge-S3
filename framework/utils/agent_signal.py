from __future__ import annotations

import os
import signal
import sys
import threading
import time
from typing import Optional

_lock = threading.Lock()
_handler_registered = False

_paused_event = threading.Event()
_exit_event = threading.Event()
_pause_prompt_printed = threading.Event()

_HAS_TTY = sys.stdin.isatty()


def register_signal_handlers() -> None:
    """Ensure our custom SIGINT handler is installed exactly once."""
    global _handler_registered
    with _lock:
        if _handler_registered:
            return
        signal.signal(signal.SIGINT, _signal_handler)
        _handler_registered = True


def clear_signal_state() -> None:
    """Reset pause/exit flags before starting a new run."""
    _paused_event.clear()
    _exit_event.clear()
    _pause_prompt_printed.clear()


def is_paused() -> bool:
    return _paused_event.is_set()


def exit_requested() -> bool:
    return _exit_event.is_set()


def raise_if_exit_requested() -> None:
    if exit_requested():
        raise SystemExit(0)


def wait_for_resume() -> None:
    """
    Block while the orchestrator is paused, allowing the user to resume with ESC
    or terminate with another Ctrl+C.
    """
    if not is_paused():
        return

    if not _HAS_TTY:
        # Without a TTY we cannot collect further input safely; request exit.
        print("\n\n🛑 No interactive TTY detected. Exiting orchestrator …", flush=True)
        _exit_event.set()
        raise_if_exit_requested()
        return

    _maybe_print_pause_banner()

    while is_paused() and not exit_requested():
        try:
            char = _read_char()
        except KeyboardInterrupt:
            _exit_event.set()
            break

        if char is None:
            continue

        code_point = ord(char)
        if code_point == 3:  # Ctrl+C
            print("\n\n🛑 Exiting agent …", flush=True)
            _exit_event.set()
            break
        if code_point == 27:  # ESC
            print("\n\n▶️  Resuming agent workflow …", flush=True)
            _paused_event.clear()
            _pause_prompt_printed.clear()
            break

        print(f"\n   Unknown command: '{char}' (ord: {code_point})", flush=True)

    raise_if_exit_requested()


def sleep_with_interrupt(seconds: float, poll_interval: float = 0.1) -> None:
    """
    Sleep in short intervals so pause/exit signals are honoured promptly.
    """
    deadline = time.monotonic() + max(0.0, seconds)
    while time.monotonic() < deadline:
        raise_if_exit_requested()
        if is_paused():
            wait_for_resume()
            continue
        remaining = deadline - time.monotonic()
        time.sleep(min(poll_interval, max(0.0, remaining)))


def _signal_handler(signum: int, frame: Optional[object]) -> None:
    # SIGINT received in paused mode requests exit. Otherwise enter pause mode.
    if is_paused():
        _exit_event.set()
        print("\n\n🛑 Exiting agent …", flush=True)
    else:
        _paused_event.set()
        _pause_prompt_printed.clear()
        _maybe_print_pause_banner()


def _maybe_print_pause_banner() -> None:
    if _pause_prompt_printed.is_set():
        return
    _pause_prompt_printed.set()
    print(
        "\n\n🔸 Agent Workflow Paused 🔸\n"
        + "=" * 50
        + "\nOptions:\n"
        "  • Press Ctrl+C again to quit\n"
        "  • Press Esc to resume workflow\n"
        + "=" * 50,
        flush=True,
    )


def _read_char() -> Optional[str]:
    """Read a single character without requiring Enter, when possible."""
    if sys.platform.startswith(("darwin", "linux")):
        import termios
        import tty

        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            data = os.read(fd, 1)
            return data.decode("utf-8", errors="ignore") if data else None
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    if os.name == "nt":
        try:
            import msvcrt

            ch = msvcrt.getwch()
            return ch
        except Exception:
            pass

    try:
        data = input("\n[PAUSED] Waiting for input… ")
    except EOFError:
        return None
    return data[0] if data else None
