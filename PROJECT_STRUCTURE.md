# Project structure

This document describes repository layout and ownership boundaries only. **Feature status, completion counts and remaining work live exclusively in [project_manifest.json](project_manifest.json)** so the checklist is not copied and allowed to drift across multiple files.

## Repository layout

```text
The-Peak-Adventure-/
├── main.py                    # Telegram bot, HTTP API and application wiring
├── *_system.py                # Game domains and persistence operations
├── postgres_adapter.py        # SQLite/PostgreSQL compatibility boundary
├── item_economy.py            # Equipment catalogue and rarity validation
├── backup_scheduler.py        # Scheduled database backup dispatch
├── db_backup.py               # SQLite backup, verification and restore
├── postgres_backup.py         # PostgreSQL backup, verification and restore
├── offsite_backup.py          # S3-compatible backup export and restore
├── runtime_monitor.py         # Runtime metrics and alert conditions
├── monsters.json              # Monster catalogue and authored lore
├── webapp/                    # Phaser Mini App client and browser assets
├── cloudflare/                # Edge Worker and embedded client assets
├── tests/                     # Python, PostgreSQL and regression tests
├── scripts/                   # Asset sync, migration and launch checks
├── docs/                      # Runbooks, audits and domain references
├── .github/workflows/         # CI workflows
├── project_manifest.json      # Canonical feature checklist and status
├── README.md                  # Setup, commands and operational overview
└── PROJECT_STRUCTURE.md       # This repository layout guide
```

## Architecture and ownership

- **Application entry point:** `main.py` connects Telegram handlers, Mini App HTTP endpoints, authorization, persistence and domain services. Keep domain rules in their existing system modules rather than adding parallel implementations to the entry point.
- **Game domains:** existing `*_system.py` modules own their respective rules and database operations. Extend the owning module and its current tests when adding behavior.
- **Persistence:** `postgres_adapter.py` is the compatibility boundary for SQLite and PostgreSQL. Keep database-specific SQL decisions inside the adapter or the owning module's existing dialect helpers.
- **Mini App:** `webapp/` contains the Phaser client, UI, animation controllers and client-side tests. The backend remains authoritative for player state, combat, inventory and rewards.
- **Edge delivery:** `cloudflare/` contains the Worker and its embedded client assets. Use the existing asset synchronization script to keep deployed assets aligned with `webapp/`.
- **Operations:** backup, monitoring and launch-preflight modules own operational behavior. Runbooks in `docs/` describe safety requirements and explicitly distinguish automated tests from live production validation.
- **Verification:** `tests/` and `.github/workflows/` provide regression and CI coverage. PostgreSQL integration tests require the configured disposable CI database and must never target production.

## Documentation ownership

| File | Single responsibility |
|---|---|
| `README.md` | Installation, player/admin commands, configuration and operational overview |
| `project_manifest.json` | Canonical feature inventory, statuses and completion counts |
| `PROJECT_STRUCTURE.md` | Repository layout, module ownership and maintenance boundaries |
| `docs/` | Focused runbooks, audits, design proposals and domain-specific references |

Do not copy the feature checklist or progress totals into another document. Link to the manifest instead. Keep design proposals clearly labeled as proposals, not implemented behavior.

## Repository maintenance rules

1. Extend an existing module and its existing test file before considering a new file.
2. Merge overlapping documentation only after preserving unique operational instructions and linking every retained reference to the canonical document.
3. Before deleting a file, search imports, workflow references, scripts, documentation links and runtime paths. Remove it only after its behavior and tests have been consolidated.
4. Keep generated or mirrored assets synchronized through the existing scripts; do not hand-maintain duplicate copies.
5. Treat passing CI as automated regression evidence, not proof of live Telegram, mobile-device, production-hosting or real off-site recovery behavior.
6. Never commit credentials or run destructive restore/deployment operations against production.
