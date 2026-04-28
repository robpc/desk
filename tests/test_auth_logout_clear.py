"""Tests for `desk auth logout`, `desk auth clear`, enriched `auth status`,
and stale-token detection on `desk auth set-client`.
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
        # Non-secret metadata is preserved
        assert remaining["scopes"] == ["scope-a"]

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
    def test_status_surfaces_client_id_and_scopes(self, fake_keyring, isolated_token_file):
        _seed_client(fake_keyring, "configured.apps.googleusercontent.com")
        _seed_token(
            fake_keyring,
            {
                "token": "ya29.abc",
                "refresh_token": "1//xyz",
                "client_id": "configured.apps.googleusercontent.com",
                "client_secret": "GOCSPX-x",
                "token_uri": "https://oauth2.googleapis.com/token",
                "scopes": [
                    "https://www.googleapis.com/auth/gmail.modify",
                    "https://www.googleapis.com/auth/drive",
                ],
            },
        )

        from desk.auth import get_auth_status

        info = get_auth_status()
        assert info["client_id"] == "configured.apps.googleusercontent.com"
        assert info["token_client_id"] == "configured.apps.googleusercontent.com"
        assert info["token_source"] == "keyring"
        assert info["scopes"] == [
            "https://www.googleapis.com/auth/gmail.modify",
            "https://www.googleapis.com/auth/drive",
        ]

    def test_status_flags_client_id_mismatch(self, fake_keyring, isolated_token_file):
        _seed_client(fake_keyring, "new.apps.googleusercontent.com")
        _seed_token(
            fake_keyring,
            {
                "token": "ya29.abc",
                "client_id": "old.apps.googleusercontent.com",
                "scopes": ["scope-a"],
            },
        )

        from desk.auth import get_auth_status

        info = get_auth_status()
        assert info["client_id"] == "new.apps.googleusercontent.com"
        assert info["token_client_id"] == "old.apps.googleusercontent.com"

    def test_status_no_token_no_client(self, fake_keyring, isolated_token_file):
        from desk.auth import get_auth_status

        # Avoid finding bundled credentials or live gcloud ADC in the test env.
        with (
            patch("desk.auth.get_bundled_credentials", return_value=None),
            patch("desk.auth._get_adc_credentials", return_value=None),
        ):
            info = get_auth_status()
        assert info["client_id"] is None
        assert info["token_client_id"] is None
        assert info["token_source"] == "none"
        assert info["scopes"] == []

    def test_status_normalizes_string_scopes(self, fake_keyring, isolated_token_file):
        _seed_token(
            fake_keyring,
            {
                "token": "ya29.abc",
                "scopes": "scope-a scope-b scope-c",
            },
        )

        from desk.auth import get_auth_status

        info = get_auth_status()
        assert info["scopes"] == ["scope-a", "scope-b", "scope-c"]


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
            {
                "token": "ya29.abc",
                "client_id": "same.apps.googleusercontent.com",
            },
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
