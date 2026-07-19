import signal
import threading
import time

import pytest

from services import render_worker_supervisor as supervisor


def env(enabled="false"):
    return {
        "KHMER_PAYMENT_LISTENER_ENABLED": enabled,
        "TELEGRAM_API_ID": "123",
        "TELEGRAM_API_HASH": "hash",
        "TELEGRAM_SESSION_STRING": "session",
        "TELEGRAM_PAYMENT_CHAT_ID": "100",
        "TELEGRAM_PAYWAY_USER_ID": "200",
        "PAYMENT_INGEST_URL": "https://example.test/api/payments/telegram-ingest",
        "PAYMENT_INGEST_SECRET": "secret",
    }


def test_only_celery_starts_when_feature_flag_false():
    specs = supervisor.build_process_specs(env("false"))
    assert specs == [("celery", supervisor.CELERY_COMMAND)]


def test_celery_and_listener_start_when_feature_flag_true():
    specs = supervisor.build_process_specs(env("true"))
    assert specs == [("celery", supervisor.CELERY_COMMAND), ("khmer-payment-listener", supervisor.LISTENER_COMMAND)]


def test_missing_env_at_true_gives_clear_error():
    bad_env = env("true")
    del bad_env["TELEGRAM_SESSION_STRING"]
    with pytest.raises(RuntimeError, match="TELEGRAM_SESSION_STRING"):
        supervisor.build_process_specs(bad_env)


class FakeProcess:
    instances = []

    def __init__(self, command, **_kwargs):
        self.command = command
        self.terminated = False
        self.killed = False
        self._return_code = None
        FakeProcess.instances.append(self)
        if len(FakeProcess.instances) == 1:
            self._return_code = 1

    def poll(self):
        return self._return_code

    def terminate(self):
        self.terminated = True
        self._return_code = -signal.SIGTERM

    def kill(self):
        self.killed = True
        self._return_code = -signal.SIGKILL

    def wait(self, timeout=None):
        return self._return_code


def test_supervisor_stops_second_process_if_first_crashes(monkeypatch):
    FakeProcess.instances = []
    monkeypatch.setattr(supervisor, "build_process_specs", lambda: [("first", ["first"]), ("second", ["second"])])
    monkeypatch.setattr(supervisor.subprocess, "Popen", FakeProcess)
    assert supervisor.run() == 1
    assert FakeProcess.instances[1].terminated is True


class LongRunningProcess:
    instances = []

    def __init__(self, command, **_kwargs):
        self.command = command
        self.terminated = False
        self._return_code = None
        LongRunningProcess.instances.append(self)

    def poll(self):
        return self._return_code

    def terminate(self):
        self.terminated = True
        self._return_code = -signal.SIGTERM

    def kill(self):
        self._return_code = -signal.SIGKILL

    def wait(self, timeout=None):
        return self._return_code


def test_sigterm_gracefully_stops_both_processes(monkeypatch):
    LongRunningProcess.instances = []
    monkeypatch.setattr(supervisor, "build_process_specs", lambda: [("one", ["one"]), ("two", ["two"])])
    monkeypatch.setattr(supervisor.subprocess, "Popen", LongRunningProcess)
    result = {}
    handlers = {}
    monkeypatch.setattr(supervisor.signal, "signal", lambda sig, handler: handlers.setdefault(sig, handler))
    thread = threading.Thread(target=lambda: result.setdefault("code", supervisor.run()))
    thread.start()
    while len(LongRunningProcess.instances) < 2 or signal.SIGTERM not in handlers:
        time.sleep(0.01)
    handlers[signal.SIGTERM](signal.SIGTERM, None)
    thread.join(timeout=2)
    assert result["code"] == 0
    assert all(process.terminated for process in LongRunningProcess.instances)
