# CLAUDE.md — decide

CLI for asking System One decision models (Jev hosted, clef-flash via Ollama)
typed questions about files and text. Stdlib-only Python; keep it that way.

## Layout (`src/decide/`)

| Module | Role |
|---|---|
| `config.py` | `Backend` dataclass + `BACKENDS` registry; loads `~/development/.env`. New backend = new entry. |
| `client.py` | POST `/v1/systemone`, bearer auth, retries on 429/5xx. |
| `questions.py` | `noul` / `choice` / `score` builders; `combine()` merges one question's answers across chunks. |
| `engine.py` | `Engine.run(documents, questions)`: chunk → parallel cached requests → combine. Reuse this for anything new. |
| `files.py` | `discover()`: path expansion, git-aware, **refuses sensitive files** (`SENSITIVE`). |
| `cache.py` | sha256(model, state, questions) → answers JSON in `~/.cache/decide`. |
| `commands/` | Auto-discovered subcommands: module with `HELP`, `configure(parser)`, `run(args, ctx)`. |
| `cli.py` | argparse wiring; `Context` gives commands `.backend`, `.engine`, `.log`. |

## Adding a subcommand

Create `src/decide/commands/<name>.py` with `HELP`, `configure`, `run`; build
`Document`s and a questions dict, call `ctx.engine.run(...)`. Results go to
stdout, progress and cost summaries to stderr (`ctx.log`). Add a test using
`FakeClient` in `tests/test_decide.py`.

## Constraints

- Jev: ~32K tokens of state per request (we chunk at 80K chars), 1–64 questions,
  1,200 req/min. Ollama: text-only bodies > 64 KiB are rejected (we chunk at 48K chars).
- Anything sent to `jev` leaves the machine. Never weaken `files.SENSITIVE`.
- Tests are offline: `PYTHONPATH=src python3 -m unittest discover -s tests`.

## Papercuts log (global, all projects)

`~/development/papercuts.md` is a shared log of anything that has slowed down
development — broken tooling, misleading errors, environment quirks.

- **Check it first when tooling fails mysteriously.** The fix may already be recorded.
- **Append to it when you lose time to a papercut mid-session**, one line, newest at the bottom:
  `- YYYY-MM-DD · symptom · fix · project`
- Keep these same instructions in every `CLAUDE.md` under `~/development`.
