"""Tests for `desk auth logout`, `desk auth clear`, the client_id diagnostics on
`auth status`, and stale-token detection on `desk auth set-client` (ADR-040).
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from desk.keyring_store import KEYRING_SERVICE


@pytest.fixture
def fake_keyring():
    """In-memory keyring substitute. Mirrors the fixture in test_keyring.py."""
    store: dict[tuple[str, str], str] = {}

    def get_password(service: str, key: str) -> str | None:
        return store.get((service, key))

    def set_password(service: str, key: str, value: str) -> None:
        store[(service, key)] = value

    def delete_password(service: str, key: str) -> None:
        if (service, key) not in store:
            import keyring.errors

            raise keyring.errors.PasswordDeleteError()
        del store[(service, key)]

    with (
        patch("desk.keyring_store.keyring.get_password", side_effect=get_password),
        patch("desk.keyring_store.keyring.set_password", side_effect=set_password),
        patch("desk.keyring_store.keyring.delete_password", side_effect=delete_password),
    ):
        yield store


@pytest.fixture
def isolated_token_file(tmp_path):
    """Redirect TOKEN_FILE and CREDENTIALS_FILE into a tmpdir."""
    token_path = tmp_path / "token.json"
    creds_path = tmp_path / "credentials.json"
    with (
        patch("desk.auth.TOKEN_FILE", token_path),
        patch("desk.auth.CREDENTIALS_FILE", creds_path),
    ):
        yield {"token": token_path, "credentials": creds_path}


@pytest.fixture
def no_live_auth():
    """Keep get_auth_status() off the network and away from real gcloud ADC."""
    with (
        patch("desk.auth._get_oauth_credentials", return_value=None),
        patch("desk.auth._get_adc_credentials", return_value=None),
        patch("desk.auth._gcloud_available", return_value=False),
    ):
        yield


def _seed_token(store: dict, token: dict) -> None:
    store[(KEYRING_SERVICE, "oauth:token")] = json.dumps(token)


def _seed_client(store: dict, client_id: str = "configured.apps.googleusercontent.com") -> None:
    store[(KEYRING_SERVICE, "client:credentials")] = json.dumps(
        {
            "installed": {
                "client_id": client_id,
                "client_secret": "GOCSPX-secret",
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        }
    )


class TestKeyringDeleteClient:
    def test_delete_client_credentials_when_present(self, fake_keyring):
        from desk.keyring_store import delete_client_credentials

        _seed_client(fake_keyring)
        assert delete_client_credentials() is True
        assert (KEYRING_SERVICE, "client:credentials") not in fake_keyring

    def test_delete_client_credentials_idempotent(self, fake_keyring):
        from desk.keyring_store import delete_client_credentials

        assert delete_client_credentials() is False


class TestLogoutCommand:
    def test_logout_removes_keyring_token(self, fake_keyring, isolated_token_file):
        _seed_token(fake_keyring, {"token": "ya29.abc", "refresh_token": "1//xyz"})

        from desk.cli import main

        result = CliRunner().invoke(main, ["auth", "logout"])
        assert result.exit_code == 0, result.output
        assert "Removed OAuth token" in result.output
        assert (KEYRING_SERVICE, "oauth:token") not in fake_keyring

    def test_logout_idempotent(self, fake_keyring, isolated_token_file):
        from desk.cli import main

        result = CliRunner().invoke(main, ["auth", "logout"])
        assert result.exit_code == 0
        assert "No stored OAuth token" in result.output

    def test_logout_preserves_client_credentials(self, fake_keyring, isolated_token_file):
        _seed_client(fake_keyring)
        _seed_token(fake_keyring, {"token": "ya29.abc"})

        from desk.cli import main

        result = CliRunner().invoke(main, ["auth", "logout"])
        assert result.exit_code == 0
        assert (KEYRING_SERVICE, "client:credentials") in fake_keyring

    def test_logout_scrubs_legacy_token_file(self, fake_keyring, isolated_token_file):
        token_path = isolated_token_file["token"]
        token_path.write_text(
            json.dumps(
                {
                    "token": "ya29.legacy",
                    "refresh_token": "1//legacy",
                    "client_id": "id.apps.googleusercontent.com",
                    "client_secret": "GOCSPX-legacy",
                    "scopes": ["scope-a"],
                    "granted_scopes": ["scope-a"],
                }
            )
        )

        from desk.cli import main

        result = CliRunner().invoke(main, ["auth", "logout"])
        assert result.exit_code == 0
        assert "Scrubbed legacy token file" in result.output

        remaining = json.loads(token_path.read_text())
        assert "token" not in remaining
        assert "refresh_token" not in remaining
        assert "client_secret" not in remaining
        # Non-secret metadata is preserved — including the ADR-037 granted set.
        assert remaining["scopes"] == ["scope-a"]
        assert remaining["granted_scopes"] == ["scope-a"]

    def test_logout_json_output(self, fake_keyring, isolated_token_file):
        _seed_token(fake_keyring, {"token": "ya29.abc"})

        from desk.cli import main

        result = CliRunner().invoke(main, ["auth", "logout", "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["keyring_token_removed"] is True
        assert payload["token_file_scrubbed"] is False


class TestClearCommand:
    def test_clear_default_removes_both(self, fake_keyring, isolated_token_file):
        _seed_token(fake_keyring, {"token": "ya29.abc"})
        _seed_client(fake_keyring)

        from desk.cli import main

        result = CliRunner().invoke(main, ["auth", "clear", "--yes"])
        assert result.exit_code == 0, result.output
        assert (KEYRING_SERVICE, "oauth:token") not in fake_keyring
        assert (KEYRING_SERVICE, "client:credentials") not in fake_keyring

    def test_clear_token_only(self, fake_keyring, isolated_token_file):
        _seed_token(fake_keyring, {"token": "ya29.abc"})
        _seed_client(fake_keyring)

        from desk.cli import main

        result = CliRunner().invoke(main, ["auth", "clear", "--token", "--yes"])
        assert result.exit_code == 0, result.output
        assert (KEYRING_SERVICE, "oauth:token") not in fake_keyring
        assert (KEYRING_SERVICE, "client:credentials") in fake_keyring

    def test_clear_client_only(self, fake_keyring, isolated_token_file):
        _seed_token(fake_keyring, {"token": "ya29.abc"})
        _seed_client(fake_keyring)

        from desk.cli import main

        result = CliRunner().invoke(main, ["auth", "clear", "--client", "--yes"])
        assert result.exit_code == 0, result.output
        assert (KEYRING_SERVICE, "oauth:token") in fake_keyring
        assert (KEYRING_SERVICE, "client:credentials") not in fake_keyring

    def test_clear_both_flags_same_as_default(self, fake_keyring, isolated_token_file):
        _seed_token(fake_keyring, {"token": "ya29.abc"})
        _seed_client(fake_keyring)

        from desk.cli import main

        result = CliRunner().invoke(main, ["auth", "clear", "--token", "--client", "--yes"])
        assert result.exit_code == 0, result.output
        assert (KEYRING_SERVICE, "oauth:token") not in fake_keyring
        assert (KEYRING_SERVICE, "client:credentials") not in fake_keyring

    def test_clear_non_interactive_requires_yes(self, fake_keyring, isolated_token_file):
        _seed_token(fake_keyring, {"token": "ya29.abc"})

        from desk.cli import main

        # CliRunner provides no TTY by default, simulating CI/scripts.
        result = CliRunner().invoke(main, ["auth", "clear"])
        assert result.exit_code != 0
        assert "Non-interactive mode requires --yes flag" in result.output
        # Token must be untouched
        assert (KEYRING_SERVICE, "oauth:token") in fake_keyring

    def test_clear_non_interactive_json(self, fake_keyring, isolated_token_file):
        from desk.cli import main

        result = CliRunner().invoke(main, ["auth", "clear", "--json"])
        assert result.exit_code != 0
        payload = json.loads(result.output)
        assert "Non-interactive" in payload["error"]

    def test_clear_idempotent(self, fake_keyring, isolated_token_file):
        from desk.cli import main

        result = CliRunner().invoke(main, ["auth", "clear", "--yes"])
        assert result.exit_code == 0
        assert "Nothing to remove" in result.output

    def test_clear_json_output(self, fake_keyring, isolated_token_file):
        _seed_token(fake_keyring, {"token": "ya29.abc"})
        _seed_client(fake_keyring)

        from desk.cli import main

        result = CliRunner().invoke(main, ["auth", "clear", "--yes", "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["keyring_token_removed"] is True
        assert payload["keyring_client_removed"] is True


class TestStatusFields:
    def test_status_surfaces_client_ids_and_source(
        self, fake_keyring, isolated_token_file, no_live_auth
    ):
        _seed_client(fake_keyring, "configured.apps.googleusercontent.com")
        _seed_token(
            fake_keyring,
            {
                "token": "ya29.abc",
                "refresh_token": "1//xyz",
                "client_id": "configured.apps.googleusercontent.com",
                "client_secret": "GOCSPX-x",
                "token_uri": "https://oauth2.googleapis.com/token",
                "scopes": ["https://www.googleapis.com/auth/gmail.modify"],
            },
        )

        from desk.auth import get_auth_status

        info = get_auth_status()
        assert info["client_id"] == "configured.apps.googleusercontent.com"
        assert info["token_client_id"] == "configured.apps.googleusercontent.com"
        assert info["token_source"] == "keyring"
        # The stored *requested* scope list is deliberately not surfaced:
        # ADR-037's missing_scopes is the actionable signal.
        assert "scopes" not in info
        assert "missing_scopes" in info

    def test_status_flags_client_id_mismatch(
        self, fake_keyring, isolated_token_file, no_live_auth
    ):
        _seed_client(fake_keyring, "new.apps.googleusercontent.com")
        _seed_token(
            fake_keyring,
            {"token": "ya29.abc", "client_id": "old.apps.googleusercontent.com"},
        )

        from desk.auth import get_auth_status

        info = get_auth_status()
        assert info["client_id"] == "new.apps.googleusercontent.com"
        assert info["token_client_id"] == "old.apps.googleusercontent.com"

    def test_status_client_id_falls_back_to_credentials_file(
        self, fake_keyring, isolated_token_file, no_live_auth
    ):
        isolated_token_file["credentials"].write_text(
            json.dumps({"installed": {"client_id": "file.apps.googleusercontent.com"}})
        )

        from desk.auth import get_auth_status

        info = get_auth_status()
        assert info["client_id"] == "file.apps.googleusercontent.com"

    def test_status_no_token_no_client(self, fake_keyring, isolated_token_file, no_live_auth):
        from desk.auth import get_auth_status

        info = get_auth_status()
        assert info["client_id"] is None
        assert info["token_client_id"] is None
        assert info["token_source"] == "none"

    def test_status_token_source_file(self, fake_keyring, isolated_token_file, no_live_auth):
        isolated_token_file["token"].write_text(
            json.dumps({"refresh_token": "1//legacy", "client_id": "legacy.apps"})
        )

        from desk.auth import get_auth_status

        info = get_auth_status()
        assert info["token_source"] == "file"
        assert info["token_client_id"] == "legacy.apps"
        assert info["token_in_keyring"] is False

    def test_status_scrubbed_token_file_is_not_a_source(
        self, fake_keyring, isolated_token_file, no_live_auth
    ):
        # After logout, the file holds only metadata — it must not count as a token.
        isolated_token_file["token"].write_text(json.dumps({"scopes": ["a"], "client_id": "x"}))

        from desk.auth import get_auth_status

        info = get_auth_status()
        assert info["token_source"] == "none"
        assert info["token_client_id"] is None


class TestStatusCommandOutput:
    # Opaque client ids on purpose: a hostname-shaped literal in an `in` assertion
    # trips CodeQL's incomplete-url-substring-sanitization rule.
    def _status(self, **fields):
        base = {
            "method": "oauth_client",
            "authenticated": True,
            "gcloud_available": False,
            "credentials_file": False,
            "credentials_in_keyring": True,
            "credentials_path": "/x/credentials.json",
            "token_file": False,
            "token_in_keyring": True,
            "token_path": "/x/token.json",
            "client_id": "configured-client",
            "token_client_id": "configured-client",
            "token_source": "keyring",
            "email": None,
            "services": None,
            "missing_scopes": [],
        }
        base.update(fields)
        return base

    def test_mismatch_is_called_out_with_the_fix(self):
        from desk.cli import main

        with patch(
            "desk.cli.get_auth_status",
            return_value=self._status(token_client_id="stale-client"),
        ):
            result = CliRunner().invoke(main, ["auth", "status"])

        assert result.exit_code == 0, result.output
        assert "stale-client" in result.output
        assert "does not match" in result.output
        assert "desk auth logout" in result.output

    def test_matching_client_prints_no_warning(self):
        from desk.cli import main

        with patch("desk.cli.get_auth_status", return_value=self._status()):
            result = CliRunner().invoke(main, ["auth", "status"])

        assert result.exit_code == 0, result.output
        assert "client_id: configured-client" in result.output
        assert "token source: keyring" in result.output
        assert "does not match" not in result.output

    def test_json_carries_the_diagnostic_fields(self):
        from desk.cli import main

        with patch(
            "desk.cli.get_auth_status",
            return_value=self._status(token_client_id="stale-client"),
        ):
            result = CliRunner().invoke(main, ["auth", "status", "--json"])

        payload = json.loads(result.output)
        assert payload["client_id"] == "configured-client"
        assert payload["token_client_id"] == "stale-client"
        assert payload["token_source"] == "keyring"
        assert "scopes" not in payload


class TestSetClientStaleToken:
    def test_set_client_invalidates_stale_token(self, fake_keyring):
        _seed_token(
            fake_keyring,
            {
                "token": "ya29.abc",
                "refresh_token": "1//xyz",
                "client_id": "old.apps.googleusercontent.com",
            },
        )

        from desk.cli import main

        result = CliRunner().invoke(
            main,
            [
                "auth",
                "set-client",
                "--client-id",
                "new.apps.googleusercontent.com",
                "--client-secret",
                "GOCSPX-new",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "Cleared stored token" in result.output
        assert (KEYRING_SERVICE, "oauth:token") not in fake_keyring

    def test_set_client_keeps_matching_token(self, fake_keyring):
        _seed_token(
            fake_keyring,
            {"token": "ya29.abc", "client_id": "same.apps.googleusercontent.com"},
        )

        from desk.cli import main

        result = CliRunner().invoke(
            main,
            [
                "auth",
                "set-client",
                "--client-id",
                "same.apps.googleusercontent.com",
                "--client-secret",
                "GOCSPX-x",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "Cleared stored token" not in result.output
        assert (KEYRING_SERVICE, "oauth:token") in fake_keyring

    def test_set_client_no_existing_token_no_note(self, fake_keyring):
        from desk.cli import main

        result = CliRunner().invoke(
            main,
            [
                "auth",
                "set-client",
                "--client-id",
                "fresh.apps.googleusercontent.com",
                "--client-secret",
                "GOCSPX-x",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "Cleared stored token" not in result.output
