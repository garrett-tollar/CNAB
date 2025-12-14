"""Core quiz logic (DB loading and grading) shared by CLI/GUI.

Important: This module does not modify stored question/answer verbiage.
"""

from __future__ import annotations

import random
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class QA:
    qnum: int
    question_text: str
    answer_text: str
    answer_value: Optional[str]
    answer_option: Optional[str]


def normalize(s: str) -> str:
    # grading normalization only; does not modify stored data
    return re.sub(r"\s+", " ", (s or "").strip()).lower()


def load_random_questions(db_path: Path, count: int, seed: Optional[int]) -> list[QA]:
    rng = random.Random(seed)

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        total = conn.execute("SELECT COUNT(*) AS c FROM questions").fetchone()["c"]
        if total == 0:
            raise ValueError("Database contains 0 questions.")

        if count > total:
            raise ValueError(f"Requested {count} questions, but database only has {total}.")

        # sample qnums to avoid expensive ORDER BY RANDOM() for larger dbs
        qnums = [r["qnum"] for r in conn.execute("SELECT qnum FROM questions").fetchall()]
        chosen = rng.sample(qnums, count)

        rows = conn.execute(
            f"""
            SELECT qnum, question_text, answer_text, answer_value, answer_option
            FROM questions
            WHERE qnum IN ({",".join("?" for _ in chosen)})
            """,
            chosen,
        ).fetchall()

        # preserve randomized order
        by_qnum = {r["qnum"]: r for r in rows}
        ordered = [by_qnum[n] for n in chosen]

        return [
            QA(
                qnum=r["qnum"],
                question_text=r["question_text"],
                answer_text=r["answer_text"],
                answer_value=r["answer_value"],
                answer_option=r["answer_option"],
            )
            for r in ordered
        ]


def extract_mc_options(question_text: str) -> list[tuple[str, str]]:
    """Extract options from question text lines like:
      A - BOOTP
      B - SMB
      C - DHCP
    Returns: [("A","BOOTP"), ...]
    """
    opts: list[tuple[str, str]] = []
    for line in (question_text or "").splitlines():
        m = re.match(r"^\s*([A-Z])\s*[-–]\s*(.+?)\s*$", line)
        if m:
            opts.append((m.group(1).upper(), m.group(2)))
    return opts


def is_correct(user_answer: str, qa: QA, case_sensitive: bool) -> bool:
    ua = (user_answer or "").strip()
    if not ua:
        return False

    # Accept option letter (e.g., "C") when provided
    if qa.answer_option:
        if ua.strip().upper() == qa.answer_option.upper():
            return True

    # Accept the derived answer value
    if qa.answer_value:
        if case_sensitive:
            if ua.strip() == qa.answer_value.strip():
                return True
        else:
            if normalize(ua) == normalize(qa.answer_value):
                return True

    # Fallback: allow matching within the raw answer text (verbatim) for edge cases
    if case_sensitive:
        return ua in (qa.answer_text or "")
    return normalize(ua) in normalize(qa.answer_text or "")
