"""Tests for granted-scope persistence and the scope gate.

Covers issue #82: the granted scope set was never persisted, so
`_missing_scopes()` compared `SCOPES` against `SCOPES` and returned `[]` for
every user. See ADR-034.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from desk import auth
from desk.config import SCOPES

A_SCOPE = "https://www.googleapis.com/auth/calendar"
PRESENTATIONS = "https://www.googleapis.com/auth/presentations"
# The scope ADR-026 added, so the one existing tokens are most likely to lack.
B_SCOPE = PRESENTATIONS


@pytest.fixture
def token_store(tmp_path):
    """Isolate token storage: empty keyring, token file under tmp_path."""
    keyring: dict = {}

    def get_token():
        return keyring.get("token")

    def set_token(data):
        keyring["token"] = data

    token_file = tmp_path / "token.json"
    with (
        patch("desk.auth.keyring_store.get_token", side_effect=get_token),
        patch("desk.auth.keyring_store.set_token", side_effect=set_token),
        patch("desk.auth.TOKEN_FILE", token_file),
        patch("desk.auth.ensure_config_dir", lambda: tmp_path),
    ):
        yield {"keyring": keyring, "file": token_file}


def _creds(granted=None, requested=None):
    """A credentials double shaped like google-auth's Credentials."""
    creds = MagicMock()
    creds.granted_scopes = granted
    creds.scopes = requested if requested is not None else list(SCOPES)
    creds.quota_project_id = None
    creds.to_json.return_value = json.dumps(
        {
            "token": "at",
            "refresh_token": "rt",
            "client_id": "cid",
            "client_secret": "secret",
            "token_uri": "https://oauth2.googleapis.com/token",
            # google-auth writes the *requested* set here, never the granted one
            "scopes": creds.scopes,
        }
    )
    return creds


class TestGrantedScopePersistence:
    def test_save_records_granted_set(self, token_store):
        auth._save_credentials(_creds(granted=[A_SCOPE]))

        stored = token_store["keyring"]["token"]
        assert stored[auth.GRANTED_SCOPES_KEY] == [A_SCOPE]

    def test_granted_set_survives_scrubbing(self, token_store):
        """The granted set is non-sensitive, so it stays in the on-disk file."""
        auth._save_credentials(_creds(granted=[A_SCOPE]))

        on_disk = json.loads(token_store["file"].read_text())
        assert on_disk[auth.GRANTED_SCOPES_KEY] == [A_SCOPE]
        for secret in auth._TOKEN_SENSITIVE_FIELDS:
            assert secret not in on_disk

    def test_save_without_granted_set_preserves_prior_record(self, token_store):
        """A save from a non-refreshed object must not wipe known truth.

        google-auth only populates `granted_scopes` from a live token response,
        so a routine save would otherwise erase it.
        """
        auth._save_credentials(_creds(granted=[A_SCOPE]))
        auth._save_credentials(_creds(granted=None))

        stored = token_store["keyring"]["token"]
        assert stored[auth.GRANTED_SCOPES_KEY] == [A_SCOPE]

    def test_unknown_when_never_recorded(self, token_store):
        assert auth._stored_granted_scopes() is None

    def test_restore_attaches_stored_set(self, token_store):
        auth._save_credentials(_creds(granted=[A_SCOPE]))

        loaded = _creds(granted=None)
        auth._restore_granted_scopes(loaded)
        assert loaded._granted_scopes == [A_SCOPE]

    def test_restore_does_not_clobber_fresher_value(self, token_store):
        auth._save_credentials(_creds(granted=[A_SCOPE]))

        refreshed = _creds(granted=[A_SCOPE, B_SCOPE])
        auth._restore_granted_scopes(refreshed)
        assert refreshed.granted_scopes == [A_SCOPE, B_SCOPE]


class TestMissingScopes:
    def test_detects_drift(self, token_store):
        """The regression from issue #82: a partial grant must be reported."""
        partial = [s for s in SCOPES if s != B_SCOPE]
        creds = _creds(granted=partial)

        assert auth._missing_scopes(creds) == [B_SCOPE]

    def test_requested_set_is_ignored(self, token_store):
        """`scopes` claiming everything must not mask a narrower grant.

        This is the exact shape of the bug: desk passes SCOPES into
        `from_authorized_user_info`, so `creds.scopes` always looks complete.
        """
        creds = _creds(granted=[A_SCOPE], requested=list(SCOPES))

        missing = auth._missing_scopes(creds)
        assert missing == sorted(set(SCOPES) - {A_SCOPE})
        assert missing, "a one-scope grant cannot satisfy every desk scope"

    def test_full_grant_reports_nothing_missing(self, token_store):
        assert auth._missing_scopes(_creds(granted=list(SCOPES))) == []

    def test_unknown_grant_reports_none_not_empty(self, token_store):
        """None and [] mean different things — callers fail open only on None."""
        assert auth._missing_scopes(_creds(granted=None)) is None


class TestGrantedScopesAccessor:
    def test_prefers_credentials_over_storage(self, token_store):
        auth._save_credentials(_creds(granted=[A_SCOPE]))

        assert auth.granted_scopes(_creds(granted=[B_SCOPE])) == {B_SCOPE}

    def test_falls_back_to_storage(self, token_store):
        auth._save_credentials(_creds(granted=[A_SCOPE]))

        assert auth.granted_scopes() == {A_SCOPE}

    def test_none_when_unknown(self, token_store):
        assert auth.granted_scopes() is None
        assert auth.granted_scopes(_creds(granted=None)) is None


class TestScopeMap:
    def test_service_entry_covers_every_command(self):
        from desk.config import scopes_for_command, scopes_for_service

        assert scopes_for_service("slides") == [PRESENTATIONS]
        assert scopes_for_command("slides", "create") == [PRESENTATIONS]
        assert scopes_for_command("slides", "ungroup") == [PRESENTATIONS]

    def test_ungated_service_has_no_scopes(self):
        from desk.config import scopes_for_command, scopes_for_service

        assert scopes_for_service("mail") == []
        assert scopes_for_command("mail", "search") == []

    def test_affected_commands_reads_naturally(self):
        from desk.config import commands_for_scopes

        assert commands_for_scopes([PRESENTATIONS]) == ["slides (all commands)"]


class TestEnforceScopes:
    def test_blocks_when_scope_missing(self, token_store):
        from desk.agent import enforce_scopes

        auth._save_credentials(_creds(granted=[A_SCOPE]))
        with pytest.raises(SystemExit) as exc:
            enforce_scopes([PRESENTATIONS], as_json=True)
        assert exc.value.code == 1

    def test_error_names_scope_and_fix(self, token_store, capsys):
        from desk.agent import enforce_scopes

        auth._save_credentials(_creds(granted=[A_SCOPE]))
        with pytest.raises(SystemExit):
            enforce_scopes([PRESENTATIONS], as_json=True)

        payload = json.loads(capsys.readouterr().err)
        assert payload["error"]["code"] == "INSUFFICIENT_SCOPES"
        assert payload["error"]["details"]["scope_needed"] == [PRESENTATIONS]
        assert payload["error"]["details"]["affected_commands"] == ["slides (all commands)"]
        assert any("desk auth login" in s for s in payload["error"]["suggestions"])

    def test_allows_when_scope_granted(self, token_store):
        from desk.agent import enforce_scopes

        auth._save_credentials(_creds(granted=[PRESENTATIONS]))
        enforce_scopes([PRESENTATIONS], as_json=True)  # must not raise

    def test_fails_open_when_grant_unknown(self, token_store):
        """A pre-#82 token must never be blocked on a guess."""
        from desk.agent import enforce_scopes

        assert auth.granted_scopes() is None
        enforce_scopes([PRESENTATIONS], as_json=True)  # must not raise

    def test_no_scopes_is_a_noop(self, token_store):
        from desk.agent import enforce_scopes

        auth._save_credentials(_creds(granted=[]))
        enforce_scopes([], as_json=True)  # must not raise


class TestCapabilitiesEnabled:
    def test_enabled_false_when_scope_missing(self, token_store):
        from desk.cli import _get_capabilities

        auth._save_credentials(_creds(granted=[s for s in SCOPES if s != PRESENTATIONS]))
        caps = _get_capabilities()

        assert caps["services"]["slides"]["commands"]["create"]["enabled"] is False
        assert caps["services"]["mail"]["commands"]["search"]["enabled"] is True

    def test_enabled_true_with_full_grant(self, token_store):
        from desk.cli import _get_capabilities

        auth._save_credentials(_creds(granted=list(SCOPES)))
        caps = _get_capabilities()

        assert caps["services"]["slides"]["commands"]["create"]["enabled"] is True

    def test_enabled_null_when_grant_unknown(self, token_store):
        """Tri-state: unknown is not the same as disabled."""
        from desk.cli import _get_capabilities

        caps = _get_capabilities()
        assert caps["services"]["slides"]["commands"]["create"]["enabled"] is None

    def test_scope_reported_per_command(self, token_store):
        from desk.cli import _get_capabilities

        caps = _get_capabilities()
        assert caps["services"]["slides"]["commands"]["create"]["scope"] == [PRESENTATIONS]
        assert caps["services"]["mail"]["commands"]["search"]["scope"] == []


class TestKeyringlessHost:
    """A host with no keyring backend must degrade, not crash.

    `--capabilities` is pure introspection, so it reads the granted set on every
    invocation. Without this, adding that read regressed startup on headless
    Linux, containers, and CI runners into a NoKeyringError traceback — the
    failure mode Cafe's ADR-024 was written to undo. See ADR-034.
    """

    @pytest.fixture
    def no_backend(self):
        import keyring.errors

        def boom(*args, **kwargs):
            raise keyring.errors.NoKeyringError("no backend")

        with patch("desk.keyring_store.keyring.get_password", side_effect=boom):
            yield

    def test_get_token_reports_absence(self, no_backend):
        from desk.keyring_store import get_token

        assert get_token() is None

    def test_get_client_credentials_reports_absence(self, no_backend):
        from desk.keyring_store import get_client_credentials

        assert get_client_credentials() is None

    def test_granted_scopes_unknown(self, no_backend, tmp_path):
        with patch("desk.auth.TOKEN_FILE", tmp_path / "absent.json"):
            assert auth.granted_scopes() is None

    def test_capabilities_still_renders(self, no_backend, tmp_path):
        from desk.cli import _get_capabilities

        with patch("desk.auth.TOKEN_FILE", tmp_path / "absent.json"):
            caps = _get_capabilities()

        assert caps["services"]["slides"]["commands"]["create"]["enabled"] is None

    def test_scope_gate_fails_open(self, no_backend, tmp_path):
        from desk.agent import enforce_scopes

        with patch("desk.auth.TOKEN_FILE", tmp_path / "absent.json"):
            enforce_scopes([PRESENTATIONS], as_json=True)  # must not raise

    def test_writes_still_fail_loudly(self, no_backend):
        """Storing a secret with nowhere to put it must never be silent."""
        import keyring.errors

        from desk.keyring_store import set_token

        with patch(
            "desk.keyring_store.keyring.set_password",
            side_effect=keyring.errors.NoKeyringError("no backend"),
        ):
            with pytest.raises(keyring.errors.NoKeyringError):
                set_token({"token": "x"})
