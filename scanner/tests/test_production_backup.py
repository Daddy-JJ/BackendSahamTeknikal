"""Security boundaries and real age round-trip using synthetic bytes only."""

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "supabase/scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location(
    "production_backup", SCRIPTS / "backup_production_prompt.py")
backup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(backup)


def test_backup_is_fixed_target_readonly_and_never_argv_password():
    for kind in ("database", "roles"):
        command = backup.dump_command(kind, "idx-backup-test", Path("C:/public-ca.crt"))
        assert backup.HOST in command
        assert backup.USER in command
        assert backup.IMAGE in command
        assert "PGPASSWORD" in command
        assert "--read-only" in command
        assert "--no-password" in command
        assert "--role=postgres" in command
        assert not any(arg.startswith("postgresql://") for arg in command)
    assert "--no-role-passwords" in backup.dump_command("roles", "test", Path("ca"))
    assert "--format=custom" in backup.dump_command("database", "test", Path("ca"))


def test_crypto_child_does_not_inherit_credentials(monkeypatch):
    for name in ("PGPASSWORD", "PGSERVICEFILE", "SUPABASE_SECRET_KEY", "EODHD_API_TOKEN",
                 "AGE_PASSPHRASE", "UNRELATED_PROVIDER_API_KEY"):
        monkeypatch.setenv(name, "synthetic-secret")
    clean = backup.clean_environment()
    assert not any(name in clean for name in ("PGPASSWORD", "PGSERVICEFILE",
                                             "SUPABASE_SECRET_KEY", "EODHD_API_TOKEN",
                                             "AGE_PASSPHRASE", "UNRELATED_PROVIDER_API_KEY"))
    assert os.environ["PGPASSWORD"] == "synthetic-secret"


def test_invalid_backup_kind_rejected():
    with pytest.raises(ValueError, match="invalid_backup_kind"):
        backup.dump_command("unknown", "test", Path("ca"))


def test_binary_roundtrip_and_exclusive_destination(tmp_path):
    # Exercises exactly the binary pipeline used for dumps, with no production connection.
    producer = [sys.executable, "-c", "import sys; sys.stdout.buffer.write(bytes(range(256))*8192)"]
    consumer = [sys.executable, "-c",
                "import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())"]
    destination = tmp_path / "synthetic.bin"
    expected = backup.stream_encrypt(producer, backup.clean_environment(), destination, consumer)
    actual = backup.decrypted_digest([sys.executable, "-c",
                                     "import sys; "
                                     "sys.stdout.buffer.write(open(sys.argv[1],'rb').read())",
                                     str(destination)])
    assert actual == expected
    assert actual[1] == 256 * 8192
    with pytest.raises(FileExistsError):
        backup.stream_encrypt(producer, backup.clean_environment(), destination, consumer)


def test_failed_producer_is_not_a_backup(tmp_path):
    producer = [sys.executable, "-c",
                "import sys; sys.stdout.buffer.write(b'partial'); sys.exit(1)"]
    consumer = [sys.executable, "-c",
                "import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())"]
    with pytest.raises(RuntimeError, match="encrypted_backup_pipeline_failed"):
        backup.stream_encrypt(producer, backup.clean_environment(), tmp_path / "partial", consumer)


def test_early_crypto_exit_reports_broken_pipe_without_raw_secret(tmp_path):
    producer = [sys.executable, "-c",
                "import sys; sys.stdout.buffer.write(b'x'*2097152)"]
    consumer = [sys.executable, "-c",
                "import sys; sys.stderr.write('could not read passphrase: synthetic-secret'); "
                "sys.exit(2)"]
    with pytest.raises(backup.PipelineFailure) as failure:
        backup.stream_encrypt(producer, backup.clean_environment(), tmp_path / "empty", consumer)
    details = failure.value.details
    assert details["crypto_exit_code"] == 2
    assert details["broken_pipe"] is True
    assert details["crypto_diagnostic"] == "crypto_hidden_prompt_failed"
    assert "synthetic-secret" not in repr(details)


def test_dump_permission_failure_is_classified_without_raw_record(tmp_path):
    producer = [sys.executable, "-c",
                "import sys; sys.stderr.write('permission denied for synthetic-private-table'); "
                "sys.exit(1)"]
    consumer = [sys.executable, "-c",
                "import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())"]
    with pytest.raises(backup.PipelineFailure) as failure:
        backup.stream_encrypt(producer, backup.clean_environment(), tmp_path / "partial", consumer)
    assert failure.value.details["dump_diagnostic"] == "dump_permission_denied"
    assert "synthetic-private-table" not in repr(failure.value.details)


def test_diagnostics_are_fixed_codes_only():
    assert backup.stderr_code(b"passphrases do not match: private", "encryption") == (
        "crypto_passphrase_confirmation_mismatch")
    assert backup.stderr_code(b"incorrect passphrase: private", "encryption") == (
        "crypto_incorrect_passphrase")
    assert backup.stderr_code(b"unrecognized option: private", "dump") == "dump_arguments_invalid"
    assert backup.stderr_code(b"private unrecognized message", "encryption") == (
        "crypto_command_failed")
    assert backup.stderr_code(b"", "dump") == "no_driver_diagnostic"


def test_failed_decryption_is_not_verified():
    with pytest.raises(RuntimeError, match="backup_decryption_failed"):
        backup.decrypted_digest([sys.executable, "-c", "raise SystemExit(1)"])


@pytest.mark.skipif(not backup.AGE.exists(), reason="Pinned Windows age not installed")
def test_real_age_encryption_decryption_and_tamper(tmp_path):
    # Ephemeral identity belongs only to this synthetic local test; never log its contents.
    identity = tmp_path / "synthetic-identity.txt"
    keygen = backup.AGE.with_name("age-keygen.exe")
    subprocess.run([str(keygen), "-o", str(identity)], check=True, capture_output=True)
    recipient = subprocess.run([str(keygen), "-y", str(identity)], check=True,
                               capture_output=True, text=True).stdout.strip()
    destination = tmp_path / "synthetic.age"
    producer = [sys.executable, "-c", "import sys; sys.stdout.buffer.write(bytes(range(256))*8192)"]
    expected = backup.stream_encrypt(producer, backup.clean_environment(), destination,
                                     [str(backup.AGE), "--encrypt", "--recipient", recipient])
    assert backup.decrypted_digest([str(backup.AGE), "-d", "-i", str(identity),
                                    str(destination)]) == expected
    encrypted = bytearray(destination.read_bytes())
    encrypted[-1] ^= 1
    destination.write_bytes(encrypted)
    with pytest.raises(RuntimeError, match="backup_decryption_failed"):
        backup.decrypted_digest([str(backup.AGE), "-d", "-i", str(identity), str(destination)])
