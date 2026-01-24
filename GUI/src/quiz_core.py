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


def _split_csv_list(s: str) -> list[str]:
    return [p.strip() for p in (s or "").split(",") if p.strip()]


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

    # 1) Multiple-choice with stored answer option: grade by option letter only
    if qa.answer_option:
        if ua.upper() == qa.answer_option.strip().upper():
            return True

        # If user answered a single letter (A/B/C/D) and it's wrong, it's wrong.
        if len(ua) == 1 and ua.isalpha():
            return False

        # Treat MC as letter-only when answer_option exists
        return False

    # 2) Fill-in / text-based: grade against derived answer_value (preferred)
    if qa.answer_value:
        # (10) Order-insensitive multi-answer grading for comma-separated values,
        # unless the question explicitly requires ordering (alphabetical / reverse alphabetical).
        qlow = (qa.question_text or "").lower()
        order_required = ("alphabetical order" in qlow) or ("reverse alphabetical" in qlow)

        if (not order_required) and ("," in qa.answer_value) and ("," in ua):
            exp_parts = _split_csv_list(qa.answer_value)
            user_parts = _split_csv_list(ua)

            if case_sensitive:
                if set(user_parts) == set(exp_parts):
                    return True
            else:
                if set(normalize(x) for x in user_parts) == set(normalize(x) for x in exp_parts):
                    return True

        # Default: exact match (with optional normalization)
        if case_sensitive:
            if ua == qa.answer_value.strip():
                return True
        else:
            if normalize(ua) == normalize(qa.answer_value):
                return True

    # 3) Fallback: whole-word/phrase match in answer_text; avoid 1-2 char traps
    at = qa.answer_text or ""
    if case_sensitive:
        if len(ua) < 3:
            return False
        return re.search(rf"\b{re.escape(ua)}\b", at) is not None

    ua_n = normalize(ua)
    at_n = normalize(at)
    if len(ua_n) < 3:
        return False
    return re.search(rf"\b{re.escape(ua_n)}\b", at_n) is not None
