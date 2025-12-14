# CNAB Study Quiz

An interactive study tool for CNAB-style exam preparation, available in both **command-line (CLI)** and **Windows graphical (GUI)** formats.  
The project uses a shared SQLite question database and supports randomized quiz rounds, scoring, and missed-question review.

---

## Project Overview

This repository contains **two implementations** of the same core study system:

- **CLI Version** – lightweight, terminal-based quiz tool for quick study sessions
- **GUI Version** – Windows desktop application with a modern interface and live progress tracking

Both versions:
- Pull questions from the same SQLite question database
- Preserve question and answer verbiage exactly as stored
- Support randomized question selection per round
- Provide scoring and missed-question review

---

## Repository Structure

```
CNAB/
├── CLI/
│   ├── README.md
│   ├── quiz.py
│   ├── build_db.py
│   ├── cnab_questions.db
│   └── requirements.txt
│
├── GUI/
│   ├── README.md
│   ├── requirements.txt
│   └── src/
│       ├── gui_app.py
│       ├── quiz_core.py
│       └── cnab_questions.db
│
└── README.md  (this file)
```

Each subdirectory contains its own README with interface-specific details.

---

## CLI Version (Terminal-Based)

The CLI version is ideal for:
- Fast study sessions
- SSH / remote environments
- Users who prefer keyboard-only workflows

### Key Features
- Random selection of *N* questions per round
- Interactive answer input
- End-of-round score and percentage
- List of missed questions with correct answers

### How to Use
See `CLI/README.md` for:
- Installation instructions
- Database setup
- Example commands
- Available flags and options

---

## GUI Version (Windows Desktop)

The GUI version provides a more visual, user-friendly experience for Windows users.

### Key Features
- Native Windows desktop interface (PySide6 / Qt)
- Automatic detection of multiple-choice vs fill-in questions
- Radio buttons for multiple-choice questions
- Free-text input for fill-in questions
- Live per-question results panel (Correct / Incorrect)
- Automatic progression between questions
- End-of-round summary with detailed missed-question review

### How to Use
See `GUI/README.md` for:
- Running from source
- Using the precompiled Windows executable
- Database placement and selection
- Build instructions (PyInstaller)

---

## Database (`cnab_questions.db`)

- SQLite database containing all study questions and answers
- Shared schema across both CLI and GUI implementations
- Question and answer text is stored **verbatim**
- The database can be:
  - Bundled with the application
  - Placed alongside the executable/script
  - Selected manually via the GUI

> **Note:** Distribution of the database depends on licensing and usage rights.  
> Refer to the subproject README files for details.

---

## Choosing Between CLI and GUI

| Use Case                   | Recommended Version |
|----------------------------|---------------------|
| Quick study session        | CLI                 |
| Remote / SSH environment   | CLI                 |
| Windows desktop use        | GUI                 |
| Visual progress tracking   | GUI                 |
| Keyboard-only workflow     | CLI                 |

You can freely switch between both — they use the same database format.

---

## Development Notes

- Python 3.10+ recommended
- GUI uses **PySide6 (Qt for Python)**
- CLI uses standard Python libraries
- GUI executable built with **PyInstaller**

Each implementation keeps UI logic separate from quiz/database logic to allow future extensions.

---

## Future Enhancements (Planned / Possible)

- Per-topic filtering
- Question tagging and difficulty levels
- Timed quiz mode
- Export missed questions to CSV
- Cross-platform GUI builds
- Automated GitHub Actions builds

---

## License / Usage

This project is intended as a **study aid**.  
Ensure you have the appropriate rights to use and distribute the question content contained in the database.

---

## Author

**Garrett Tollar**  
GitHub: https://github.com/garrett-tollar
