# decide

Typed decisions about files and text from a **System One decision model**
(TypeSafe's [Jev](https://jevtypesafeai.com/jev/api) by default, or Ollama's
`clef-flash` locally). The model only answers questions — yes/no, pick one,
or score — so it is cheap and fast, and the files never enter Claude's context.

No dependencies beyond Python 3.11+.

## Install

```sh
~/development/decide/bin/decide --help       # run from the checkout
ln -s ~/development/decide/bin/decide ~/bin/  # or put it on PATH
```

Jev needs `TYPESAFE_API_KEY`, read from the environment or `~/development/.env`.

## triage — which files matter?

```sh
decide triage -q "Does this code refresh OAuth tokens?" src/
decide triage -q "Handles payments?" -q "Writes to the database?" --match all .
decide triage -q "Parses CSV input?" --glob '*.py' --dry-run ~/development/finance
```

Prints matching files, highest P(yes) first. Useful flags: `--threshold`
(default 0.3), `--all` (show every file), `--json`, `--dry-run` (list files and
estimate cost without sending), `--max-files` (default 200).

**Never sent:** `.env*`, keys/certs (`*.pem`, `*.key`, `id_rsa*`, …),
credential files, and anything with `secret` in its name — even if named
explicitly. Directories inside git honour `.gitignore`; elsewhere, `node_modules`,
`venv`, `build`, `dist` and dot-directories are skipped.

## Backends

| | `jev` (default) | `ollama` |
|---|---|---|
| Model | `jev-latest` | `clef-flash` |
| ~31K-token file | ~0.5–1 s | ~150 s |
| Cost | $0.42 / M input tokens | free |
| Code leaves the machine | yes | no |

Choose with `--backend ollama` or `DECIDE_BACKEND=ollama`. Answers are cached in
`~/.cache/decide` by model + questions + exact text, so re-asking about an
unchanged file is free; `--no-cache` bypasses it.

## Notes from benchmarking (Oct 2026)

- Jev separates real hits from clean files well, but at mid-range scores
  (0.5–0.75) it is often flagging something defensible (an unused import, a
  fallback default). Treat 0.3–0.7 as "worth a look", not "yes".
- Use `grep` for anything grep can answer; use `decide` for questions about
  meaning ("does this validate user input?").
- Jev's built-in verdict-style choice questions over-block; derive decisions
  from individual yes/no scores instead.

## Extending

See `CLAUDE.md` for the architecture. A new subcommand is one module in
`src/decide/commands/`; a new backend is one entry in `config.BACKENDS`.

```sh
PYTHONPATH=src python3 -m unittest discover -s tests   # offline, no API calls
```
