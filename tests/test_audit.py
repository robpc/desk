"""Tests for desk.audit — the audit-logging module."""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path
from unittest.mock import patch

import pytest

from desk import audit


@pytest.fixture(autouse=True)
def reset_logger():
    """The audit logger is a module-level singleton — reset between tests."""
    audit._reset_for_tests()
    yield
    audit._reset_for_tests()


class TestGetAuditLogger:
    def test_writes_to_local_file(self, tmp_path: Path):
        with patch("desk.audit.logging.handlers.SysLogHandler", side_effect=OSError):
            log = audit.get_audit_logger(tmp_path)
            log.info("event=cmd subcmd=mail exit=0")
            for h in log.handlers:
                h.flush()

        audit_file = tmp_path / "audit.log"
        assert audit_file.exists()
        body = audit_file.read_text()
        assert "event=cmd subcmd=mail exit=0" in body
        assert "user=" in body
        assert "host=" in body

    def test_audit_log_perms_0600(self, tmp_path: Path):
        with patch("desk.audit.logging.handlers.SysLogHandler", side_effect=OSError):
            log = audit.get_audit_logger(tmp_path)
            log.info("event=cmd subcmd=drive exit=0")
            for h in log.handlers:
                h.flush()

        mode = (tmp_path / "audit.log").stat().st_mode & 0o777
        assert mode == 0o600

    def test_idempotent(self, tmp_path: Path):
        with patch("desk.audit.logging.handlers.SysLogHandler", side_effect=OSError):
            log1 = audit.get_audit_logger(tmp_path)
            log2 = audit.get_audit_logger(tmp_path)
            assert log1 is log2
            # Just the file handler (syslog mocked out). Filter to the file
            # handler we add — test runners may attach their own (e.g. log
            # capture). SysLogHandler is patched here, so don't isinstance it.
            file_handlers = [
                h
                for h in log1.handlers
                if isinstance(h, logging.handlers.RotatingFileHandler)
            ]
            assert len(file_handlers) == 1

    def test_syslog_unavailable_falls_back_to_file_only(self, tmp_path: Path):
        with patch("desk.audit.logging.handlers.SysLogHandler", side_effect=OSError):
            log = audit.get_audit_logger(tmp_path)
            log.info("event=cmd subcmd=docs exit=0")
            for h in log.handlers:
                h.flush()
        assert (tmp_path / "audit.log").exists()

    def test_propagation_disabled(self, tmp_path: Path):
        with patch("desk.audit.logging.handlers.SysLogHandler", side_effect=OSError):
            log = audit.get_audit_logger(tmp_path)
            assert log.propagate is False
