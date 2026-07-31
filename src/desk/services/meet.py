"""Google Meet API wrapper.

Covers meeting-space artifact settings — auto-recording, auto-transcription, and
auto smart notes. See ADR-036.

Co-host membership (`spaces.members.create` with `role: COHOST`) is deliberately
absent: it's gated behind Google's Developer Preview Program, so shipping it
would fail for anyone not enrolled.
"""

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# CLI values for the API's AutoGenerationType. `default` defers to the user's
# Workspace policy rather than forcing the setting either way. See ADR-036.
AUTO_GENERATION_CHOICES = ("on", "off", "default")
_AUTO_GENERATION_API = {
    "on": "ON",
    "off": "OFF",
    "default": "AUTO_GENERATION_TYPE_UNSPECIFIED",
}

# Each artifact setting: CLI name -> (config block, field, updateMask path)
_ARTIFACT_FIELDS = {
    "auto_record": (
        "recordingConfig",
        "autoRecordingGeneration",
        "config.artifactConfig.recordingConfig.autoRecordingGeneration",
    ),
    "auto_transcript": (
        "transcriptionConfig",
        "autoTranscriptionGeneration",
        "config.artifactConfig.transcriptionConfig.autoTranscriptionGeneration",
    ),
    "auto_smart_notes": (
        "smartNotesConfig",
        "autoSmartNotesGeneration",
        "config.artifactConfig.smartNotesConfig.autoSmartNotesGeneration",
    ),
}


def space_resource_name(space: str) -> str:
    """Normalize a space ID or meeting code into a `spaces/…` resource name.

    Both `spaces.get` and `spaces.patch` accept `spaces/{space}` (a
    server-assigned ID) or `spaces/{meetingCode}` (the typeable
    `abc-mnop-xyz` form), so callers can pass a Calendar event's
    `conferenceId` straight through. See ADR-036.
    """
    space = space.strip()
    if space.startswith("spaces/"):
        return space
    return f"spaces/{space}"


class MeetClient:
    """Client for Google Meet API operations."""

    def __init__(self, credentials: Credentials):
        self.service = build("meet", "v2", credentials=credentials)

    def get_space(self, space: str) -> dict:
        """Read a meeting space's configuration.

        Args:
            space: Space ID, meeting code, or full `spaces/…` resource name

        Returns:
            Parsed space dict
        """
        try:
            result = (
                self.service.spaces()
                .get(name=space_resource_name(space))
                .execute()
            )
            return self._parse_space(result)
        except HttpError as error:
            raise RuntimeError(f"Meet API error: {error}")

    def configure_artifacts(
        self,
        space: str,
        auto_record: str | None = None,
        auto_transcript: str | None = None,
        auto_smart_notes: str | None = None,
    ) -> dict:
        """Set a space's auto-artifact generation settings.

        Only the settings passed are sent, so an unmentioned setting is left
        alone rather than reset.

        Args:
            space: Space ID, meeting code, or full `spaces/…` resource name
            auto_record: "on", "off", or "default"
            auto_transcript: "on", "off", or "default"
            auto_smart_notes: "on", "off", or "default"

        Returns:
            Parsed space dict reflecting the update

        Raises:
            ValueError: If no setting was requested, or a value is invalid.
        """
        requested = {
            "auto_record": auto_record,
            "auto_transcript": auto_transcript,
            "auto_smart_notes": auto_smart_notes,
        }
        requested = {k: v for k, v in requested.items() if v is not None}
        if not requested:
            raise ValueError(
                "Nothing to update. Pass at least one of --auto-record, "
                "--auto-transcript, or --auto-smart-notes."
            )

        artifact_config: dict = {}
        update_mask: list[str] = []
        for name, value in requested.items():
            if value not in _AUTO_GENERATION_API:
                raise ValueError(
                    f"Invalid value '{value}' for {name}. "
                    f"Must be one of: {', '.join(AUTO_GENERATION_CHOICES)}"
                )
            block, field, mask_path = _ARTIFACT_FIELDS[name]
            artifact_config[block] = {field: _AUTO_GENERATION_API[value]}
            update_mask.append(mask_path)

        body = {"config": {"artifactConfig": artifact_config}}

        try:
            result = (
                self.service.spaces()
                .patch(
                    name=space_resource_name(space),
                    body=body,
                    updateMask=",".join(update_mask),
                )
                .execute()
            )
            return self._parse_space(result)
        except HttpError as error:
            raise RuntimeError(f"Meet API error: {error}")

    def _parse_space(self, space: dict) -> dict:
        """Parse a Meet API space resource into a clean dict."""
        config = space.get("config") or {}
        artifacts = config.get("artifactConfig") or {}

        def _setting(block: str, field: str) -> str:
            return (artifacts.get(block) or {}).get(field, "")

        return {
            "name": space.get("name", ""),
            "meetingCode": space.get("meetingCode", ""),
            "meetingUri": space.get("meetingUri", ""),
            "accessType": config.get("accessType", ""),
            "entryPointAccess": config.get("entryPointAccess", ""),
            "moderation": config.get("moderation", ""),
            "autoRecord": _setting("recordingConfig", "autoRecordingGeneration"),
            "autoTranscript": _setting(
                "transcriptionConfig", "autoTranscriptionGeneration"
            ),
            "autoSmartNotes": _setting("smartNotesConfig", "autoSmartNotesGeneration"),
        }
