"""Google Groups / distribution list API wrapper (Admin SDK Directory)."""

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# Directory members.list / groups.list cap page size at 200.
_MAX_RESULTS = 200


class GroupsClient:
    """Client for Admin SDK Directory group + membership operations.

    Read-only: lists distribution-list (Google Group) membership and
    searches groups. Requires the directory.group / directory.group.member
    read-only scopes and a domain that permits the caller to read group
    data (frequently admin-gated — see the 403 handling in commands/groups).
    """

    def __init__(self, credentials: Credentials):
        self.service = build("admin", "directory_v1", credentials=credentials)

    def list_members(
        self,
        group_key: str,
        roles: str | None = None,
        page_token: str | None = None,
    ) -> dict:
        """List members of a group.

        Args:
            group_key: Group email address or unique ID.
            roles: Optional comma-separated role filter (OWNER, MANAGER, MEMBER).
            page_token: Token for fetching the next page of results.

        Returns:
            Dict with 'members' list and 'nextPageToken' (if more results exist).
        """
        request_kwargs: dict = {"groupKey": group_key, "maxResults": _MAX_RESULTS}
        if roles:
            request_kwargs["roles"] = roles
        if page_token:
            request_kwargs["pageToken"] = page_token

        results = self.service.members().list(**request_kwargs).execute()

        result = {"members": [self._parse_member(m) for m in results.get("members", [])]}
        if results.get("nextPageToken"):
            result["nextPageToken"] = results["nextPageToken"]
        return result

    def get_group(self, group_key: str) -> dict:
        """Get a single group's metadata.

        Args:
            group_key: Group email address or unique ID.

        Returns:
            Parsed group dict.
        """
        group = self.service.groups().get(groupKey=group_key).execute()
        return self._parse_group(group)

    def search_groups(
        self,
        query: str | None = None,
        domain: str | None = None,
        page_token: str | None = None,
    ) -> dict:
        """Search/list groups.

        Args:
            query: Optional Directory search query (e.g. ``name:orion*`` or
                ``email:orion*``). Omit to list all groups in scope.
            domain: Restrict to a specific domain. When omitted, searches the
                caller's customer (``my_customer``).
            page_token: Token for fetching the next page of results.

        Returns:
            Dict with 'groups' list and 'nextPageToken' (if more results exist).
        """
        request_kwargs: dict = {"maxResults": _MAX_RESULTS}
        if domain:
            request_kwargs["domain"] = domain
        else:
            request_kwargs["customer"] = "my_customer"
        if query:
            request_kwargs["query"] = query
        if page_token:
            request_kwargs["pageToken"] = page_token

        results = self.service.groups().list(**request_kwargs).execute()

        result = {"groups": [self._parse_group(g) for g in results.get("groups", [])]}
        if results.get("nextPageToken"):
            result["nextPageToken"] = results["nextPageToken"]
        return result

    @staticmethod
    def _parse_member(member: dict) -> dict:
        """Flatten a Directory member resource to the fields we surface."""
        return {
            "email": member.get("email", ""),
            "role": member.get("role", ""),
            "type": member.get("type", ""),
            "status": member.get("status", ""),
            "id": member.get("id", ""),
        }

    @staticmethod
    def _parse_group(group: dict) -> dict:
        """Flatten a Directory group resource to the fields we surface."""
        return {
            "email": group.get("email", ""),
            "name": group.get("name", ""),
            "description": group.get("description", ""),
            "directMembersCount": group.get("directMembersCount", ""),
            "aliases": group.get("aliases", []),
            "id": group.get("id", ""),
        }
