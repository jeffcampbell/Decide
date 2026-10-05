"""Builders for the three System One question types, and how to combine a
question's answers across chunks of one document.
"""
from __future__ import annotations


def noul(instructions: str, true: str | None = None, false: str | None = None) -> dict:
    """Yes/no question; answer is P(yes)."""
    q = {"type": "noul", "instructions": instructions}
    if true or false:
        q["criteria"] = {"true": true or "Yes", "false": false or "No"}
    return q


def choice(instructions: str, options: dict[str, str | None]) -> dict:
    """Pick one of 2-26 named options (value = description, or None)."""
    return {"type": "choice", "instructions": instructions, "criteria": options}


def score(instructions: str, levels: list[str]) -> dict:
    """Place the input on an ordered scale of 2-26 levels, lowest first."""
    return {"type": "score", "instructions": instructions, "criteria": levels}


def value(answer: dict) -> float | str:
    """The headline value of one answer: P(yes), chosen option, or level."""
    return answer[answer["type"]]


def combine(answers: list[dict]) -> dict:
    """Merge one question's answers from several chunks of the same document.

    noul:   max P(yes) -- the document says yes if any part does.
    score:  the highest-scoring chunk.
    choice: per option, the max probability over chunks; pick the argmax.
    """
    if len(answers) == 1:
        return answers[0]
    kind = answers[0]["type"]
    if kind == "noul":
        return max(answers, key=lambda a: a["noul"])
    if kind == "score":
        return max(answers, key=lambda a: a["score"])
    if kind == "choice":
        probs: dict[str, float] = {}
        for a in answers:
            for option, p in a.get("probabilities", {}).items():
                probs[option] = max(probs.get(option, 0.0), p)
        best = max(probs, key=probs.get)
        return {"type": "choice", "choice": best, "probabilities": probs, "confidence": probs[best]}
    raise ValueError(f"unknown question type {kind!r}")
