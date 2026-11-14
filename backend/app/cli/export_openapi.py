# backend/app/cli/export_openapi.py
"""Write the OpenAPI document to a file (the frontend generates its client from it).

Usage::

    python -m app.cli.export_openapi ../frontend/openapi.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from app.core.config import Environment, Settings
from app.main import create_app

# Dummy values: exporting the schema never connects to a database or signs tokens.
_EXPORT_SETTINGS = Settings(
    environment=Environment.DEVELOPMENT,
    database_url="postgresql+asyncpg://export:export@localhost/export",
    jwt_secret="x" * 32,
    audit_ip_salt="x" * 32,
    _env_file=None,
)


def main() -> None:
    """Export the OpenAPI JSON to the path given as the first argument."""
    if len(sys.argv) != 2:
        sys.exit("usage: python -m app.cli.export_openapi <output.json>")
    schema = create_app(_EXPORT_SETTINGS).openapi()
    Path(sys.argv[1]).write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
