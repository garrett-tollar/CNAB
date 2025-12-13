#!/usr/bin/env python3
"""
Interactive quiz runner for the CNAB Study Questions database.

Behavior:
- Randomly selects N questions from the database.
- Prompts the user for an answer per question.
- Reports score and missed questions at the end.

Important: Question/answer verbiage shown is stored verbatim from the source document.
"""

from __future__ import annotations

import argparse
import random
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


from colorama import Fore, Style, init as colorama_init

colorama_init(autoreset=True)


@dataclass
class QA:
    qnum: int
    question_text: str
    answer_text: str
    answer_value: Optional[str]
    answer_option: Optional[str]


def normalize(s: str) -> str:
    # grading normalization only; does not modify stored data
    return re.sub(r"\s+", " ", s.strip()).lower()


def load_random_questions(db_path: Path, count: int, seed: Optional[int]) -> list[QA]:
    rng = random.Random(seed)

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        total = conn.execute("SELECT COUNT(*) AS c FROM questions").fetchone()["c"]
        if total == 0:
            raise SystemExit("Database contains 0 questions.")

        if count > total:
            raise SystemExit(f"Requested {count} questions, but database only has {total}.")

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


def is_correct(user_answer: str, qa: QA, case_sensitive: bool) -> bool:
    ua = user_answer.strip()
    if not ua:
        return False

    # Accept option letter (e.g., "C") when provided
    if qa.answer_option:
        if (ua.strip().upper() == qa.answer_option.upper()):
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
        return ua in qa.answer_text
    return normalize(ua) in normalize(qa.answer_text)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, type=Path, help="SQLite database file")
    ap.add_argument("-n", "--count", type=int, default=25, help="Number of random questions")
    ap.add_argument("--seed", type=int, default=None, help="Seed for reproducible randomness")
    ap.add_argument("--show-answer", action="store_true", help="Show the correct answer after each question")
    ap.add_argument("--case-sensitive", action="store_true", help="Use case-sensitive grading")
    args = ap.parse_args()

    if not args.db.exists():
        raise SystemExit(f"DB not found: {args.db}")

    qas = load_random_questions(args.db, args.count, args.seed)

    results = []  # list of (QA, user_answer, correct_bool)

    print(f"Loaded {len(qas)} questions. Type your answer and press Enter.\n")

    for idx, qa in enumerate(qas, start=1):
        print("=" * 80)
        print(f"Question {idx}/{len(qas)} (Source question #{qa.qnum})")
        print()
        print(qa.question_text)
        print()
        ua = input("Your answer> ")
        correct = is_correct(ua, qa, args.case_sensitive)
        results.append((qa, ua, correct))

        if args.show_answer or not correct:
            print()
            print(f"{Fore.GREEN}[+] Answer>{Style.RESET_ALL}")
            print(f"{Fore.GREEN}{qa.answer_text}{Style.RESET_ALL}")

        print(f"\n{Fore.GREEN if correct else Fore.RED}Result: {'CORRECT' if correct else 'INCORRECT'}{Style.RESET_ALL}\n")

    correct_count = sum(1 for _, _, c in results if c)
    total = len(results)
    pct = (correct_count / total) * 100 if total else 0.0

    missed = [(qa, ua) for qa, ua, c in results if not c]

    print("=" * 80)
    print("Round Summary")
    print(f"Correct: {correct_count}/{total}")
    print(f"Score: {pct:.2f}%")

    if missed:
        print("\nMissed Questions:")
        for qa, ua in missed:
            print("-" * 80)
            print(f"Source question #{qa.qnum}")
            print(qa.question_text)
            print(f"{Fore.RED}\nYour answer: {ua!r}{Style.RESET_ALL}")
            print(f"{Fore.GREEN}[+] Answer>{Style.RESET_ALL}")
            print(f"{Fore.GREEN}{qa.answer_text}{Style.RESET_ALL}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
