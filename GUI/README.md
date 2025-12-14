# CNAB Study Quiz (Windows GUI)

A Windows desktop quiz application (PySide6/Qt) backed by an SQLite question database (`cnab_questions.db`).

## Features
- Randomly selects **N** questions per round (optional seed for reproducibility)
- Automatically detects multiple-choice questions (lines like `A - ...`, `B - ...`) and renders them as **radio buttons**
- Uses **free-text input** for non-multiple-choice questions
- Per-question feedback (Correct/Incorrect with color)
- Running “This Round” panel showing results for each answered question
- Round summary with score and a missed-question review pane

## Requirements (source)
- Windows 10/11
- Python 3.10+ recommended

## Run from source
```powershell
cd src
python -m pip install -r ..\requirements.txt
python .\gui_app.py
