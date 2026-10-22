# Forge Lab commands on Hermes

The former AntiGravity bridge's local-command concept now runs inside Hermes
`forge-lab-bot`. AntiGravity Bridge stays disabled, and Hermes remains the sole
Telegram receiver. Commands are registered as a Forge-only plugin, rather than
being sent to a language model.

| Command | Behavior |
| --- | --- |
| `/forge` | Focused hardware-bot guide, showing Hermes as the receiver |
| `/inventory [component ID]` | Event-derived balances, plus separately labeled purchase evidence |
| `/projects [keyword]` | Existing workspace project definitions and separately listed actual Builds |
| `/shortages [project or BOM path]` | Candidate BOM list, or semantic BOM/inventory comparison for a file inside `projects/<project>/bom/` |
| `/worklog [project name]` | Read the latest five recorded lab worklogs; never create a record |
| `/model` | Hermes native session model controls |
| `/cancel`, `/stop` | Hermes native stop for the current task; `/cancel` is a quick alias |
| `/queue list`, `/queue clear` | Hermes native pending-message controls |
| `/new`, `/reset`, `/clear` | Hermes native new-session handling; `/clear` is a quick alias |
| `/help` | Hermes's full command help, including the new plugin commands |

The old bridge's fixed AntiGravity model claims, hardcoded project descriptions,
and generic shortage recommendations were not carried over. Stock is read through
the existing `uuma-worker` semantic tools; purchase evidence does not become stock.
Project definitions do not assert that a physical Build exists, and BOM candidates
do not assert confirmed shortages. Ordinary text, images and voice continue through
the existing Hermes Forge agent and governed recording workflow.

`integrations/hermes/uuma_forge_commands` contains the plugin. The profile grants
only its existing `uuma-worker` server, and each handler checks the current profile.
`scripts/deploy-forge-commands.py` installs it with raw config backups and preserves
the existing model, MCP server definitions and unrelated configuration. The main
`scripts/deploy-hermes.ps1` also installs it when deploying Forge.

Telegram menu priority puts hardware commands first, with a default 24-entry cap;
the complete native command list remains available through `/help`. The separate
`scripts/sync-forge-telegram-menu.py` builds the menu from Hermes's actual registry,
backs up the previous menu, updates default/private/group scopes, and verifies
readback. It never polls updates or sends a chat message.

Verification includes deterministic handler and deployment tests; real Hermes
plugin discovery, actual stdio MCP reads against a fixture database, Telegram menu
generation, native cancel alias resolution and profile A→B→A isolation; plus
Telegram API menu readback. No user lab records are rewritten by this migration.
