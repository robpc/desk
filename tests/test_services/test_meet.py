"""Tests for the Meet service wrapper (ADR-036, issue #81)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from desk.services.meet import MeetClient, space_resource_name


@pytest.fixture
def client():
    with patch("desk.services.meet.build") as build:
        service = MagicMock()
        build.return_value = service
        c = MeetClient(MagicMock())
        c._service_mock = service
        yield c


def _patch_call(client):
    return client._service_mock.spaces.return_value.patch.call_args


def _set_patch_result(client, result=None):
    client._service_mock.spaces.return_value.patch.return_value.execute.return_value = (
        result or {"name": "spaces/x", "meetingCode": "abc-defg-hij"}
    )


class TestSpaceResourceName:
    """A Calendar event's conferenceId must work as-is."""

    def test_bare_meeting_code(self):
        assert space_resource_name("abc-defg-hij") == "spaces/abc-defg-hij"

    def test_already_qualified(self):
        assert space_resource_name("spaces/jQCFfuBOdN5z") == "spaces/jQCFfuBOdN5z"

    def test_strips_whitespace(self):
        assert space_resource_name("  abc-defg-hij \n") == "spaces/abc-defg-hij"


class TestConfigureArtifacts:
    def test_sets_recording_with_correct_enum(self, client):
        _set_patch_result(client)
        client.configure_artifacts("abc-defg-hij", auto_record="on")

        body = _patch_call(client).kwargs["body"]
        recording = body["config"]["artifactConfig"]["recordingConfig"]
        assert recording["autoRecordingGeneration"] == "ON"

    def test_off_and_default_enums(self, client):
        _set_patch_result(client)
        client.configure_artifacts("abc", auto_record="off")
        assert (
            _patch_call(client).kwargs["body"]["config"]["artifactConfig"][
                "recordingConfig"
            ]["autoRecordingGeneration"]
            == "OFF"
        )

        client.configure_artifacts("abc", auto_record="default")
        assert (
            _patch_call(client).kwargs["body"]["config"]["artifactConfig"][
                "recordingConfig"
            ]["autoRecordingGeneration"]
            == "AUTO_GENERATION_TYPE_UNSPECIFIED"
        )

    def test_update_mask_names_only_requested_fields(self, client):
        """An unmentioned setting must not be reset."""
        _set_patch_result(client)
        client.configure_artifacts("abc", auto_record="on")

        mask = _patch_call(client).kwargs["updateMask"]
        assert mask == "config.artifactConfig.recordingConfig.autoRecordingGeneration"

    def test_multiple_settings_build_a_combined_mask(self, client):
        _set_patch_result(client)
        client.configure_artifacts("abc", auto_record="on", auto_transcript="on")

        mask = _patch_call(client).kwargs["updateMask"].split(",")
        assert "config.artifactConfig.recordingConfig.autoRecordingGeneration" in mask
        assert (
            "config.artifactConfig.transcriptionConfig.autoTranscriptionGeneration"
            in mask
        )
        assert len(mask) == 2

    def test_smart_notes_path(self, client):
        _set_patch_result(client)
        client.configure_artifacts("abc", auto_smart_notes="on")

        assert (
            _patch_call(client).kwargs["updateMask"]
            == "config.artifactConfig.smartNotesConfig.autoSmartNotesGeneration"
        )

    def test_resolves_space_name(self, client):
        _set_patch_result(client)
        client.configure_artifacts("abc-defg-hij", auto_record="on")

        assert _patch_call(client).kwargs["name"] == "spaces/abc-defg-hij"

    def test_rejects_empty_update(self, client):
        with pytest.raises(ValueError, match="Nothing to update"):
            client.configure_artifacts("abc")

    def test_rejects_invalid_value(self, client):
        with pytest.raises(ValueError, match="Invalid value"):
            client.configure_artifacts("abc", auto_record="yes")

    def test_no_api_call_on_empty_update(self, client):
        with pytest.raises(ValueError):
            client.configure_artifacts("abc")

        client._service_mock.spaces.return_value.patch.assert_not_called()


class TestParseSpace:
    def test_surfaces_artifact_settings(self, client):
        client._service_mock.spaces.return_value.get.return_value.execute.return_value = {
            "name": "spaces/jQCFfuBOdN5z",
            "meetingCode": "abc-defg-hij",
            "meetingUri": "https://meet.google.com/abc-defg-hij",
            "config": {
                "accessType": "TRUSTED",
                "moderation": "ON",
                "artifactConfig": {
                    "recordingConfig": {"autoRecordingGeneration": "ON"},
                    "transcriptionConfig": {"autoTranscriptionGeneration": "OFF"},
                },
            },
        }

        space = client.get_space("abc-defg-hij")
        assert space["meetingCode"] == "abc-defg-hij"
        assert space["autoRecord"] == "ON"
        assert space["autoTranscript"] == "OFF"
        assert space["autoSmartNotes"] == ""  # absent, not assumed off
        assert space["moderation"] == "ON"

    def test_tolerates_missing_config(self, client):
        client._service_mock.spaces.return_value.get.return_value.execute.return_value = {
            "name": "spaces/x"
        }

        space = client.get_space("x")
        assert space["autoRecord"] == ""
        assert space["accessType"] == ""

    def test_tolerates_null_config(self, client):
        client._service_mock.spaces.return_value.get.return_value.execute.return_value = {
            "name": "spaces/x",
            "config": None,
        }

        assert client.get_space("x")["autoRecord"] == ""
