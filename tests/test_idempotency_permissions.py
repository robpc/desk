"""Tests for idempotency cache file and directory permission hardening.

Validates that _save_store creates the config directory with 0o700
and the idempotency.json file with 0o600, both for new and pre-existing paths.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from desk.idempotency import _save_store, record_idempotency


@pytest.fixture
def desk_dir(tmp_path: Path):
    """Provide a temporary ~/.desk directory and patch CONFIG_DIR."""
    fake_desk = tmp_path / ".desk"
    fake_idem = fake_desk / "idempotency.json"

    with (
        patch("desk.idempotency.CONFIG_DIR", fake_desk),
        patch("desk.idempotency.IDEMPOTENCY_FILE", fake_idem),
    ):
        yield fake_desk, fake_idem


class TestSaveStorePermissions:
    """Permission assertions for _save_store."""

    def test_new_directory_created_with_0o700(self, desk_dir):
        fake_desk, _ = desk_dir
        assert not fake_desk.exists()

        _save_store({"key": {"operation": "test", "result": {}}})

        dir_mode = fake_desk.stat().st_mode & 0o777
        assert dir_mode == 0o700, f"Expected dir mode 0o700, got {oct(dir_mode)}"

    def test_new_file_created_with_0o600(self, desk_dir):
        _, fake_idem = desk_dir

        _save_store({"key": {"operation": "test", "result": {}}})

        file_mode = fake_idem.stat().st_mode & 0o777
        assert file_mode == 0o600, f"Expected file mode 0o600, got {oct(file_mode)}"

    def test_preexisting_directory_tightened_to_0o700(self, desk_dir):
        fake_desk, _ = desk_dir
        # Create directory with permissive mode (simulates old install)
        fake_desk.mkdir(parents=True, mode=0o755)
        assert (fake_desk.stat().st_mode & 0o777) == 0o755

        _save_store({"key": {"operation": "test", "result": {}}})

        dir_mode = fake_desk.stat().st_mode & 0o777
        assert dir_mode == 0o700, f"Expected dir mode 0o700 after tightening, got {oct(dir_mode)}"

    def test_preexisting_file_tightened_to_0o600(self, desk_dir):
        fake_desk, fake_idem = desk_dir
        # Create directory and file with permissive mode
        fake_desk.mkdir(parents=True, mode=0o755)
        fake_idem.write_text("{}")
        os.chmod(fake_idem, 0o644)
        assert (fake_idem.stat().st_mode & 0o777) == 0o644

        _save_store({"key": {"operation": "test", "result": {}}})

        file_mode = fake_idem.stat().st_mode & 0o777
        assert file_mode == 0o600, f"Expected file mode 0o600 after tightening, got {oct(file_mode)}"

    def test_file_content_is_valid_json(self, desk_dir):
        _, fake_idem = desk_dir
        payload = {"k1": {"operation": "mail.send", "result": {"id": "abc"}}}

        _save_store(payload)

        data = json.loads(fake_idem.read_text())
        assert data == payload


class TestRecordIdempotencyPermissions:
    """End-to-end permission check through the public API."""

    def test_record_sets_correct_permissions(self, desk_dir):
        fake_desk, fake_idem = desk_dir

        record_idempotency(
            key="test-key",
            operation="mail.send",
            result={"message_id": "12345"},
        )

        dir_mode = fake_desk.stat().st_mode & 0o777
        file_mode = fake_idem.stat().st_mode & 0o777
        assert dir_mode == 0o700, f"Expected dir 0o700, got {oct(dir_mode)}"
        assert file_mode == 0o600, f"Expected file 0o600, got {oct(file_mode)}"
