"""Tests for groups CLI commands."""

import json

import pytest
from click.testing import CliRunner
from unittest.mock import MagicMock, patch


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def mock_get_credentials():
    with patch("desk.commands.groups.get_credentials") as mock:
        mock.return_value = MagicMock()
        yield mock


@pytest.fixture
def mock_groups_client_class():
    with patch("desk.commands.groups.GroupsClient") as mock:
        yield mock


class TestGroupsMembers:
    """Tests for desk groups members."""

    def test_members_json_output(
        self, runner, mock_get_credentials, mock_groups_client_class
    ):
        from desk.commands.groups import groups

        mock_client = MagicMock()
        mock_client.list_members.return_value = {
            "members": [
                {"email": "a@x.com", "role": "OWNER", "type": "USER", "status": "ACTIVE"}
            ]
        }
        mock_groups_client_class.return_value = mock_client

        result = runner.invoke(groups, ["members", "team@x.com", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["members"][0]["email"] == "a@x.com"
        mock_client.list_members.assert_called_once()

    def test_members_table_output(
        self, runner, mock_get_credentials, mock_groups_client_class
    ):
        from desk.commands.groups import groups

        mock_client = MagicMock()
        mock_client.list_members.return_value = {
            "members": [
                {"email": "a@x.com", "role": "MEMBER", "type": "USER", "status": "ACTIVE"}
            ]
        }
        mock_groups_client_class.return_value = mock_client

        result = runner.invoke(groups, ["members", "team@x.com"])

        assert result.exit_code == 0
        assert "a@x.com" in result.output

    def test_members_403_maps_to_permission_denied(
        self, runner, mock_get_credentials, mock_groups_client_class
    ):
        from desk.commands.groups import groups

        mock_client = MagicMock()
        mock_client.list_members.side_effect = Exception("403 insufficient permission")
        mock_groups_client_class.return_value = mock_client

        result = runner.invoke(groups, ["members", "team@x.com", "--json"])

        assert result.exit_code == 1
        err = json.loads(result.stderr)
        assert err["error"]["code"] == "PERMISSION_DENIED"


class TestGroupsFind:
    """Tests for desk groups find."""

    def test_find_lists_groups(
        self, runner, mock_get_credentials, mock_groups_client_class
    ):
        from desk.commands.groups import groups

        mock_client = MagicMock()
        mock_client.search_groups.return_value = {
            "groups": [{"email": "g@x.com", "name": "G", "directMembersCount": "2"}]
        }
        mock_groups_client_class.return_value = mock_client

        result = runner.invoke(groups, ["find", "email:g*", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["groups"][0]["email"] == "g@x.com"


class TestGroupsGet:
    """Tests for desk groups get."""

    def test_get_group_404_maps_to_group_not_found(
        self, runner, mock_get_credentials, mock_groups_client_class
    ):
        from desk.commands.groups import groups

        mock_client = MagicMock()
        mock_client.get_group.side_effect = Exception("404 not found")
        mock_groups_client_class.return_value = mock_client

        result = runner.invoke(groups, ["get", "nope@x.com", "--json"])

        assert result.exit_code == 1
        err = json.loads(result.stderr)
        assert err["error"]["code"] == "GROUP_NOT_FOUND"
