"""Tests for Groups service client."""

from unittest.mock import MagicMock, patch


class TestGroupsClientInit:
    """Tests for GroupsClient initialization."""

    def test_creates_service_with_credentials(self, mock_credentials):
        """Should create Admin Directory service with provided credentials."""
        with patch("desk.services.groups.build") as mock_build:
            mock_build.return_value = MagicMock()
            from desk.services.groups import GroupsClient

            GroupsClient(mock_credentials)

            mock_build.assert_called_once_with(
                "admin", "directory_v1", credentials=mock_credentials
            )


class TestListMembers:
    """Tests for GroupsClient.list_members."""

    def test_returns_parsed_members(self, mock_credentials):
        """Should flatten member resources to surfaced fields."""
        with patch("desk.services.groups.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service
            members_mock = mock_service.members.return_value
            members_mock.list.return_value.execute.return_value = {
                "members": [
                    {
                        "email": "a@example.com",
                        "role": "OWNER",
                        "type": "USER",
                        "status": "ACTIVE",
                        "id": "1",
                    }
                ]
            }

            from desk.services.groups import GroupsClient

            client = GroupsClient(mock_credentials)
            result = client.list_members("team@example.com")

            assert result["members"] == [
                {
                    "email": "a@example.com",
                    "role": "OWNER",
                    "type": "USER",
                    "status": "ACTIVE",
                    "id": "1",
                }
            ]
            assert "nextPageToken" not in result

    def test_passes_roles_and_page_token(self, mock_credentials):
        """Should forward role filter and page token to the API."""
        with patch("desk.services.groups.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service
            members_mock = mock_service.members.return_value
            members_mock.list.return_value.execute.return_value = {
                "members": [],
                "nextPageToken": "tok2",
            }

            from desk.services.groups import GroupsClient

            client = GroupsClient(mock_credentials)
            result = client.list_members(
                "team@example.com", roles="OWNER,MANAGER", page_token="tok1"
            )

            _, kwargs = members_mock.list.call_args
            assert kwargs["groupKey"] == "team@example.com"
            assert kwargs["roles"] == "OWNER,MANAGER"
            assert kwargs["pageToken"] == "tok1"
            assert result["nextPageToken"] == "tok2"


class TestSearchGroups:
    """Tests for GroupsClient.search_groups."""

    def test_defaults_to_my_customer(self, mock_credentials):
        """Without a domain, should query the caller's customer."""
        with patch("desk.services.groups.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service
            groups_mock = mock_service.groups.return_value
            groups_mock.list.return_value.execute.return_value = {"groups": []}

            from desk.services.groups import GroupsClient

            client = GroupsClient(mock_credentials)
            client.search_groups(query="email:orion*")

            _, kwargs = groups_mock.list.call_args
            assert kwargs["customer"] == "my_customer"
            assert "domain" not in kwargs
            assert kwargs["query"] == "email:orion*"

    def test_domain_overrides_customer(self, mock_credentials):
        """A domain should be sent instead of customer."""
        with patch("desk.services.groups.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service
            groups_mock = mock_service.groups.return_value
            groups_mock.list.return_value.execute.return_value = {
                "groups": [{"email": "g@x.com", "name": "G", "directMembersCount": "3"}]
            }

            from desk.services.groups import GroupsClient

            client = GroupsClient(mock_credentials)
            result = client.search_groups(domain="x.com")

            _, kwargs = groups_mock.list.call_args
            assert kwargs["domain"] == "x.com"
            assert "customer" not in kwargs
            assert result["groups"][0]["email"] == "g@x.com"


class TestGetGroup:
    """Tests for GroupsClient.get_group."""

    def test_returns_parsed_group(self, mock_credentials):
        """Should flatten a group resource."""
        with patch("desk.services.groups.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service
            groups_mock = mock_service.groups.return_value
            groups_mock.get.return_value.execute.return_value = {
                "email": "team@example.com",
                "name": "Team",
                "description": "desc",
                "directMembersCount": "5",
                "aliases": ["t@example.com"],
                "id": "abc",
            }

            from desk.services.groups import GroupsClient

            client = GroupsClient(mock_credentials)
            result = client.get_group("team@example.com")

            assert result["email"] == "team@example.com"
            assert result["aliases"] == ["t@example.com"]
            assert result["directMembersCount"] == "5"
