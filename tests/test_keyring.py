"""Tests for keyring-based credential storage."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from desk.keyring_store import KEYRING_SERVICE


@pytest.fixture
def fake_keyring():
    """In-memory keyring substitute for testing."""
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


class TestClientCredentials:
    def test_get_empty(self, fake_keyring):
        from desk.keyring_store import get_client_credentials

        assert get_client_credentials() is None

    def test_round_trip(self, fake_keyring):
        from desk.keyring_store import get_client_credentials, set_client_credentials

        creds = {"installed": {"client_id": "my-id", "client_secret": "my-secret"}}
        set_client_credentials(creds)
        result = get_client_credentials()
        assert result is not None
        assert result["installed"]["client_id"] == "my-id"

    def test_overwrite(self, fake_keyring):
        from desk.keyring_store import get_client_credentials, set_client_credentials

        set_client_credentials({"installed": {"client_id": "old"}})
        set_client_credentials({"installed": {"client_id": "new"}})
        assert get_client_credentials()["installed"]["client_id"] == "new"


class TestTokenStorage:
    def test_get_empty(self, fake_keyring):
        from desk.keyring_store import get_token

        assert get_token() is None

    def test_round_trip(self, fake_keyring):
        from desk.keyring_store import get_token, set_token

        token = {
            "token": "ya29.abc",
            "refresh_token": "1//xyz",
            "client_id": "my-id.apps.googleusercontent.com",
            "client_secret": "GOCSPX-secret",
        }
        set_token(token)
        loaded = get_token()
        assert loaded is not None
        assert loaded["token"] == "ya29.abc"
        assert loaded["refresh_token"] == "1//xyz"

    def test_delete(self, fake_keyring):
        from desk.keyring_store import delete_token, get_token, set_token

        set_token({"token": "ya29.abc"})
        assert delete_token() is True
        assert get_token() is None

    def test_delete_nonexistent(self, fake_keyring):
        from desk.keyring_store import delete_token

        assert delete_token() is False


class TestClearAll:
    def test_clear_existing(self, fake_keyring):
        from desk.keyring_store import clear_all, get_client_credentials, get_token

        fake_keyring[(KEYRING_SERVICE, "client:credentials")] = '{"installed":{}}'
        fake_keyring[(KEYRING_SERVICE, "oauth:token")] = '{"token":"x"}'
        assert clear_all() is True
        assert get_client_credentials() is None
        assert get_token() is None

    def test_clear_empty(self, fake_keyring):
        from desk.keyring_store import clear_all

        assert clear_all() is False


class TestMigration:
    def test_migrate_token(self, fake_keyring, tmp_path):
        """Token file is migrated to keyring; secrets scrubbed from file."""
        token_file = tmp_path / "token.json"
        token_data = {
            "token": "ya29.secret",
            "refresh_token": "1//secret",
            "client_id": "my-id.apps.googleusercontent.com",
            "client_secret": "GOCSPX-secret",
            "token_uri": "https://oauth2.googleapis.com/token",
            "scopes": ["https://www.googleapis.com/auth/gmail.modify"],
        }
        token_file.write_text(json.dumps(token_data))

        with (
            patch("desk.auth.TOKEN_FILE", token_file),
            patch("desk.auth.keyring_store.set_token") as mock_set,
        ):
            from desk.auth import _migrate_token_to_keyring

            _migrate_token_to_keyring()
            mock_set.assert_called_once_with(token_data)

        # File should be scrubbed of secrets
        remaining = json.loads(token_file.read_text())
        assert "token" not in remaining
        assert "refresh_token" not in remaining
        assert "client_secret" not in remaining
        assert remaining["client_id"] == "my-id.apps.googleusercontent.com"

    def test_migrate_credentials(self, fake_keyring, tmp_path):
        """Credentials file is migrated to keyring and deleted."""
        creds_file = tmp_path / "credentials.json"
        creds_data = {
            "installed": {
                "client_id": "123.apps.googleusercontent.com",
                "client_secret": "GOCSPX-secret",
            }
        }
        creds_file.write_text(json.dumps(creds_data))

        with (
            patch("desk.auth.CREDENTIALS_FILE", creds_file),
            patch("desk.auth.keyring_store.set_client_credentials") as mock_set,
        ):
            from desk.auth import _migrate_credentials_to_keyring

            _migrate_credentials_to_keyring()
            mock_set.assert_called_once_with(creds_data)

        assert not creds_file.exists()

    def test_no_migration_when_keyring_populated(self, fake_keyring, tmp_path):
        """If keyring has token, file is not used."""
        token_data = {
            "token": "ya29.from-keyring",
            "refresh_token": "1//from-keyring",
            "client_id": "id.apps.googleusercontent.com",
            "client_secret": "secret",
        }
        fake_keyring[(KEYRING_SERVICE, "oauth:token")] = json.dumps(token_data)

        # Mock Credentials.from_authorized_user_info to return a valid creds object
        mock_creds = MagicMock()
        mock_creds.valid = True

        with (
            patch("desk.auth.Credentials.from_authorized_user_info", return_value=mock_creds),
            patch("desk.auth._last_auth_failure", {"reason": None, "error_code": None}),
        ):
            from desk.auth import _get_oauth_credentials

            result = _get_oauth_credentials()
            assert result is mock_creds


class TestSetClientCommand:
    def test_stores_in_keyring(self, fake_keyring):
        from click.testing import CliRunner

        from desk.cli import main

        runner = CliRunner()
        result = runner.invoke(main, [
            "auth", "set-client",
            "--client-id", "test-id.apps.googleusercontent.com",
            "--client-secret", "GOCSPX-test",
            "--project-id", "my-project",
        ])
        assert result.exit_code == 0, result.output
        assert "stored in keychain" in result.output.lower()

        stored = json.loads(fake_keyring[(KEYRING_SERVICE, "client:credentials")])
        assert stored["installed"]["client_id"] == "test-id.apps.googleusercontent.com"
        assert stored["installed"]["client_secret"] == "GOCSPX-test"
        assert stored["installed"]["project_id"] == "my-project"
        assert stored["installed"]["auth_uri"] == "https://accounts.google.com/o/oauth2/auth"

    def test_without_project_id(self, fake_keyring):
        from click.testing import CliRunner

        from desk.cli import main

        runner = CliRunner()
        result = runner.invoke(main, [
            "auth", "set-client",
            "--client-id", "test-id.apps.googleusercontent.com",
            "--client-secret", "GOCSPX-test",
        ])
        assert result.exit_code == 0, result.output

        stored = json.loads(fake_keyring[(KEYRING_SERVICE, "client:credentials")])
        assert "project_id" not in stored["installed"]

    def test_no_backend_fails(self):
        from click.testing import CliRunner

        from desk.cli import main
        from desk.keyring_store import KeyringUnavailableError

        runner = CliRunner()
        with patch(
            "desk.keyring_store.check_keyring_backend",
            side_effect=KeyringUnavailableError("No usable keyring backend"),
        ):
            result = runner.invoke(main, [
                "auth", "set-client",
                "--client-id", "test-id",
                "--client-secret", "test-secret",
            ])
            assert result.exit_code != 0
            assert "no usable keyring backend" in result.output.lower()


class TestCredentialsFromKeyring:
    def test_from_authorized_user_info(self, fake_keyring):
        """Verify Credentials.from_authorized_user_info works with keyring data shape."""
        from google.oauth2.credentials import Credentials

        from desk.config import SCOPES

        token_data = {
            "token": "ya29.test-access-token",
            "refresh_token": "1//test-refresh-token",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "test.apps.googleusercontent.com",
            "client_secret": "GOCSPX-test",
            "scopes": SCOPES,
        }
        # This should not raise — validates the data shape is correct
        creds = Credentials.from_authorized_user_info(token_data, SCOPES)
        assert creds.token == "ya29.test-access-token"
        assert creds.refresh_token == "1//test-refresh-token"
        assert creds.client_id == "test.apps.googleusercontent.com"
