"""Find which files are relevant to a question, without reading them into context.

Every file is asked each --question as a yes/no decision. Files scoring at
or above --threshold are printed, highest first, one per line:

    0.94  src/auth/session.py

Examples:
    decide triage -q "Does this code refresh OAuth tokens?" src/
    decide triage -q "Handles payments?" -q "Writes to the database?" --match all .
    decide triage -q "Parses CSV input?" --glob '*.py' --dry-run ../other-project
"""
from __future__ import annotations

import json

from ..engine import Document
from ..files import discover
from ..questions import noul

HELP = "rank files by relevance to yes/no questions"
CHARS_PER_TOKEN = 3.5  # rough, for the --dry-run estimate


def configure(p):
    p.add_argument("paths", nargs="+", help="files and/or directories (git repos honour .gitignore)")
    p.add_argument("-q", "--question", action="append", required=True,
                   help="yes/no question to ask about each file (repeatable)")
    p.add_argument("-t", "--threshold", type=float, default=0.3,
                   help="minimum P(yes) to count as a match (default 0.3; low, because a missed "
                        "file costs more than an extra one)")
    p.add_argument("--match", choices=["any", "all"], default="any",
                   help="with several questions: match if any (default) or all are yes")
    p.add_argument("-g", "--glob", action="append", help="only file names matching this glob (repeatable)")
    p.add_argument("--all", action="store_true", help="print every file with its scores, not just matches")
    p.add_argument("--max-files", type=int, default=200, help="refuse to send more files than this (default 200)")
    p.add_argument("--dry-run", action="store_true", help="show what would be sent and the estimated cost")
    p.add_argument("--json", action="store_true", help="machine-readable output")


def run(args, ctx) -> int:
    files, skipped = discover(args.paths, args.glob)
    for path, reason in skipped:
        if reason.startswith("sensitive"):
            ctx.log(f"skip {path}: {reason}")
    if not files:
        ctx.log("decide: no text files to check")
        return 1
    if len(files) > args.max_files:
        ctx.log(f"decide: {len(files)} files exceeds --max-files {args.max_files}; narrow the paths or use --glob")
        return 2

    names = [f"q{i}" for i in range(1, len(args.question) + 1)]
    questions = {n: noul(q) for n, q in zip(names, args.question)}
    documents = [Document(str(p), p.read_text(errors="replace")) for p in files]

    backend = ctx.backend
    if args.dry_run:
        jobs = ctx.engine.plan(documents)
        tokens = sum(len(state) for _, state in jobs) / CHARS_PER_TOKEN
        ctx.log(f"would send {len(files)} files as {len(jobs)} requests to {backend.name} ({backend.model}), "
                f"~{tokens:,.0f} input tokens, ~${tokens * backend.usd_per_mtok / 1e6:.3f} before cache hits")
        for p in files:
            print(p)
        return 0

    done = [0]

    def progress(result):
        done[0] += 1
        if len(files) > 5 and done[0] % 10 == 0:
            ctx.log(f"... {done[0]} chunks")

    results = ctx.engine.run(documents, questions, on_done=progress)

    rows = []
    for r in results:
        scores = [r.answers[n]["noul"] for n in names] if r.answers else []
        hit = bool(scores) and (any if args.match == "any" else all)(s >= args.threshold for s in scores)
        rows.append({"path": r.label, "match": hit, "scores": dict(zip(args.question, scores)),
                     "chunks": r.chunks, "error": r.error})
    rows.sort(key=lambda row: max(row["scores"].values(), default=-1), reverse=True)

    if args.json:
        print(json.dumps({"questions": args.question, "threshold": args.threshold, "files": rows}, indent=1))
    else:
        if len(args.question) > 1:
            ctx.log("columns: " + "  ".join(f"[{i}] {q}" for i, q in enumerate(args.question, 1)))
        for row in rows:
            if row["error"] or not (row["match"] or args.all):
                continue
            print("  ".join(f"{s:.2f}" for s in row["scores"].values()) + f"  {row['path']}")

    errors = [r for r in results if r.error]
    for r in errors:
        ctx.log(f"error {r.label}: {r.error}")
    billed = sum(r.input_tokens for r in results)
    cached = sum(r.cached_chunks for r in results)
    matched = sum(row["match"] for row in rows)
    ctx.log(f"{matched}/{len(files)} files matched · {sum(r.chunks for r in results)} requests "
            f"({cached} cached) · {billed:,} tokens · ${billed * backend.usd_per_mtok / 1e6:.4f}")
    return 1 if errors else 0
