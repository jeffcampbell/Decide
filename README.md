# decide

Ask a cheap, fast decision model typed questions about files and text — yes/no,
pick one, or score — and get back probabilities instead of prose.

`decide` talks to **System One** decision models: TypeSafe's hosted
[Jev](https://jevtypesafeai.com/jev/api) by default, or `clef-flash` running locally
in [Ollama](https://ollama.com). These models only answer questions, so they cost a
fraction of a chat model and reply in about a second.

Two ways to use it:

- **A CLI for coding agents and people.** `decide triage` tells an agent which files
  are worth reading before it reads them, so the rest never enter its context window.
- **A Python library.** Agent frameworks can send cheap yes/no and classification
  decisions to it and save LLM calls for the cases where it's unsure.
  [Yamanote](https://github.com/jeffcampbell/yamanote) uses it this way for triage,
  difficulty routing and log screening.

Pure Python standard library, 3.11+. No dependencies.

## Install

```sh
pip install git+https://github.com/jeffcampbell/Decide.git
decide --help
```

Or run it from a checkout without installing:

```sh
git clone https://github.com/jeffcampbell/Decide.git
Decide/bin/decide --help
```

### API key

Jev needs a TypeSafe API key ([get one here](https://jevtypesafeai.com/jev/api)).
`decide` looks for `TYPESAFE_API_KEY` in the environment, then in a key file:

```sh
mkdir -p ~/.config/decide
echo 'TYPESAFE_API_KEY=...' > ~/.config/decide/env
chmod 600 ~/.config/decide/env
```

The key file is `$XDG_CONFIG_HOME/decide/env` (normally `~/.config/decide/env`), or
whatever `DECIDE_ENV_FILE` points to. The local Ollama backend needs no key.

## `decide triage`: which files matter?

```console
$ decide triage -q "Does this code retry failed HTTP requests?" -q "Does this code write to disk?" src/
columns: [1] Does this code retry failed HTTP requests?  [2] Does this code write to disk?
0.01  0.97  src/decide/cache.py
0.97  0.02  src/decide/client.py
0.04  0.63  src/decide/cli.py
3/11 files matched · 11 requests (0 cached) · 9,230 tokens · $0.0039
```

Every file is asked every question. Matching files are printed to stdout, highest
P(yes) first; progress and the cost summary go to stderr.

```sh
decide triage -q "Handles payments?" -q "Writes to the database?" --match all .
decide triage -q "Parses CSV input?" --glob '*.py' --dry-run ../other-project
decide triage -q "Validates user input?" --json src/ | jq '.files[] | select(.match)'
```

| Flag | |
|---|---|
| `-q`, `--question` | A yes/no question to ask about each file (repeatable) |
| `-t`, `--threshold` | Minimum P(yes) to count as a match (default 0.3: a missed file costs more than an extra one) |
| `--match any\|all` | With several questions, match if any (default) or all are yes |
| `-g`, `--glob` | Only file names matching this glob (repeatable) |
| `--all` | Print every file with its scores, not just matches |
| `--dry-run` | List what would be sent and estimate the cost, without sending anything |
| `--json` | Machine-readable output |
| `--max-files` | Refuse to send more files than this (default 200) |

Global flags go before the subcommand: `--backend jev|ollama`, `--model NAME`,
`--no-cache`.

### Using it from a coding agent

Add something like this to your agent's instructions (`CLAUDE.md`, `AGENTS.md`, …):

> Before reading large or unfamiliar files to find what's relevant, triage first:
> `decide triage -q "Does this code handle session expiry?" src/` — then read only
> the files it prints. Use grep instead when the question is lexical (a name, an
> import, a string); use `decide` for questions about meaning. Scores of 0.3–0.7 mean
> "worth a look", not "yes".

## What gets sent, and what never does

With the `jev` backend, **file contents leave your machine** and go to TypeSafe's API.
Use `--backend ollama` (or `DECIDE_BACKEND=ollama`) for code that must stay local.

These are refused even if you name them explicitly: `.env*`, keys and certificates
(`*.pem`, `*.key`, `*.p12`, `id_rsa*`, `id_ed25519*`, …), `.netrc`, `.npmrc`,
`.pypirc`, `credentials*`, `.git-credentials`, Terraform state, and anything with
`secret` in its name.

When walking a directory inside a git repository, `decide` sends only the files git
would track, so `.gitignore` is respected. Outside git it skips `node_modules`,
virtualenvs, build output and dot-directories. Binary files, empty files and files
over 2 MB are skipped too.

## Backends

| | `jev` (default) | `ollama` |
|---|---|---|
| Model | `jev-latest` | `clef-flash` |
| A ~31K-token file | ~0.5–1 s | ~150 s on a laptop |
| Cost | $0.42 per million input tokens | free |
| Code leaves the machine | yes | no |

Pick one with `--backend` or `DECIDE_BACKEND`. Large files are split on line
boundaries into chunks the backend accepts; a file is a "yes" if any chunk is.

Answers are cached in `~/.cache/decide` (or `DECIDE_CACHE_DIR`), keyed by model,
questions and exact text, so asking again about an unchanged file is free.
`--no-cache` skips the cache.

## Python API

```python
from decide.cache import Cache
from decide.config import get_backend
from decide.engine import Document, Engine
from decide.questions import choice, noul, score, value

engine = Engine(get_backend("jev"), Cache())
questions = {
    "actionable": noul("Is this bug report specific enough to act on?"),
    "area": choice("Which part of the system is affected?",
                   {"api": None, "ui": None, "database": None, "other": None}),
    "difficulty": score("How hard is this to fix?", ["trivial", "small", "medium", "hard"]),
}
[result] = engine.run([Document("issue #42", report_text)], questions)
if result.error:
    ...  # network or API failure: fall back to an LLM
print(value(result.answers["actionable"]))   # 0.85
print(value(result.answers["area"]))         # "api"
print(result.answers["area"]["probabilities"])        # {"api": 1.0, "ui": 0.0, ...}
print(value(result.answers["difficulty"]))   # 0.86: between trivial (0) and small (1)
print(result.answers["difficulty"]["probabilities"])  # {"0": 0.19, "1": 0.77, ...} by level
```

- `noul` is a yes/no question; its value is P(yes).
- `choice` picks one of 2–26 named options and returns a probability for each.
- `score` places the input on an ordered scale of 2–26 levels, lowest first. Its value is the
  expected level index, from 0 (lowest) to the number of levels minus 1;
  `probabilities` gives each level's probability keyed by index, and `legend` maps
  each index to its level name. Round the value to get the most likely level.
- Up to 64 questions go in one request. `Engine.run` takes any number of documents,
  chunks and parallelises the requests, caches them, and merges the answers per
  document.
- `get_backend` raises `SystemExit` when a required key is missing. Catch it if
  `decide` is optional in your program.

## Tips from benchmarking

- Jev separates real hits from clean files well. At mid-range scores (0.5–0.75) it is
  often flagging something defensible, like an unused import or a fallback default.
  Treat 0.3–0.7 as "worth a look", not "yes".
- Use `grep` for anything grep can answer. `decide` is for questions about meaning
  ("does this validate user input?").
- Verdict-style choice questions ("approve / reject / hold") tend to over-block.
  Ask separate yes/no questions and decide from the scores.

## Development

```sh
PYTHONPATH=src python3 -m unittest discover -s tests   # offline; no API calls
```

A new subcommand is one module in `src/decide/commands/` that defines `HELP`,
`configure(parser)` and `run(args, ctx)`; it is picked up automatically. A new
backend is one entry in `config.BACKENDS`: anything that speaks the System One API
(`POST /v1/systemone` with `{model, state, questions}`). See `CLAUDE.md` for the
module layout.

## License

MIT
