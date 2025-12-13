# CNAB Study Questions – Interactive Quiz

This package builds an SQLite database from the provided **CNAB Study Questions.docx** and runs interactive quiz rounds from that database.

## Requirements

- Python 3.10+ recommended
- `python-docx`

Install:

```bash
python -m pip install python-docx
```

## Build the database

```bash
python build_db.py --docx "CNAB Study Questions.docx" --db cnab_questions.db
```

## Run a quiz round

Random 25 questions:

```bash
python quiz.py --db cnab_questions.db -n 25
```

Reproducible round (same questions every time):

```bash
python quiz.py --db cnab_questions.db -n 25 --seed 1234
```

Show answer after every question:

```bash
python quiz.py --db cnab_questions.db -n 25 --show-answer
```

## Notes on “no verbiage changes”

- The scripts store **question text** and **answer lines** verbatim from the .docx.
- A derived `answer_value` and `answer_option` are extracted purely for grading convenience.
