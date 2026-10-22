#!/usr/bin/env python3
"""Write gitignored .cursor/mcp.json from the example. Does not read the token."""

from pathlib import Path

root = Path(__file__).resolve().parents[1]
example = root / ".cursor" / "mcp.json.example"
target = root / ".cursor" / "mcp.json"
target.write_text(example.read_text())
print(f"Wrote {target}")
