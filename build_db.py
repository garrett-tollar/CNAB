#!/usr/bin/env python3
"""
Build an SQLite database from the CNAB Study Questions .docx.

Design intent:
- Preserve question/answer verbiage exactly as it appears in the source document.
- Store a derived "answer_value" and "answer_option" strictly for grading convenience.
"""

from __future__ import annotations

import argparse
import re
import sqlite3
from pathlib import Path

from docx import Document


Q_MARKER_RE = re.compile(r"^Question\s+(?P<num>\d+)\s+of\s+(?P<total>\d+)\s*$", re.IGNORECASE)


def parse_docx(docx_path: Path) -> list[dict]:
    doc = Document(str(docx_path))
    paras = [p.text.rstrip() for p in doc.paragraphs]

    q_indices = [i for i, t in enumerate(paras) if Q_MARKER_RE.match(t.strip())]
    questions: list[dict] = []

    for k, start in enumerate(q_indices):
        end = q_indices[k + 1] if k + 1 < len(q_indices) else len(paras)
        block = paras[start:end]

        m = Q_MARKER_RE.match(block[0].strip())
        if not m:
            continue

        qnum = int(m.group("num"))

        try:
            ans_idx = next(j for j, line in enumerate(block) if "[+] Answer>" in line)
        except StopIteration:
            continue

        q_lines = block[1:ans_idx]

        # The source .docx typically places the answer on the *same line* as the
        # "[+] Answer>" marker (e.g., "[+] Answer>   the correct answer is ...").
        # Preserve the post-marker verbiage exactly, and also capture any
        # subsequent lines (some answers span multiple paragraphs).
        marker_line = block[ans_idx]
        marker = "[+] Answer>"
        post_marker = ""
        if marker in marker_line:
            post_marker = marker_line.split(marker, 1)[1]

        a_lines = []
        if post_marker != "":
            a_lines.append(post_marker)
        a_lines.extend(block[ans_idx + 1 :])

        # stop at separator line of ===== (if present)
        sep_pos = next(
            (j for j, line in enumerate(a_lines) if set(line.strip()) == {"="} and len(line.strip()) > 10),
            None,
        )
        if sep_pos is not None:
            a_lines = a_lines[:sep_pos]

        # trim trailing blank lines
        while q_lines and q_lines[-1].strip() == "":
            q_lines.pop()
        while a_lines and a_lines[-1].strip() == "":
            a_lines.pop()

        question_text = "\n".join(q_lines).strip("\n")
        # raw, unchanged verbiage (do not trim inner whitespace)
        answer_text = "\n".join(a_lines).strip("\n")

        # derive a grading-friendly key without altering stored verbiage
        answer_value = None
        answer_option = None

        for l in a_lines:
            l2 = l.strip()
            mm = re.search(r"the correct answer is\s+(.*)$", l2, flags=re.IGNORECASE)
            if not mm:
                continue

            rest = mm.group(1).strip()

            # Common form: "Frames (C)"
            mopt = re.match(r"^(.*)\s+\(([A-Z])\)\s*$", rest)
            if mopt:
                answer_value = mopt.group(1).strip()
                answer_option = mopt.group(2).strip()
                break

            # Sometimes: "Social Engineering (Social Engineering)"
            mpar = re.match(r"^(.*)\s+\((.*)\)\s*$", rest)
            if mpar:
                left = mpar.group(1).strip()
                right = mpar.group(2).strip()
                answer_value = right if right.lower() == left.lower() else left
                break

            answer_value = rest
            break

        questions.append(
            {
                "qnum": qnum,
                "question_text": question_text,
                "answer_text": answer_text,
                "answer_value": answer_value,
                "answer_option": answer_option,
            }
        )

    return questions


def init_db(db_path: Path) -> None:
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                qnum INTEGER UNIQUE NOT NULL,
                question_text TEXT NOT NULL,
                answer_text TEXT NOT NULL,
                answer_value TEXT,
                answer_option TEXT
            );
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_questions_qnum ON questions(qnum);")
        conn.commit()


def upsert_questions(db_path: Path, questions: list[dict]) -> None:
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.executemany(
            """
            INSERT INTO questions (qnum, question_text, answer_text, answer_value, answer_option)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(qnum) DO UPDATE SET
                question_text=excluded.question_text,
                answer_text=excluded.answer_text,
                answer_value=excluded.answer_value,
                answer_option=excluded.answer_option;
            """,
            [
                (
                    q["qnum"],
                    q["question_text"],
                    q["answer_text"],
                    q.get("answer_value"),
                    q.get("answer_option"),
                )
                for q in questions
            ],
        )
        conn.commit()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--docx", required=True, type=Path, help="Path to the source .docx")
    ap.add_argument("--db", required=True, type=Path, help="Path to output SQLite .db")
    args = ap.parse_args()

    if not args.docx.exists():
        raise SystemExit(f"Docx not found: {args.docx}")

    questions = parse_docx(args.docx)
    if not questions:
        raise SystemExit("No questions were parsed. Check the document formatting.")

    init_db(args.db)
    upsert_questions(args.db, questions)

    print(f"Imported {len(questions)} questions into {args.db}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
