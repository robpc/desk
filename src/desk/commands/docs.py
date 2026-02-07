"""Docs commands — read and update Google Docs."""

import json
import sys

import click
from rich.console import Console

from desk.auth import get_credentials
from desk.services.docs import DocsClient

console = Console()


def _get_client() -> DocsClient:
    """Get authenticated Docs client or exit."""
    creds = get_credentials()
    if not creds:
        console.print("[red]Not authenticated.[/red]")
        console.print("Run: [cyan]desk setup[/cyan]")
        sys.exit(1)
    return DocsClient(creds)


@click.group()
def docs() -> None:
    """Google Docs — read and update documents."""
    pass


@docs.command()
@click.argument("title")
@click.option("--body", "-b", default="", help="Initial document content")
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def create(title: str, body: str, quiet: bool, as_json: bool) -> None:
    """Create a new Google Doc.

    Examples:

        desk docs create "Meeting Notes"

        desk docs create "Draft" --body "Hello world"
    """
    client = _get_client()
    result = client.create(title, body=body)

    if as_json:
        print(json.dumps(result, indent=2))
    elif not quiet:
        console.print(f"[green]Created: {result['title']}[/green]")
        if result.get("webViewLink"):
            console.print(f"[dim]{result['webViewLink']}[/dim]")


@docs.command()
@click.argument("document_id")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def read(document_id: str, as_json: bool) -> None:
    """Read a document's content.

    Examples:

        desk docs read <document-id>
    """
    client = _get_client()
    result = client.read(document_id)

    if as_json:
        print(json.dumps(result, indent=2))
        return

    console.print(f"[bold]{result['title']}[/bold]")
    console.print()
    console.print(result["body"])


@docs.command()
@click.argument("document_id")
@click.argument("text")
@click.option(
    "--mode",
    "-m",
    type=click.Choice(["append", "prepend", "replace"]),
    default="append",
    help="Where to insert: append (end), prepend (beginning), replace (all)",
)
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def update(document_id: str, text: str, mode: str, quiet: bool, as_json: bool) -> None:
    """Insert or replace text in a document.

    Examples:

        desk docs update <id> "New text at the end"

        desk docs update <id> "Text at start" --mode prepend

        desk docs update <id> "Replace everything" --mode replace
    """
    client = _get_client()
    result = client.update(document_id, text, mode=mode)

    if as_json:
        print(json.dumps(result, indent=2))
    elif not quiet:
        console.print(f"[green]Updated document ({mode})[/green]")


@docs.command()
@click.argument("document_id")
@click.argument("dest", type=click.Path())
@click.option(
    "--format",
    "-f",
    "fmt",
    type=click.Choice(["pdf", "txt", "docx", "html"]),
    default="pdf",
    help="Export format",
)
@click.option("--quiet", "-q", is_flag=True, help="Suppress success messages")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def export(document_id: str, dest: str, fmt: str, quiet: bool, as_json: bool) -> None:
    """Export a document to a different format.

    Examples:

        desk docs export <id> report.pdf

        desk docs export <id> notes.txt --format txt

        desk docs export <id> doc.docx --format docx
    """
    from pathlib import Path

    client = _get_client()
    content = client.export(document_id, fmt=fmt)

    dest_path = Path(dest)
    if isinstance(content, str):
        dest_path.write_text(content, encoding="utf-8")
    else:
        dest_path.write_bytes(content)

    if as_json:
        out = {"documentId": document_id, "format": fmt, "path": str(dest_path)}
        print(json.dumps(out, indent=2))
    elif not quiet:
        console.print(f"[green]Exported to: {dest_path}[/green]")
