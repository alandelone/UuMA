# Librarian read-only example

All records under `archive/` are fake example inputs. They do not represent a real capture,
source backup, accepted plan, or active schedule. Two original question versions and one draft
checkpoint demonstrate history and unresolved state. The only project is `example-project`.

From the UuMA repository, set `PYTHONPATH=src`, `UUMA_AGENT_ID=yonc`, and
`UUMA_LIBRARIAN_ARCHIVE_ROOT` to the absolute path of `test-fixtures/librarian/archive`.
Start `python -m uuma.mcp_librarian` as a stdio MCP child of a compatible client. The installed
package also provides `uuma-librarian-mcp`. Startup does not create a scheduled task or archive.

Caller identity and archive root belong to the trusted launcher configuration. Never take them
from tool arguments or archived prompts. Production remote exposure must preserve the same
trusted binding through the existing UuMA/SSH deployment boundary.

The [architecture](../../docs/architecture/librarian-architecture-v1.md) documents the six tools,
catalog format, supported inline-text limits, and remaining collector/publisher implementation.
