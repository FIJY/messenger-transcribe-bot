"""Render worker supervisor for Celery and optional Khmer payment listener."""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
import time

from services.khmer_payment_listener import REQUIRED_ENV, is_enabled

LOGGER = logging.getLogger("render-worker-supervisor")
CELERY_COMMAND = [
    "celery",
    "-A",
    "services.transcription.celery_app",
    "worker",
    "--loglevel=info",
    "--concurrency=1",
]
LISTENER_COMMAND = [sys.executable, "-m", "services.khmer_payment_listener"]


def validate_listener_env(env: dict[str, str] | None = None) -> None:
    source = os.environ if env is None else env
    missing = [name for name in REQUIRED_ENV if not source.get(name)]
    if missing:
        raise RuntimeError(
            "KHMER_PAYMENT_LISTENER_ENABLED=true but required environment variables are missing: "
            + ", ".join(missing)
        )


def build_process_specs(env: dict[str, str] | None = None) -> list[tuple[str, list[str]]]:
    source = os.environ if env is None else env
    specs = [("celery", CELERY_COMMAND)]
    if is_enabled(source.get("KHMER_PAYMENT_LISTENER_ENABLED")):
        validate_listener_env(source)
        specs.append(("khmer-payment-listener", LISTENER_COMMAND))
    return specs


def terminate_processes(processes: list[tuple[str, subprocess.Popen]], grace_seconds: float = 10.0) -> None:
    for name, process in processes:
        if process.poll() is None:
            LOGGER.info("[render-worker-supervisor] stopping %s", name)
            process.terminate()
    deadline = time.monotonic() + grace_seconds
    for name, process in processes:
        while process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.1)
        if process.poll() is None:
            LOGGER.warning("[render-worker-supervisor] killing %s after graceful timeout", name)
            process.kill()
    for _, process in processes:
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            pass


def run() -> int:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    shutdown_requested = False
    processes: list[tuple[str, subprocess.Popen]] = []

    def handle_signal(signum: int, _frame: object) -> None:
        nonlocal shutdown_requested
        shutdown_requested = True
        LOGGER.info("[render-worker-supervisor] received signal %s; shutting down", signum)
        terminate_processes(processes)

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    try:
        specs = build_process_specs()
    except RuntimeError as exc:
        LOGGER.error("[render-worker-supervisor] %s", exc)
        return 2

    LOGGER.info("[render-worker-supervisor] starting %s", ", ".join(name for name, _ in specs))
    try:
        for name, command in specs:
            processes.append((name, subprocess.Popen(command)))

        while True:
            for name, process in processes:
                return_code = process.poll()
                if return_code is not None:
                    if shutdown_requested:
                        return 0
                    LOGGER.error("[render-worker-supervisor] %s exited with code %s; stopping siblings", name, return_code)
                    terminate_processes(processes)
                    return return_code if return_code != 0 else 1
            time.sleep(1)
    except Exception:
        LOGGER.exception("[render-worker-supervisor] supervisor crashed; stopping children")
        terminate_processes(processes)
        return 1
    finally:
        terminate_processes(processes)


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
