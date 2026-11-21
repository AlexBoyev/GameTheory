"""Write the OpenAPI schema to a file without starting a server.

    uv run python -m app.tools.dump_openapi ../frontend/openapi.json

`npm run gen:api` reads the schema from a running backend, which is the normal
workflow. This exists for the cases where that is awkward - CI, a cold
checkout, or a machine where something else already owns port 8000.
"""

import argparse
import json
from pathlib import Path

from app.main import create_app


def dump(destination: Path) -> int:
    """Write the schema to `destination` and return the byte count."""
    schema = create_app().openapi()
    payload = json.dumps(schema, indent=2, sort_keys=True)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(payload, encoding="utf-8")
    return len(payload)


def main() -> None:
    """Parse arguments and dump the schema."""
    parser = argparse.ArgumentParser(description="Dump the OpenAPI schema to a file")
    parser.add_argument(
        "destination",
        nargs="?",
        default="../frontend/openapi.json",
        type=Path,
        help="Where to write the schema (default: ../frontend/openapi.json)",
    )
    args = parser.parse_args()
    written = dump(args.destination)
    print(f"wrote {written} bytes to {args.destination}")


if __name__ == "__main__":
    main()
