"""Fixed backup failure classifications; synthetic input, no production access."""

import importlib
import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def backup(monkeypatch):
    scripts = Path(__file__).resolve().parents[2] / "supabase/scripts"
    monkeypatch.syspath_prepend(str(scripts))
    return importlib.import_module("backup_production_prompt")


@pytest.mark.parametrize(("message", "expected"), [
    ("SSL SYSCALL error: EOF detected", "dump_ssl_eof"),
    ("SSL error: unexpected EOF", "dump_ssl_eof"),
    ("SSL connection has been closed unexpectedly", "dump_ssl_connection_closed"),
    ("SSL connection closed", "dump_ssl_connection_closed"),
    ("connection reset by peer", "dump_connection_reset"),
    ("server closed the connection unexpectedly", "dump_server_connection_closed"),
    ("server closed connection unexpectedly", "dump_server_connection_closed"),
    ("connection to server was lost", "dump_connection_lost"),
    ("could not receive data from server", "dump_connection_lost"),
    ("could not send data to server", "dump_connection_lost"),
    ("connection has been closed unexpectedly", "dump_connection_lost"),
    ("canceling statement due to statement timeout", "dump_statement_timeout"),
    ("canceling statement due to lock timeout", "dump_lock_timeout"),
    ("could not obtain lock", "dump_lock_timeout"),
    ("canceling statement due to user request", "dump_cancelled"),
    ("operation cancelled", "dump_cancelled"),
    ("no space left on device", "dump_disk_full"),
    ("disk full", "dump_disk_full"),
    ("COPY failed", "dump_copy_failed"),
    ("error during COPY", "dump_copy_failed"),
    ("COPY command failed", "dump_copy_failed"),
    ("query failed", "dump_query_failed"),
    ("error executing query", "dump_query_failed"),
    ("timeout expired", "dump_timeout"),
    ("connection timed out", "dump_timeout"),
])
def test_specific_dump_failures_are_fixed_codes(backup, message, expected):
    private = '\npassword=PRIVATE_SECRET table "private_trade" (price=12345)'
    assert backup.stderr_code((message + private).encode(), "dump") == expected


def test_specific_cause_wins_over_generic_copy_or_query_failure(backup):
    assert backup.stderr_code(
        b"pg_dump: COPY failed: SSL SYSCALL error: EOF detected", "dump"
    ) == "dump_ssl_eof"
    assert backup.stderr_code(
        b"pg_dump: query failed: ERROR: canceling statement due to lock timeout", "dump"
    ) == "dump_lock_timeout"
    assert backup.stderr_code(
        b"COPY failed: permission denied for private_table", "dump"
    ) == "dump_permission_denied"


def test_unrecognized_or_invalid_bytes_do_not_escape_classifier(backup):
    assert backup.stderr_code(b"\xffprivate password=PRIVATE", "dump") == "dump_or_docker_failed"
    assert backup.stderr_code(b"COPY failed PRIVATE", "encryption") == "crypto_command_failed"


def test_stderr_is_fully_drained_but_memory_capture_is_bounded(backup):
    source = io.BytesIO(b"x" * 100_000 + b"PRIVATE_SECRET")
    captured, thread = backup.capture_stderr(SimpleNamespace(stderr=source))
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert source.closed
    assert captured == b"x" * 65_536
    assert backup.stderr_code(bytes(captured), "dump") == "dump_or_docker_failed"


def test_stream_failure_report_contains_only_sanitized_diagnostics(backup, tmp_path):
    producer = [sys.executable, "-c",
                "import sys; sys.stdout.buffer.write(b'synthetic'); "
                "sys.stderr.write('COPY failed: SSL SYSCALL error: EOF detected; ' + "
                "'postgresql://' + 'private:PRIVATE_SECRET@host/private_table price=12345'); "
                "sys.exit(1)"]
    consumer = [sys.executable, "-c",
                "import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())"]
    with pytest.raises(backup.PipelineFailure) as failure:
        backup.stream_encrypt(producer, backup.clean_environment(), tmp_path / "partial", consumer)
    details = failure.value.details
    assert details["dump_exit_code"] == 1
    assert details["crypto_exit_code"] == 0
    assert details["dump_diagnostic"] == "dump_ssl_eof"
    serialized = json.dumps(details)
    for private in ("PRIVATE_SECRET", "private_table", "price", "postgresql://"):
        assert private not in serialized
