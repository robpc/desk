"""Shared console instances.

`error_console` is a stderr-bound Rich console. All failure-path output —
human-readable error messages and structured JSON error envelopes — must go
through it (or `sys.stderr` directly for `print(json.dumps(...))` sites) so
that stdout stays reserved for successful results. See ADR-019.
"""

from rich.console import Console

error_console = Console(stderr=True)
