"""Tests for Docs service client."""

from unittest.mock import MagicMock, patch

import pytest
from googleapiclient.errors import HttpError


class TestDocsClientInit:
    """Tests for DocsClient initialization."""

    def test_creates_only_docs_service_on_init(self, mock_credentials):
        """Should only create Docs service on init; Drive is lazy."""
        with patch("desk.services.docs.build") as mock_build:
            mock_build.return_value = MagicMock()
            from desk.services.docs import DocsClient

            DocsClient(mock_credentials)

            # Only Docs service created eagerly
            assert mock_build.call_count == 1
            assert mock_build.call_args_list[0][0] == ("docs", "v1")

    def test_drive_service_created_lazily_on_first_access(self, mock_credentials):
        """Drive service should be created on first access to _drive property."""
        with patch("desk.services.docs.build") as mock_build:
            mock_build.return_value = MagicMock()
            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            assert mock_build.call_count == 1

            # Access _drive triggers Drive build
            _ = client._drive
            assert mock_build.call_count == 2
            assert mock_build.call_args_list[1][0] == ("drive", "v3")

            # Second access should not trigger another build
            _ = client._drive
            assert mock_build.call_count == 2


class TestDocsRead:
    """Tests for DocsClient.read method."""

    def test_read_returns_document_content(self, mock_credentials):
        """Should return document content."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            documents_mock = mock_service.documents.return_value
            documents_mock.get.return_value.execute.return_value = {
                "documentId": "doc123",
                "title": "Test Document",
                "body": {
                    "content": [
                        {"paragraph": {"elements": [{"textRun": {"content": "Hello World\n"}}]}},
                    ]
                },
            }

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            result = client.read("doc123")

            assert "documentId" in result
            assert result["title"] == "Test Document"

    def test_read_does_not_build_drive_service(self, mock_credentials):
        """read() should not trigger Drive service creation."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            documents_mock = mock_service.documents.return_value
            documents_mock.get.return_value.execute.return_value = {
                "documentId": "doc123",
                "title": "Test",
                "body": {"content": []},
            }

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            client.read("doc123")

            # Only Docs build, no Drive build
            assert mock_build.call_count == 1

    def test_read_not_found_raises_error(self, mock_credentials):
        """Should raise error when document not found."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            documents_mock = mock_service.documents.return_value
            http_error = HttpError(
                resp=MagicMock(status=404),
                content=b'{"error": {"message": "Document not found"}}'
            )
            documents_mock.get.return_value.execute.side_effect = http_error

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            with pytest.raises(RuntimeError, match="Docs API error"):
                client.read("nonexistent_id")


class TestDocsReadBullets:
    """Tests for bullet list extraction in DocsClient.read."""

    def test_unordered_bullets_prefixed_with_dash(self, mock_credentials):
        """Bullet list items should be prefixed with '- ' in read output."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            documents_mock = mock_service.documents.return_value
            documents_mock.get.return_value.execute.return_value = {
                "documentId": "doc123",
                "title": "Bullet Doc",
                "body": {
                    "content": [
                        {
                            "paragraph": {
                                "elements": [{"textRun": {"content": "Header\n"}}],
                            },
                        },
                        {
                            "paragraph": {
                                "bullet": {"listId": "kix.abc", "nestingLevel": 0},
                                "elements": [{"textRun": {"content": "Item one\n"}}],
                            },
                        },
                        {
                            "paragraph": {
                                "bullet": {"listId": "kix.abc", "nestingLevel": 0},
                                "elements": [{"textRun": {"content": "Item two\n"}}],
                            },
                        },
                    ]
                },
            }

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            result = client.read("doc123")

            assert "- Item one\n" in result["body"]
            assert "- Item two\n" in result["body"]
            assert "Header\n" in result["body"]
            # Header should NOT have a bullet prefix
            assert "- Header" not in result["body"]

    def test_nested_bullets_indented(self, mock_credentials):
        """Nested bullet items should have indentation."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            documents_mock = mock_service.documents.return_value
            documents_mock.get.return_value.execute.return_value = {
                "documentId": "doc123",
                "title": "Nested Doc",
                "body": {
                    "content": [
                        {
                            "paragraph": {
                                "bullet": {"listId": "kix.abc", "nestingLevel": 0},
                                "elements": [{"textRun": {"content": "Top level\n"}}],
                            },
                        },
                        {
                            "paragraph": {
                                "bullet": {"listId": "kix.abc", "nestingLevel": 1},
                                "elements": [{"textRun": {"content": "Nested\n"}}],
                            },
                        },
                    ]
                },
            }

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            result = client.read("doc123")

            assert "- Top level\n" in result["body"]
            assert "  - Nested\n" in result["body"]


class TestDocsReadTables:
    """Tests for table extraction in DocsClient.read."""

    def _make_paragraph(self, text):
        return {"paragraph": {"elements": [{"textRun": {"content": text}}]}}

    def _make_table(self, rows):
        """Build a Google Docs API table structure from a list of lists of strings."""
        return {
            "table": {
                "tableRows": [
                    {
                        "tableCells": [
                            {"content": [self._make_paragraph(cell)]}
                            for cell in row
                        ]
                    }
                    for row in rows
                ]
            }
        }

    def test_read_table_only_doc(self, mock_credentials):
        """Should extract table content from a doc with only tables."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            documents_mock = mock_service.documents.return_value
            documents_mock.get.return_value.execute.return_value = {
                "documentId": "doc123",
                "title": "Table Doc",
                "body": {
                    "content": [
                        self._make_table([
                            ["Name", "Status"],
                            ["Alice", "Active"],
                            ["Bob", "Inactive"],
                        ])
                    ]
                },
            }

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            result = client.read("doc123")

            assert "Name" in result["body"]
            assert "Alice" in result["body"]
            assert "| Name | Status |" in result["body"]
            assert "| --- | --- |" in result["body"]
            assert "| Alice | Active |" in result["body"]

    def test_read_mixed_paragraphs_and_tables(self, mock_credentials):
        """Should preserve both paragraphs and tables."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            documents_mock = mock_service.documents.return_value
            documents_mock.get.return_value.execute.return_value = {
                "documentId": "doc123",
                "title": "Mixed Doc",
                "body": {
                    "content": [
                        self._make_paragraph("Introduction\n"),
                        self._make_table([["Col A", "Col B"], ["1", "2"]]),
                        self._make_paragraph("Conclusion\n"),
                    ]
                },
            }

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            result = client.read("doc123")

            body = result["body"]
            assert "Introduction" in body
            assert "| Col A | Col B |" in body
            assert "Conclusion" in body
            # Paragraph before table before paragraph
            assert body.index("Introduction") < body.index("Col A")
            assert body.index("Col A") < body.index("Conclusion")

    def test_read_empty_table(self, mock_credentials):
        """Should handle table with no rows gracefully."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            documents_mock = mock_service.documents.return_value
            documents_mock.get.return_value.execute.return_value = {
                "documentId": "doc123",
                "title": "Empty Table",
                "body": {
                    "content": [{"table": {"tableRows": []}}]
                },
            }

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            result = client.read("doc123")
            assert result["body"] == ""

    def test_read_table_with_pipe_in_cell(self, mock_credentials):
        """Should escape pipe characters in cell text."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            documents_mock = mock_service.documents.return_value
            documents_mock.get.return_value.execute.return_value = {
                "documentId": "doc123",
                "title": "Pipe Doc",
                "body": {
                    "content": [
                        self._make_table([
                            ["Command", "Example"],
                            ["grep", "grep foo|bar"],
                        ])
                    ]
                },
            }

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            result = client.read("doc123")

            assert "grep foo\\|bar" in result["body"]

    def test_read_table_with_uneven_rows(self, mock_credentials):
        """Should pad shorter rows to match column count."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            documents_mock = mock_service.documents.return_value
            documents_mock.get.return_value.execute.return_value = {
                "documentId": "doc123",
                "title": "Uneven Doc",
                "body": {
                    "content": [
                        {
                            "table": {
                                "tableRows": [
                                    {
                                        "tableCells": [
                                            {"content": [self._make_paragraph("A")]},
                                            {"content": [self._make_paragraph("B")]},
                                            {"content": [self._make_paragraph("C")]},
                                        ]
                                    },
                                    {
                                        "tableCells": [
                                            {"content": [self._make_paragraph("1")]},
                                        ]
                                    },
                                ]
                            }
                        }
                    ]
                },
            }

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            result = client.read("doc123")

            lines = result["body"].strip().split("\n")
            # Header should have 3 columns
            assert lines[0].count("|") == 4  # | A | B | C |
            # Data row should also have 3 columns (padded)
            assert lines[2].count("|") == 4  # | 1 |  |  |


class TestDocsReadHyperlinks:
    """Tests for hyperlink preservation in DocsClient.read."""

    def test_read_preserves_hyperlinks_as_markdown(self, mock_credentials):
        """Hyperlinked text should be emitted as [text](url)."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            documents_mock = mock_service.documents.return_value
            documents_mock.get.return_value.execute.return_value = {
                "documentId": "doc123",
                "title": "Link Doc",
                "body": {
                    "content": [
                        {
                            "paragraph": {
                                "elements": [
                                    {"textRun": {"content": "Visit "}},
                                    {
                                        "textRun": {
                                            "content": "our site",
                                            "textStyle": {
                                                "link": {"url": "https://example.com"}
                                            },
                                        }
                                    },
                                    {"textRun": {"content": " for details.\n"}},
                                ],
                            },
                        },
                    ]
                },
            }

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            result = client.read("doc123")

            assert "[our site](https://example.com)" in result["body"]
            assert "Visit [our site](https://example.com) for details." in result["body"]

    def test_read_link_with_trailing_newline(self, mock_credentials):
        """Trailing newline on linked text should be preserved outside the markdown link."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            documents_mock = mock_service.documents.return_value
            documents_mock.get.return_value.execute.return_value = {
                "documentId": "doc123",
                "title": "Link Newline",
                "body": {
                    "content": [
                        {
                            "paragraph": {
                                "elements": [
                                    {
                                        "textRun": {
                                            "content": "click here\n",
                                            "textStyle": {
                                                "link": {"url": "https://example.com"}
                                            },
                                        }
                                    },
                                ],
                            },
                        },
                    ]
                },
            }

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            result = client.read("doc123")

            assert result["body"] == "[click here](https://example.com)\n"

    def test_read_escapes_markdown_delimiters_in_links(self, mock_credentials):
        """Brackets in text and parens in URLs should be escaped."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            documents_mock = mock_service.documents.return_value
            documents_mock.get.return_value.execute.return_value = {
                "documentId": "doc123",
                "title": "Escape Doc",
                "body": {
                    "content": [
                        {
                            "paragraph": {
                                "elements": [
                                    {
                                        "textRun": {
                                            "content": "foo]bar\n",
                                            "textStyle": {
                                                "link": {"url": "https://example.com/a(b)"}
                                            },
                                        }
                                    },
                                ],
                            },
                        },
                    ]
                },
            }

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            result = client.read("doc123")

            assert r"[foo\]bar](https://example.com/a\(b\))" in result["body"]

    def test_read_plain_text_with_empty_textstyle(self, mock_credentials):
        """Text with textStyle but no link should not get markdown link syntax."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            documents_mock = mock_service.documents.return_value
            documents_mock.get.return_value.execute.return_value = {
                "documentId": "doc123",
                "title": "Styled Doc",
                "body": {
                    "content": [
                        {
                            "paragraph": {
                                "elements": [
                                    {
                                        "textRun": {
                                            "content": "bold text\n",
                                            "textStyle": {"bold": True},
                                        }
                                    },
                                ],
                            },
                        },
                    ]
                },
            }

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            result = client.read("doc123")

            assert result["body"] == "bold text\n"
            assert "[" not in result["body"]


class TestDocsCreate:
    """Tests for DocsClient.create method."""

    def test_create_returns_document(self, mock_credentials):
        """Should return created document."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            documents_mock = mock_service.documents.return_value
            documents_mock.create.return_value.execute.return_value = {
                "documentId": "new_doc_id",
                "title": "New Document",
            }

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            result = client.create("New Document")

            assert result["documentId"] == "new_doc_id"
            assert result["title"] == "New Document"
            documents_mock.create.assert_called_once()

    def test_create_triggers_drive_build(self, mock_credentials):
        """create() needs Drive for webViewLink, so it should build Drive."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            documents_mock = mock_service.documents.return_value
            documents_mock.create.return_value.execute.return_value = {
                "documentId": "new_doc_id",
                "title": "New Document",
            }

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            assert mock_build.call_count == 1  # Only Docs

            client.create("New Document")

            # Docs + Drive = 2 builds
            assert mock_build.call_count == 2

    def test_create_with_body_uses_markdown_by_default(self, mock_credentials):
        """Should call write_markdown when body is provided and markdown=True."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            documents_mock = mock_service.documents.return_value
            documents_mock.create.return_value.execute.return_value = {
                "documentId": "new_doc_id",
                "title": "Markdown Doc",
            }
            # write_markdown needs the doc body for replace mode
            documents_mock.get.return_value.execute.return_value = {
                "documentId": "new_doc_id",
                "body": {"content": [{"endIndex": 1}]},
            }

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            with patch.object(client, "write_markdown") as mock_wm:
                client.create("Markdown Doc", body="# Hello")
                mock_wm.assert_called_once_with("new_doc_id", "# Hello", replace=True)

    def test_create_with_plain_text(self, mock_credentials):
        """Should use insertText when markdown=False."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            documents_mock = mock_service.documents.return_value
            documents_mock.create.return_value.execute.return_value = {
                "documentId": "new_doc_id",
                "title": "Plain Doc",
            }

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            with patch.object(client, "write_markdown") as mock_wm:
                client.create("Plain Doc", body="plain text", markdown=False)
                mock_wm.assert_not_called()
                # Should have used batchUpdate with insertText
                documents_mock.batchUpdate.assert_called_once()

    def test_create_empty_body_skips_content(self, mock_credentials):
        """Should not write any content when body is empty."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            documents_mock = mock_service.documents.return_value
            documents_mock.create.return_value.execute.return_value = {
                "documentId": "new_doc_id",
                "title": "Empty Doc",
            }

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            with patch.object(client, "write_markdown") as mock_wm:
                client.create("Empty Doc", body="")
                mock_wm.assert_not_called()
                documents_mock.batchUpdate.assert_not_called()


class TestDocsFindAndReplace:
    """Tests for DocsClient.find_and_replace method."""

    def test_find_and_replace_basic(self, mock_credentials):
        """Should send replaceAllText request and return occurrences changed."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            documents_mock = mock_service.documents.return_value
            documents_mock.batchUpdate.return_value.execute.return_value = {
                "replies": [{"replaceAllText": {"occurrencesChanged": 3}}],
                "documentId": "doc123",
            }

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            result = client.find_and_replace("doc123", "old", "new")

            assert result["documentId"] == "doc123"
            assert result["occurrences_changed"] == 3
            assert result["status"] == "ok"

            # Verify the API call structure
            call_kwargs = documents_mock.batchUpdate.call_args
            requests = call_kwargs[1]["body"]["requests"]
            assert len(requests) == 1
            req = requests[0]["replaceAllText"]
            assert req["containsText"]["text"] == "old"
            assert req["containsText"]["matchCase"] is True
            assert req["replaceText"] == "new"

    def test_find_and_replace_case_insensitive(self, mock_credentials):
        """Should pass matchCase=False when match_case is False."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            documents_mock = mock_service.documents.return_value
            documents_mock.batchUpdate.return_value.execute.return_value = {
                "replies": [{"replaceAllText": {"occurrencesChanged": 1}}],
                "documentId": "doc123",
            }

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            client.find_and_replace("doc123", "OLD", "new", match_case=False)

            call_kwargs = documents_mock.batchUpdate.call_args
            req = call_kwargs[1]["body"]["requests"][0]["replaceAllText"]
            assert req["containsText"]["matchCase"] is False

    def test_find_and_replace_api_error(self, mock_credentials):
        """Should raise RuntimeError on API error."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            documents_mock = mock_service.documents.return_value
            http_error = HttpError(
                resp=MagicMock(status=404),
                content=b'{"error": {"message": "Document not found"}}',
            )
            documents_mock.batchUpdate.return_value.execute.side_effect = http_error

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            with pytest.raises(RuntimeError, match="Docs API error"):
                client.find_and_replace("bad_id", "old", "new")


class TestDocsUpdate:
    """Tests for DocsClient.update method."""

    def test_update_appends_text(self, mock_credentials):
        """Should batch update document with text append."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            documents_mock = mock_service.documents.return_value
            # Mock get to return document structure for finding end index
            documents_mock.get.return_value.execute.return_value = {
                "documentId": "doc123",
                "body": {"content": [{"endIndex": 10}]},
            }
            documents_mock.batchUpdate.return_value.execute.return_value = {
                "replies": [],
                "documentId": "doc123",
            }

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            client.update("doc123", text="New text to append")

            documents_mock.batchUpdate.assert_called_once()

    def test_update_replaces_text(self, mock_credentials):
        """Should replace all document content when mode=replace."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            documents_mock = mock_service.documents.return_value
            documents_mock.get.return_value.execute.return_value = {
                "documentId": "doc123",
                "body": {"content": [{"endIndex": 50}]},
            }
            documents_mock.batchUpdate.return_value.execute.return_value = {
                "replies": [],
                "documentId": "doc123",
            }

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            client.update("doc123", text="New content", mode="replace")

            documents_mock.batchUpdate.assert_called_once()


class TestDocsInsertAt:
    """Tests for DocsClient.insert_at method."""

    def test_insert_at_index(self, mock_credentials):
        """Should insert text at a specific index."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service
            documents_mock = mock_service.documents.return_value
            documents_mock.batchUpdate.return_value.execute.return_value = {"replies": []}

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            result = client.insert_at("doc123", "Hello", index=5)

            assert result["status"] == "ok"
            call_kwargs = documents_mock.batchUpdate.call_args
            req = call_kwargs[1]["body"]["requests"][0]
            assert req["insertText"]["location"]["index"] == 5
            assert req["insertText"]["text"] == "Hello"

    def test_insert_at_end(self, mock_credentials):
        """Should use EndOfSegmentLocation when index is None."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service
            documents_mock = mock_service.documents.return_value
            documents_mock.batchUpdate.return_value.execute.return_value = {"replies": []}

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            result = client.insert_at("doc123", "Hello", index=None)

            assert result["status"] == "ok"
            call_kwargs = documents_mock.batchUpdate.call_args
            req = call_kwargs[1]["body"]["requests"][0]
            assert "endOfSegmentLocation" in req["insertText"]


class TestDocsFindParagraphBoundary:
    """Tests for DocsClient.find_paragraph_boundary method."""

    def _make_client(self, mock_credentials, body_content):
        """Helper to create a client with mocked document body."""
        from unittest.mock import MagicMock, patch
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service
            documents_mock = mock_service.documents.return_value
            documents_mock.get.return_value.execute.return_value = {
                "documentId": "doc123",
                "title": "Test Doc",
                "body": {"content": body_content},
            }
            from desk.services.docs import DocsClient
            client = DocsClient(mock_credentials)
            return client

    def test_after_returns_paragraph_end(self, mock_credentials):
        """--after-paragraph should return the endIndex of the containing paragraph."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service
            documents_mock = mock_service.documents.return_value
            documents_mock.get.return_value.execute.return_value = {
                "documentId": "doc123",
                "title": "Test",
                "body": {
                    "content": [
                        {"startIndex": 0, "endIndex": 1, "sectionBreak": {}},
                        {
                            "startIndex": 1, "endIndex": 20,
                            "paragraph": {
                                "elements": [{"textRun": {"content": "First paragraph\n"}}],
                            },
                        },
                        {
                            "startIndex": 20, "endIndex": 40,
                            "paragraph": {
                                "elements": [{"textRun": {"content": "Second paragraph\n"}}],
                            },
                        },
                    ]
                },
            }
            from desk.services.docs import DocsClient
            client = DocsClient(mock_credentials)
            result = client.find_paragraph_boundary("doc123", 10, position="after")
            assert result == 20  # endIndex of first paragraph

    def test_before_returns_paragraph_start(self, mock_credentials):
        """--before-paragraph should return the startIndex of the containing paragraph."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service
            documents_mock = mock_service.documents.return_value
            documents_mock.get.return_value.execute.return_value = {
                "documentId": "doc123",
                "title": "Test",
                "body": {
                    "content": [
                        {"startIndex": 0, "endIndex": 1, "sectionBreak": {}},
                        {
                            "startIndex": 1, "endIndex": 20,
                            "paragraph": {
                                "elements": [{"textRun": {"content": "First paragraph\n"}}],
                            },
                        },
                        {
                            "startIndex": 20, "endIndex": 40,
                            "paragraph": {
                                "elements": [{"textRun": {"content": "Second paragraph\n"}}],
                            },
                        },
                    ]
                },
            }
            from desk.services.docs import DocsClient
            client = DocsClient(mock_credentials)
            result = client.find_paragraph_boundary("doc123", 25, position="before")
            assert result == 20  # startIndex of second paragraph

    def test_index_not_in_any_paragraph_raises(self, mock_credentials):
        """Should raise RuntimeError if index is not in any paragraph."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service
            documents_mock = mock_service.documents.return_value
            documents_mock.get.return_value.execute.return_value = {
                "documentId": "doc123",
                "title": "Test",
                "body": {
                    "content": [
                        {"startIndex": 0, "endIndex": 1, "sectionBreak": {}},
                        {
                            "startIndex": 1, "endIndex": 20,
                            "paragraph": {
                                "elements": [{"textRun": {"content": "Only paragraph\n"}}],
                            },
                        },
                    ]
                },
            }
            from desk.services.docs import DocsClient
            client = DocsClient(mock_credentials)
            with pytest.raises(RuntimeError, match="No paragraph found"):
                client.find_paragraph_boundary("doc123", 999, position="after")


class TestDocsDeleteRange:
    """Tests for DocsClient.delete_range method."""

    def test_delete_range(self, mock_credentials):
        """Should send deleteContentRange request."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service
            documents_mock = mock_service.documents.return_value
            documents_mock.batchUpdate.return_value.execute.return_value = {"replies": []}

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            result = client.delete_range("doc123", 5, 20)

            assert result["status"] == "ok"
            call_kwargs = documents_mock.batchUpdate.call_args
            req = call_kwargs[1]["body"]["requests"][0]
            assert req["deleteContentRange"]["range"]["startIndex"] == 5
            assert req["deleteContentRange"]["range"]["endIndex"] == 20


class TestDocsUpdateTextStyle:
    """Tests for DocsClient.update_text_style method."""

    def test_bold_style(self, mock_credentials):
        """Should send updateTextStyle with bold."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service
            documents_mock = mock_service.documents.return_value
            documents_mock.batchUpdate.return_value.execute.return_value = {"replies": []}

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            result = client.update_text_style("doc123", 1, 10, bold=True)

            assert result["status"] == "ok"
            call_kwargs = documents_mock.batchUpdate.call_args
            req = call_kwargs[1]["body"]["requests"][0]["updateTextStyle"]
            assert req["textStyle"]["bold"] is True
            assert "bold" in req["fields"]

    def test_no_styles_specified(self, mock_credentials):
        """Should return without API call when no styles given."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service
            documents_mock = mock_service.documents.return_value

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            result = client.update_text_style("doc123", 1, 10)

            assert result["note"] == "no styles specified"
            documents_mock.batchUpdate.assert_not_called()


class TestDocsInsertTable:
    """Tests for DocsClient.insert_table method."""

    def test_insert_table_at_end(self, mock_credentials):
        """Should insert table with EndOfSegmentLocation."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service
            documents_mock = mock_service.documents.return_value
            documents_mock.batchUpdate.return_value.execute.return_value = {"replies": []}

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            result = client.insert_table("doc123", 3, 4)

            assert result["status"] == "ok"
            call_kwargs = documents_mock.batchUpdate.call_args
            req = call_kwargs[1]["body"]["requests"][0]["insertTable"]
            assert req["rows"] == 3
            assert req["columns"] == 4
            assert "endOfSegmentLocation" in req


class TestDocsUpdateParagraphStyle:
    """Tests for DocsClient.update_paragraph_style method."""

    def test_heading_style(self, mock_credentials):
        """Should send updateParagraphStyle with heading."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service
            documents_mock = mock_service.documents.return_value
            documents_mock.batchUpdate.return_value.execute.return_value = {"replies": []}

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            result = client.update_paragraph_style("doc123", 1, 20, heading=2)

            assert result["status"] == "ok"
            call_kwargs = documents_mock.batchUpdate.call_args
            req = call_kwargs[1]["body"]["requests"][0]["updateParagraphStyle"]
            assert req["paragraphStyle"]["namedStyleType"] == "HEADING_2"
            assert "namedStyleType" in req["fields"]

    def test_normal_text_heading_zero(self, mock_credentials):
        """Should set NORMAL_TEXT when heading=0."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service
            documents_mock = mock_service.documents.return_value
            documents_mock.batchUpdate.return_value.execute.return_value = {"replies": []}

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            client.update_paragraph_style("doc123", 1, 20, heading=0)

            call_kwargs = documents_mock.batchUpdate.call_args
            req = call_kwargs[1]["body"]["requests"][0]["updateParagraphStyle"]
            assert req["paragraphStyle"]["namedStyleType"] == "NORMAL_TEXT"

    def test_alignment_style(self, mock_credentials):
        """Should send updateParagraphStyle with alignment."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service
            documents_mock = mock_service.documents.return_value
            documents_mock.batchUpdate.return_value.execute.return_value = {"replies": []}

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            client.update_paragraph_style("doc123", 1, 50, alignment="CENTER")

            call_kwargs = documents_mock.batchUpdate.call_args
            req = call_kwargs[1]["body"]["requests"][0]["updateParagraphStyle"]
            assert req["paragraphStyle"]["alignment"] == "CENTER"

    def test_no_styles_specified(self, mock_credentials):
        """Should return without API call when no styles given."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service
            documents_mock = mock_service.documents.return_value

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            result = client.update_paragraph_style("doc123", 1, 10)

            assert result["note"] == "no styles specified"
            documents_mock.batchUpdate.assert_not_called()

    def test_spacing_and_line_spacing(self, mock_credentials):
        """Should send updateParagraphStyle with spacing fields."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service
            documents_mock = mock_service.documents.return_value
            documents_mock.batchUpdate.return_value.execute.return_value = {"replies": []}

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            result = client.update_paragraph_style(
                "doc123", 1, 99,
                space_above=4,
                space_below=8,
                line_spacing=115,
            )

            assert result["status"] == "ok"
            req = documents_mock.batchUpdate.call_args[1]["body"]["requests"][0][
                "updateParagraphStyle"
            ]
            assert req["paragraphStyle"]["spaceAbove"] == {"magnitude": 4, "unit": "PT"}
            assert req["paragraphStyle"]["spaceBelow"] == {"magnitude": 8, "unit": "PT"}
            assert req["paragraphStyle"]["lineSpacing"] == 115
            fields = req["fields"].split(",")
            assert "spaceAbove" in fields
            assert "spaceBelow" in fields
            assert "lineSpacing" in fields

    def test_indent_fields(self, mock_credentials):
        """Should send updateParagraphStyle with indent fields."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service
            documents_mock = mock_service.documents.return_value
            documents_mock.batchUpdate.return_value.execute.return_value = {"replies": []}

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            client.update_paragraph_style(
                "doc123", 1, 99,
                indent_start=36,
                indent_end=18,
                indent_first_line=24,
            )

            req = documents_mock.batchUpdate.call_args[1]["body"]["requests"][0][
                "updateParagraphStyle"
            ]
            assert req["paragraphStyle"]["indentStart"] == {"magnitude": 36, "unit": "PT"}
            assert req["paragraphStyle"]["indentEnd"] == {"magnitude": 18, "unit": "PT"}
            assert req["paragraphStyle"]["indentFirstLine"] == {"magnitude": 24, "unit": "PT"}

    def test_negative_spacing_rejected(self, mock_credentials):
        """Should raise ValueError on negative spacing values."""
        with patch("desk.services.docs.build") as mock_build:
            mock_build.return_value = MagicMock()
            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            with pytest.raises(ValueError, match="space_below"):
                client.update_paragraph_style("doc123", 1, 10, space_below=-1)

    def test_line_spacing_floor_rejected(self, mock_credentials):
        """Should raise ValueError when line_spacing below the 50% floor."""
        with patch("desk.services.docs.build") as mock_build:
            mock_build.return_value = MagicMock()
            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            with pytest.raises(ValueError, match="line_spacing"):
                client.update_paragraph_style("doc123", 1, 10, line_spacing=10)


class TestDocsInsertImage:
    """Tests for DocsClient.insert_image method."""

    def test_insert_image_at_end(self, mock_credentials):
        """Should insert image with EndOfSegmentLocation."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service
            documents_mock = mock_service.documents.return_value
            documents_mock.batchUpdate.return_value.execute.return_value = {"replies": []}

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            result = client.insert_image("doc123", "https://example.com/img.png")

            assert result["status"] == "ok"
            call_kwargs = documents_mock.batchUpdate.call_args
            req = call_kwargs[1]["body"]["requests"][0]["insertInlineImage"]
            assert req["uri"] == "https://example.com/img.png"
            assert "endOfSegmentLocation" in req

    def test_insert_image_at_index_with_size(self, mock_credentials):
        """Should insert image at index with width/height."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service
            documents_mock = mock_service.documents.return_value
            documents_mock.batchUpdate.return_value.execute.return_value = {"replies": []}

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            result = client.insert_image(
                "doc123", "https://example.com/img.png",
                index=5, width=200.0, height=100.0,
            )

            assert result["status"] == "ok"
            call_kwargs = documents_mock.batchUpdate.call_args
            req = call_kwargs[1]["body"]["requests"][0]["insertInlineImage"]
            assert req["location"]["index"] == 5
            assert req["objectSize"]["width"]["magnitude"] == 200.0
            assert req["objectSize"]["height"]["magnitude"] == 100.0

    def test_insert_image_api_error(self, mock_credentials):
        """Should raise RuntimeError on API error."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service
            documents_mock = mock_service.documents.return_value
            http_error = HttpError(
                resp=MagicMock(status=400),
                content=b'{"error": {"message": "Invalid URI"}}',
            )
            documents_mock.batchUpdate.return_value.execute.side_effect = http_error

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            with pytest.raises(RuntimeError, match="Docs API error"):
                client.insert_image("doc123", "not-a-url")


class TestDocsInspect:
    """Tests for DocsClient.inspect method."""

    def test_inspect_returns_elements(self, mock_credentials):
        """Should return document structure with indices."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service
            documents_mock = mock_service.documents.return_value
            documents_mock.get.return_value.execute.return_value = {
                "documentId": "doc123",
                "title": "Test Doc",
                "body": {
                    "content": [
                        {
                            "startIndex": 0,
                            "endIndex": 1,
                            "sectionBreak": {},
                        },
                        {
                            "startIndex": 1,
                            "endIndex": 15,
                            "paragraph": {
                                "paragraphStyle": {"namedStyleType": "HEADING_1"},
                                "elements": [{"textRun": {"content": "Hello World\n"}}],
                            },
                        },
                    ]
                },
            }

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            result = client.inspect("doc123")

            assert result["title"] == "Test Doc"
            assert len(result["elements"]) == 2
            assert result["elements"][1]["type"] == "paragraph"
            assert result["elements"][1]["style"] == "HEADING_1"
            assert result["elements"][1]["startIndex"] == 1


    def test_inspect_detects_bullet_list(self, mock_credentials):
        """Should flag paragraphs with bullet property."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service
            documents_mock = mock_service.documents.return_value
            documents_mock.get.return_value.execute.return_value = {
                "documentId": "doc123",
                "title": "Test Doc",
                "body": {
                    "content": [
                        {
                            "startIndex": 1,
                            "endIndex": 15,
                            "paragraph": {
                                "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                                "bullet": {"listId": "kix.abc", "nestingLevel": 0},
                                "elements": [{"textRun": {"content": "Bullet item\n"}}],
                            },
                        },
                    ]
                },
            }

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            result = client.inspect("doc123")

            assert len(result["elements"]) == 1
            assert result["elements"][0]["bullet"] is True

    def test_inspect_detects_horizontal_rule(self, mock_credentials):
        """Should flag paragraphs containing a horizontalRule element."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service
            documents_mock = mock_service.documents.return_value
            documents_mock.get.return_value.execute.return_value = {
                "documentId": "doc123",
                "title": "Test Doc",
                "body": {
                    "content": [
                        {
                            "startIndex": 50,
                            "endIndex": 51,
                            "paragraph": {
                                "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                                "elements": [
                                    {
                                        "horizontalRule": {},
                                        "startIndex": 50,
                                        "endIndex": 51,
                                    }
                                ],
                            },
                        },
                    ]
                },
            }

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            result = client.inspect("doc123")

            assert len(result["elements"]) == 1
            assert result["elements"][0]["horizontalRule"] is True

    def test_inspect_detects_border_bottom_hr(self, mock_credentials):
        """Should detect empty paragraphs with borderBottom as horizontal rules."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service
            documents_mock = mock_service.documents.return_value
            documents_mock.get.return_value.execute.return_value = {
                "documentId": "doc123",
                "title": "Test Doc",
                "body": {
                    "content": [
                        {
                            "startIndex": 50,
                            "endIndex": 51,
                            "paragraph": {
                                "paragraphStyle": {
                                    "namedStyleType": "NORMAL_TEXT",
                                    "borderBottom": {
                                        "color": {"color": {"rgbColor": {"red": 0.8, "green": 0.8, "blue": 0.8}}},
                                        "width": {"magnitude": 1, "unit": "PT"},
                                        "dashStyle": "SOLID",
                                    },
                                },
                                "elements": [{"textRun": {"content": "\n"}}],
                            },
                        },
                    ]
                },
            }

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            result = client.inspect("doc123")

            assert len(result["elements"]) == 1
            assert result["elements"][0]["horizontalRule"] is True

    def test_inspect_normal_paragraph_no_extra_flags(self, mock_credentials):
        """Normal paragraphs should not have bullet or horizontalRule flags."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service
            documents_mock = mock_service.documents.return_value
            documents_mock.get.return_value.execute.return_value = {
                "documentId": "doc123",
                "title": "Test Doc",
                "body": {
                    "content": [
                        {
                            "startIndex": 1,
                            "endIndex": 15,
                            "paragraph": {
                                "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                                "elements": [{"textRun": {"content": "Normal text\n"}}],
                            },
                        },
                    ]
                },
            }

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            result = client.inspect("doc123")

            assert len(result["elements"]) == 1
            assert "bullet" not in result["elements"][0]
            assert "horizontalRule" not in result["elements"][0]


class TestDocsListTabs:
    """Tests for DocsClient.list_tabs method."""

    def test_list_tabs_returns_tab_metadata(self, mock_credentials):
        """Should return tab list with IDs and titles."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service
            documents_mock = mock_service.documents.return_value
            documents_mock.get.return_value.execute.return_value = {
                "documentId": "doc123",
                "tabs": [
                    {
                        "tabProperties": {"tabId": "t.0", "title": "Tab 1", "index": 0},
                        "documentTab": {"body": {"content": []}},
                        "childTabs": [],
                    },
                    {
                        "tabProperties": {"tabId": "t.1", "title": "Tab 2", "index": 1},
                        "documentTab": {"body": {"content": []}},
                        "childTabs": [],
                    },
                ],
            }

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            result = client.list_tabs("doc123")

            assert len(result) == 2
            assert result[0]["tabId"] == "t.0"
            assert result[0]["title"] == "Tab 1"
            assert result[1]["tabId"] == "t.1"
            # Verify includeTabsContent was passed
            documents_mock.get.assert_called_with(
                documentId="doc123", includeTabsContent=True
            )

    def test_list_tabs_with_nested_children(self, mock_credentials):
        """Should flatten nested tabs."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service
            documents_mock = mock_service.documents.return_value
            documents_mock.get.return_value.execute.return_value = {
                "documentId": "doc123",
                "tabs": [
                    {
                        "tabProperties": {"tabId": "t.0", "title": "Parent", "index": 0},
                        "documentTab": {"body": {"content": []}},
                        "childTabs": [
                            {
                                "tabProperties": {
                                    "tabId": "t.child",
                                    "title": "Child",
                                    "index": 0,
                                    "parentTabId": "t.0",
                                },
                                "documentTab": {"body": {"content": []}},
                                "childTabs": [],
                            },
                        ],
                    },
                ],
            }

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            result = client.list_tabs("doc123")

            assert len(result) == 2
            assert result[0]["tabId"] == "t.0"
            assert result[1]["tabId"] == "t.child"
            assert result[1]["parentTabId"] == "t.0"


class TestDocsAddTab:
    """Tests for DocsClient.add_tab method."""

    def test_add_tab_basic(self, mock_credentials):
        """Should send createTab request."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service
            documents_mock = mock_service.documents.return_value
            documents_mock.batchUpdate.return_value.execute.return_value = {
                "replies": [{
                    "createTab": {
                        "tab": {
                            "tabProperties": {"tabId": "t.new", "title": "Notes"},
                        }
                    }
                }],
            }

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            result = client.add_tab("doc123", "Notes")

            assert result["tabId"] == "t.new"
            assert result["title"] == "Notes"
            call_kwargs = documents_mock.batchUpdate.call_args
            req = call_kwargs[1]["body"]["requests"][0]["createTab"]
            assert req["tabProperties"]["title"] == "Notes"

    def test_add_tab_with_parent(self, mock_credentials):
        """Should include parentTabId in request."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service
            documents_mock = mock_service.documents.return_value
            documents_mock.batchUpdate.return_value.execute.return_value = {
                "replies": [{"createTab": {"tab": {"tabProperties": {"tabId": "t.child", "title": "Sub"}}}}],
            }

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            client.add_tab("doc123", "Sub", parent_tab_id="t.0")

            call_kwargs = documents_mock.batchUpdate.call_args
            req = call_kwargs[1]["body"]["requests"][0]["createTab"]
            assert req["parentTabId"] == "t.0"


class TestDocsDeleteTab:
    """Tests for DocsClient.delete_tab method."""

    def test_delete_tab(self, mock_credentials):
        """Should send deleteTab request."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service
            documents_mock = mock_service.documents.return_value

            documents_mock.batchUpdate.return_value.execute.return_value = {"replies": []}

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            result = client.delete_tab("doc123", "t.1")

            assert result["status"] == "ok"
            call_kwargs = documents_mock.batchUpdate.call_args
            req = call_kwargs[1]["body"]["requests"][0]["deleteTab"]
            assert req["tabId"] == "t.1"


class TestDocsRenameTab:
    """Tests for DocsClient.rename_tab method."""

    def test_rename_tab(self, mock_credentials):
        """Should send updateTabProperties request."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service
            documents_mock = mock_service.documents.return_value

            documents_mock.batchUpdate.return_value.execute.return_value = {"replies": []}

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            result = client.rename_tab("doc123", "t.0", "New Name")

            assert result["tabId"] == "t.0"
            assert result["title"] == "New Name"
            call_kwargs = documents_mock.batchUpdate.call_args
            req = call_kwargs[1]["body"]["requests"][0]["updateTabProperties"]
            assert req["tabProperties"]["tabId"] == "t.0"
            assert req["tabProperties"]["title"] == "New Name"
            assert req["fields"] == "title"


class TestDocsTabIdOnExistingMethods:
    """Tests for tab_id parameter on existing service methods."""

    def test_delete_range_with_tab_id(self, mock_credentials):
        """Should include tabId in the range when tab_id is provided."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service
            documents_mock = mock_service.documents.return_value

            documents_mock.batchUpdate.return_value.execute.return_value = {"replies": []}

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            client.delete_range("doc123", 5, 20, tab_id="t.1")

            call_kwargs = documents_mock.batchUpdate.call_args
            req = call_kwargs[1]["body"]["requests"][0]["deleteContentRange"]
            assert req["range"]["tabId"] == "t.1"
            assert req["range"]["startIndex"] == 5
            assert req["range"]["endIndex"] == 20

    def test_insert_at_with_tab_id(self, mock_credentials):
        """Should include tabId in location when tab_id is provided."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service
            documents_mock = mock_service.documents.return_value

            documents_mock.batchUpdate.return_value.execute.return_value = {"replies": []}

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            client.insert_at("doc123", "Hello", index=5, tab_id="t.1")

            call_kwargs = documents_mock.batchUpdate.call_args
            req = call_kwargs[1]["body"]["requests"][0]["insertText"]
            assert req["location"]["tabId"] == "t.1"
            assert req["location"]["index"] == 5

    def test_insert_at_end_with_tab_id(self, mock_credentials):
        """Should include tabId in endOfSegmentLocation when tab_id is provided."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service
            documents_mock = mock_service.documents.return_value

            documents_mock.batchUpdate.return_value.execute.return_value = {"replies": []}

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            client.insert_at("doc123", "Hello", index=None, tab_id="t.1")

            call_kwargs = documents_mock.batchUpdate.call_args
            req = call_kwargs[1]["body"]["requests"][0]["insertText"]
            assert req["endOfSegmentLocation"]["tabId"] == "t.1"

    def test_update_text_style_with_tab_id(self, mock_credentials):
        """Should include tabId in range when tab_id is provided."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service
            documents_mock = mock_service.documents.return_value

            documents_mock.batchUpdate.return_value.execute.return_value = {"replies": []}

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            client.update_text_style("doc123", 1, 10, bold=True, tab_id="t.1")

            call_kwargs = documents_mock.batchUpdate.call_args
            req = call_kwargs[1]["body"]["requests"][0]["updateTextStyle"]
            assert req["range"]["tabId"] == "t.1"

    def test_insert_table_with_tab_id(self, mock_credentials):
        """Should include tabId in location when tab_id is provided."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service
            documents_mock = mock_service.documents.return_value

            documents_mock.batchUpdate.return_value.execute.return_value = {"replies": []}

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            client.insert_table("doc123", 3, 4, index=5, tab_id="t.1")

            call_kwargs = documents_mock.batchUpdate.call_args
            req = call_kwargs[1]["body"]["requests"][0]["insertTable"]
            assert req["location"]["tabId"] == "t.1"

    def test_update_paragraph_style_with_tab_id(self, mock_credentials):
        """Should include tabId in range when tab_id is provided."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service
            documents_mock = mock_service.documents.return_value

            documents_mock.batchUpdate.return_value.execute.return_value = {"replies": []}

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            client.update_paragraph_style("doc123", 1, 20, heading=2, tab_id="t.1")

            call_kwargs = documents_mock.batchUpdate.call_args
            req = call_kwargs[1]["body"]["requests"][0]["updateParagraphStyle"]
            assert req["range"]["tabId"] == "t.1"

    def test_update_append_with_tab_id(self, mock_credentials):
        """Should include tabId in location when appending with tab_id."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service
            documents_mock = mock_service.documents.return_value
            # Mock get for tab-aware body read
            documents_mock.get.return_value.execute.return_value = {
                "documentId": "doc123",
                "tabs": [{
                    "tabProperties": {"tabId": "t.1"},
                    "documentTab": {"body": {"content": [{"endIndex": 10}]}},
                    "childTabs": [],
                }],
            }
            documents_mock.batchUpdate.return_value.execute.return_value = {"replies": []}

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            client.update("doc123", "New text", mode="append", tab_id="t.1")

            call_kwargs = documents_mock.batchUpdate.call_args
            req = call_kwargs[1]["body"]["requests"][0]["insertText"]
            assert req["location"]["tabId"] == "t.1"

    def test_update_replace_with_tab_id(self, mock_credentials):
        """Should include tabId in range and location when replacing with tab_id."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service
            documents_mock = mock_service.documents.return_value
            documents_mock.get.return_value.execute.return_value = {
                "documentId": "doc123",
                "tabs": [{
                    "tabProperties": {"tabId": "t.1"},
                    "documentTab": {"body": {"content": [{"endIndex": 50}]}},
                    "childTabs": [],
                }],
            }
            documents_mock.batchUpdate.return_value.execute.return_value = {"replies": []}

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            client.update("doc123", "New content", mode="replace", tab_id="t.1")

            call_kwargs = documents_mock.batchUpdate.call_args
            requests = call_kwargs[1]["body"]["requests"]
            # First request: delete range with tabId
            assert requests[0]["deleteContentRange"]["range"]["tabId"] == "t.1"
            # Second request: insert text with tabId
            assert requests[1]["insertText"]["location"]["tabId"] == "t.1"

    def test_update_prepend_with_tab_id(self, mock_credentials):
        """Should include tabId in location when prepending with tab_id."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service
            documents_mock = mock_service.documents.return_value

            documents_mock.batchUpdate.return_value.execute.return_value = {"replies": []}

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            client.update("doc123", "Start text", mode="prepend", tab_id="t.1")

            call_kwargs = documents_mock.batchUpdate.call_args
            req = call_kwargs[1]["body"]["requests"][0]["insertText"]
            assert req["location"]["tabId"] == "t.1"

    def test_find_and_replace_with_tab_id(self, mock_credentials):
        """Should include tabsCriteria when tab_id is provided."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service
            documents_mock = mock_service.documents.return_value

            documents_mock.batchUpdate.return_value.execute.return_value = {
                "replies": [{"replaceAllText": {"occurrencesChanged": 1}}],
            }

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            client.find_and_replace("doc123", "old", "new", tab_id="t.1")

            call_kwargs = documents_mock.batchUpdate.call_args
            req = call_kwargs[1]["body"]["requests"][0]["replaceAllText"]
            assert req["tabsCriteria"]["tabIds"] == ["t.1"]

    def test_write_markdown_with_tab_id(self, mock_credentials):
        """Should pass tab_id through to markdown_to_requests."""
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service
            documents_mock = mock_service.documents.return_value
            # Mock for _get_body with tab
            documents_mock.get.return_value.execute.return_value = {
                "documentId": "doc123",
                "tabs": [{
                    "tabProperties": {"tabId": "t.1"},
                    "documentTab": {"body": {"content": [{"endIndex": 10}]}},
                    "childTabs": [],
                }],
            }
            documents_mock.batchUpdate.return_value.execute.return_value = {"replies": []}

            from desk.services.docs import DocsClient

            client = DocsClient(mock_credentials)
            with patch("desk.services.markdown_to_docs.markdown_to_requests") as mock_m2r:
                mock_m2r.return_value = [{"insertText": {"location": {"index": 9, "tabId": "t.1"}, "text": "hello"}}]
                client.write_markdown("doc123", "hello", tab_id="t.1")
                mock_m2r.assert_called_once_with(
                    "hello", base_index=9, tab_id="t.1", body_paragraph_style=None,
                )


class TestExtractParagraphText:
    """Tests for smart chip rendering in _extract_paragraph_text."""

    def _make_client(self, mock_credentials):
        with patch("desk.services.docs.build") as mock_build:
            mock_build.return_value = MagicMock()
            from desk.services.docs import DocsClient

            return DocsClient(mock_credentials)

    def test_text_run_only(self, mock_credentials):
        """Baseline: textRun elements render as before."""
        client = self._make_client(mock_credentials)
        paragraph = {
            "elements": [{"textRun": {"content": "Hello World\n"}}]
        }
        assert client._extract_paragraph_text(paragraph) == "Hello World\n"

    def test_person_chip_with_name(self, mock_credentials):
        """Person chip with name renders as @Name."""
        client = self._make_client(mock_credentials)
        paragraph = {
            "elements": [
                {"person": {"personProperties": {"name": "Alice", "email": "alice@co.com"}}},
            ]
        }
        assert client._extract_paragraph_text(paragraph) == "@Alice"

    def test_person_chip_email_only(self, mock_credentials):
        """Person chip without name falls back to @email."""
        client = self._make_client(mock_credentials)
        paragraph = {
            "elements": [
                {"person": {"personProperties": {"email": "bob@co.com"}}},
            ]
        }
        assert client._extract_paragraph_text(paragraph) == "@bob@co.com"

    def test_person_chip_no_properties(self, mock_credentials):
        """Person chip with no name or email renders as @someone."""
        client = self._make_client(mock_credentials)
        paragraph = {
            "elements": [
                {"person": {"personProperties": {}}},
            ]
        }
        assert client._extract_paragraph_text(paragraph) == "@someone"

    def test_rich_link_chip_with_title_and_uri(self, mock_credentials):
        """Rich link chip renders as markdown link."""
        client = self._make_client(mock_credentials)
        paragraph = {
            "elements": [
                {
                    "richLink": {
                        "richLinkProperties": {
                            "title": "Meeting Notes",
                            "uri": "https://docs.google.com/document/d/abc",
                        }
                    }
                },
            ]
        }
        result = client._extract_paragraph_text(paragraph)
        assert "[Meeting Notes]" in result
        assert "https://docs.google.com/document/d/abc" in result

    def test_rich_link_chip_uri_only(self, mock_credentials):
        """Rich link chip without title renders as bare URL."""
        client = self._make_client(mock_credentials)
        paragraph = {
            "elements": [
                {"richLink": {"richLinkProperties": {"uri": "https://example.com"}}},
            ]
        }
        assert client._extract_paragraph_text(paragraph) == "https://example.com"

    def test_rich_link_chip_no_uri(self, mock_credentials):
        """Rich link chip with no URI renders as empty."""
        client = self._make_client(mock_credentials)
        paragraph = {
            "elements": [
                {"richLink": {"richLinkProperties": {}}},
            ]
        }
        assert client._extract_paragraph_text(paragraph) == ""

    def test_mixed_elements(self, mock_credentials):
        """Paragraph with text, person, and rich link interleaved."""
        client = self._make_client(mock_credentials)
        paragraph = {
            "elements": [
                {"textRun": {"content": "Meeting with "}},
                {"person": {"personProperties": {"name": "Alice"}}},
                {"textRun": {"content": " about "}},
                {
                    "richLink": {
                        "richLinkProperties": {
                            "title": "Project Plan",
                            "uri": "https://docs.google.com/document/d/xyz",
                        }
                    }
                },
                {"textRun": {"content": "\n"}},
            ]
        }
        result = client._extract_paragraph_text(paragraph)
        assert result.startswith("Meeting with @Alice about ")
        assert "[Project Plan]" in result
        assert result.endswith("\n")


class TestDocsGetTabsCached:
    """Tests for DocsClient.get_tabs_cached caching behavior."""

    def _make_client_with_tabs(self, mock_credentials):
        from desk.services.docs import DocsClient

        patcher = patch("desk.services.docs.build")
        mock_build = patcher.start()
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        documents_mock = mock_service.documents.return_value
        documents_mock.get.return_value.execute.return_value = {
            "documentId": "doc123",
            "tabs": [
                {
                    "tabProperties": {"tabId": "t.0", "title": "Tab 1", "index": 0},
                    "documentTab": {"body": {"content": []}},
                    "childTabs": [],
                },
            ],
        }
        client = DocsClient(mock_credentials)
        return client, documents_mock, patcher

    def test_caches_tabs_within_instance(self, mock_credentials):
        """Repeated calls for the same document should hit the API once."""
        client, documents_mock, patcher = self._make_client_with_tabs(mock_credentials)
        try:
            client.get_tabs_cached("doc123")
            client.get_tabs_cached("doc123")
            client.get_tabs_cached("doc123")
            assert documents_mock.get.call_count == 1
        finally:
            patcher.stop()

    def test_cache_is_per_document(self, mock_credentials):
        """Different document IDs should each trigger a fetch."""
        client, documents_mock, patcher = self._make_client_with_tabs(mock_credentials)
        try:
            client.get_tabs_cached("doc123")
            client.get_tabs_cached("doc456")
            assert documents_mock.get.call_count == 2
        finally:
            patcher.stop()

    def test_add_tab_invalidates_cache(self, mock_credentials):
        """Mutating tabs should drop the cache so the next read sees the new state."""
        client, documents_mock, patcher = self._make_client_with_tabs(mock_credentials)
        try:
            client.get_tabs_cached("doc123")
            documents_mock.batchUpdate.return_value.execute.return_value = {
                "replies": [{
                    "createTab": {
                        "tab": {"tabProperties": {"tabId": "t.new", "title": "New"}},
                    }
                }],
            }
            client.add_tab("doc123", "New")
            client.get_tabs_cached("doc123")
            assert documents_mock.get.call_count == 2
        finally:
            patcher.stop()

    def test_delete_tab_invalidates_cache(self, mock_credentials):
        client, documents_mock, patcher = self._make_client_with_tabs(mock_credentials)
        try:
            client.get_tabs_cached("doc123")
            documents_mock.batchUpdate.return_value.execute.return_value = {}
            client.delete_tab("doc123", "t.0")
            client.get_tabs_cached("doc123")
            assert documents_mock.get.call_count == 2
        finally:
            patcher.stop()

    def test_rename_tab_invalidates_cache(self, mock_credentials):
        client, documents_mock, patcher = self._make_client_with_tabs(mock_credentials)
        try:
            client.get_tabs_cached("doc123")
            documents_mock.batchUpdate.return_value.execute.return_value = {}
            client.rename_tab("doc123", "t.0", "Renamed")
            client.get_tabs_cached("doc123")
            assert documents_mock.get.call_count == 2
        finally:
            patcher.stop()


class TestGetBodyExtent:
    """Tests for DocsClient.get_body_extent (ADR-024)."""

    def test_returns_range_for_non_empty_body(self, mock_credentials):
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service
            documents_mock = mock_service.documents.return_value
            documents_mock.get.return_value.execute.return_value = {
                "body": {
                    "content": [
                        {"endIndex": 1},
                        {"endIndex": 100},
                        {"endIndex": 250},
                    ]
                }
            }

            from desk.services.docs import DocsClient
            client = DocsClient(mock_credentials)
            start, end = client.get_body_extent("doc123")

            assert start == 1
            assert end == 249  # endIndex - 1

    def test_empty_body_returns_zero_width(self, mock_credentials):
        with patch("desk.services.docs.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service
            documents_mock = mock_service.documents.return_value
            documents_mock.get.return_value.execute.return_value = {
                "body": {"content": []}
            }

            from desk.services.docs import DocsClient
            client = DocsClient(mock_credentials)
            start, end = client.get_body_extent("doc123")

            assert (start, end) == (1, 1)
