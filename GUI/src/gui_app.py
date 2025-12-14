from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from quiz_core import QA, extract_mc_options, is_correct, load_random_questions


def escape_html(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class StartPage(QWidget):
    def __init__(self, on_start, on_pick_db):
        super().__init__()
        self.on_start = on_start
        self.on_pick_db = on_pick_db

        layout = QVBoxLayout(self)

        title = QLabel("CNAB Study Quiz")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        layout.addWidget(title)

        form = QFormLayout()

        default_db = Path.cwd() / "cnab_questions.db"
        self.db_path = QLineEdit()
        if default_db.exists():
            self.db_path.setText(str(default_db))
        else:
            self.db_path.setPlaceholderText("Select cnab_questions.db ...")


        pick = QPushButton("Browse...")
        pick.clicked.connect(self._pick_db_clicked)

        row = QHBoxLayout()
        row.addWidget(self.db_path, 1)
        row.addWidget(pick)
        form.addRow("Database:", row)

        self.count = QSpinBox()
        self.count.setRange(1, 5000)
        self.count.setValue(25)
        form.addRow("Questions this round:", self.count)

        self.seed = QLineEdit()
        self.seed.setPlaceholderText("Optional (e.g., 1234)")
        form.addRow("Seed (optional):", self.seed)

        self.case_sensitive = QCheckBox("Case-sensitive grading")
        self.show_answer = QCheckBox("Always show correct answer after submit")
        form.addRow("", self.case_sensitive)
        form.addRow("", self.show_answer)

        layout.addLayout(form)

        btn_row = QHBoxLayout()
        self.start_btn = QPushButton("Start")
        self.start_btn.clicked.connect(self._start_clicked)
        btn_row.addStretch(1)
        btn_row.addWidget(self.start_btn)
        layout.addLayout(btn_row)

        layout.addStretch(1)

    def _pick_db_clicked(self):
        p = self.on_pick_db()
        if p:
            self.db_path.setText(str(p))

    def _start_clicked(self):
        db = self.db_path.text().strip()
        if not db:
            QMessageBox.warning(self, "Missing database", "Please select cnab_questions.db.")
            return

        seed_text = self.seed.text().strip()
        seed_val = None
        if seed_text:
            try:
                seed_val = int(seed_text)
            except ValueError:
                QMessageBox.warning(self, "Seed", "Seed must be an integer.")
                return

        self.on_start(
            Path(db),
            int(self.count.value()),
            seed_val,
            bool(self.case_sensitive.isChecked()),
            bool(self.show_answer.isChecked()),
        )


class QuizPage(QWidget):
    def __init__(self, on_submit, on_quit):
        super().__init__()
        self.on_submit = on_submit
        self.on_quit = on_quit

        root = QVBoxLayout(self)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter, 1)

        # Left: question/answer
        left = QWidget()
        layout = QVBoxLayout(left)

        self.progress = QLabel("Question 0/0")
        self.progress.setFont(QFont("Segoe UI", 11, QFont.Weight.DemiBold))
        layout.addWidget(self.progress)

        self.q_text = QTextEdit()
        self.q_text.setReadOnly(True)
        self.q_text.setMinimumHeight(260)
        layout.addWidget(self.q_text, 1)

        self.answer_box = QGroupBox("Your Answer")
        self.answer_layout = QVBoxLayout(self.answer_box)
        layout.addWidget(self.answer_box)

        self.feedback = QLabel("")
        self.feedback.setTextFormat(Qt.TextFormat.RichText)
        self.feedback.setWordWrap(True)
        layout.addWidget(self.feedback)

        btns = QHBoxLayout()
        self.submit_btn = QPushButton("Submit")
        self.submit_btn.clicked.connect(self._submit_clicked)
        self.quit_btn = QPushButton("Quit Round")
        self.quit_btn.clicked.connect(self.on_quit)
        btns.addStretch(1)
        btns.addWidget(self.quit_btn)
        btns.addWidget(self.submit_btn)
        layout.addLayout(btns)

        splitter.addWidget(left)

        # Right: running round results
        right = QWidget()
        rlayout = QVBoxLayout(right)

        hdr = QLabel("This Round")
        hdr.setFont(QFont("Segoe UI", 11, QFont.Weight.DemiBold))
        rlayout.addWidget(hdr)

        self.round_list = QListWidget()
        rlayout.addWidget(self.round_list, 1)

        hint = QLabel("Per-question results (green=correct, red=incorrect).")
        hint.setStyleSheet("color: #666;")
        rlayout.addWidget(hint)

        splitter.addWidget(right)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        # input state
        self._mode = "text"
        self._mc_group: Optional[QButtonGroup] = None
        self._text_input: Optional[QLineEdit] = None

    def reset_round(self):
        self.round_list.clear()

    def append_result(self, q_index: int, correct: bool):
        label = f"Question {q_index}: " + ("Correct" if correct else "Incorrect")
        item = QListWidgetItem(label)
        item.setForeground(Qt.GlobalColor.darkGreen if correct else Qt.GlobalColor.red)
        self.round_list.addItem(item)
        self.round_list.scrollToBottom()

    def set_question(self, idx: int, total: int, qa: QA):
        self.progress.setText(f"Question {idx}/{total} (Source question #{qa.qnum})")
        self.q_text.setPlainText(qa.question_text)
        self.feedback.setText("")

        # clear answer layout
        while self.answer_layout.count():
            item = self.answer_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        options = extract_mc_options(qa.question_text)

        if options:
            self._mode = "mc"
            self._mc_group = QButtonGroup(self)
            self._mc_group.setExclusive(True)
            self._text_input = None

            for letter, text in options:
                rb = QRadioButton(f"{letter} - {text}")
                rb.setProperty("letter", letter)
                self._mc_group.addButton(rb)
                self.answer_layout.addWidget(rb)

            hint = QLabel("Select one option, then click Submit.")
            hint.setStyleSheet("color: #666;")
            self.answer_layout.addWidget(hint)
        else:
            self._mode = "text"
            self._mc_group = None

            self._text_input = QLineEdit()
            self._text_input.setPlaceholderText("Type your answer…")
            self._text_input.returnPressed.connect(self._submit_clicked)
            self.answer_layout.addWidget(self._text_input)

            hint = QLabel("Fill-in questions are graded against the stored answer (case handling is a setting).")
            hint.setStyleSheet("color: #666;")
            self.answer_layout.addWidget(hint)

    def get_user_answer(self) -> str:
        if self._mode == "mc" and self._mc_group:
            btn = self._mc_group.checkedButton()
            if not btn:
                return ""
            return str(btn.property("letter") or "").strip()
        if self._text_input:
            return self._text_input.text().strip()
        return ""

    def set_feedback(self, correct: bool, answer_text: str, show_answer: bool):
        if correct:
            msg = '<span style="color:#0a7a0a; font-weight:600;">Result: CORRECT</span>'
        else:
            msg = '<span style="color:#b00020; font-weight:600;">Result: INCORRECT</span>'

        if show_answer:
            msg += (
                '<br><br><span style="color:#0a7a0a; font-weight:600;">[+] Answer&gt;</span><br>'
                f'<span style="color:#0a7a0a;">{escape_html(answer_text)}</span>'
            )

        self.feedback.setText(msg)

    def _submit_clicked(self):
        self.on_submit(self.get_user_answer())


class ResultsPage(QWidget):
    def __init__(self, on_back_to_start):
        super().__init__()
        self.on_back_to_start = on_back_to_start

        layout = QVBoxLayout(self)

        title = QLabel("Round Summary")
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        layout.addWidget(title)

        self.summary = QLabel("")
        self.summary.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(self.summary)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter, 1)

        left = QWidget()
        lyt = QVBoxLayout(left)
        lyt.addWidget(QLabel("Missed Questions"))
        self.missed_list = QListWidget()
        lyt.addWidget(self.missed_list, 1)
        splitter.addWidget(left)

        right = QWidget()
        ryt = QVBoxLayout(right)
        ryt.addWidget(QLabel("Details"))
        self.details = QTextEdit()
        self.details.setReadOnly(True)
        ryt.addWidget(self.details, 1)
        splitter.addWidget(right)
        splitter.setStretchFactor(1, 2)

        btn_row = QHBoxLayout()
        back = QPushButton("Back to Start")
        back.clicked.connect(self.on_back_to_start)
        btn_row.addStretch(1)
        btn_row.addWidget(back)
        layout.addLayout(btn_row)

        self.missed_list.currentItemChanged.connect(self._on_missed_selected)
        self._missed_payload: list[dict] = []

    def set_results(self, correct_count: int, total: int, missed_payload: list[dict]):
        pct = (correct_count / total) * 100 if total else 0.0
        self.summary.setText(
            f"<b>Correct:</b> {correct_count}/{total}<br>"
            f"<b>Score:</b> {pct:.2f}%"
        )

        self._missed_payload = missed_payload
        self.missed_list.clear()
        self.details.clear()

        if not missed_payload:
            self.missed_list.addItem(QListWidgetItem("No missed questions."))
            self.missed_list.setEnabled(False)
            self.details.setPlainText("Nice work. No missed questions this round.")
            return

        self.missed_list.setEnabled(True)
        for m in missed_payload:
            self.missed_list.addItem(QListWidgetItem(f"#{m['qnum']}"))

        self.missed_list.setCurrentRow(0)

    def _on_missed_selected(self, current, _prev):
        if not current or not self._missed_payload:
            return
        idx = self.missed_list.currentRow()
        if idx < 0 or idx >= len(self._missed_payload):
            return
        m = self._missed_payload[idx]
        txt = (
            f"Source question #{m['qnum']}\n\n"
            f"{m['question_text']}\n\n"
            f"Your answer: {m['user_answer']!r}\n\n"
            f"[+] Answer>\n{m['answer_text']}\n"
        )
        self.details.setPlainText(txt)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CNAB Study Quiz")
        self.resize(980, 720)

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self._qas: list[QA] = []
        self._idx = 0
        self._case_sensitive = False
        self._always_show_answer = False
        self._results: list[tuple[QA, str, bool]] = []
        self._advance_delay_ms = 600

        self.start_page = StartPage(self.start_round, self.pick_db)
        self.quiz_page = QuizPage(self.submit_current, self.quit_round)
        self.results_page = ResultsPage(self.back_to_start)

        self.stack.addWidget(self.start_page)
        self.stack.addWidget(self.quiz_page)
        self.stack.addWidget(self.results_page)

    def pick_db(self) -> Optional[Path]:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select cnab_questions.db",
            "",
            "SQLite DB (*.db *.sqlite *.sqlite3);;All files (*.*)",
        )
        return Path(path) if path else None

    def start_round(self, db_path: Path, count: int, seed: Optional[int], case_sensitive: bool, always_show_answer: bool):
        if not db_path.exists():
            QMessageBox.warning(self, "Database", f"DB not found:\n{db_path}")
            return

        try:
            self._qas = load_random_questions(db_path, count, seed)
        except Exception as e:
            QMessageBox.critical(self, "Load Questions Failed", str(e))
            return

        self._idx = 0
        self._case_sensitive = case_sensitive
        self._always_show_answer = always_show_answer
        self._results = []

        self.stack.setCurrentWidget(self.quiz_page)
        self.quiz_page.reset_round()
        self._show_question()

    def _show_question(self):
        qa = self._qas[self._idx]
        self.quiz_page.set_question(self._idx + 1, len(self._qas), qa)

    def submit_current(self, user_answer: str):
        qa = self._qas[self._idx]
        correct = is_correct(user_answer, qa, self._case_sensitive)
        self._results.append((qa, user_answer, correct))

        self.quiz_page.append_result(self._idx + 1, correct)

        show_answer_now = self._always_show_answer or (not correct)
        self.quiz_page.set_feedback(correct, qa.answer_text, show_answer_now)

        if self._idx + 1 >= len(self._qas):
            QTimer.singleShot(self._advance_delay_ms, self.finish_round)
            return

        def _advance():
            self._idx += 1
            self._show_question()

        QTimer.singleShot(self._advance_delay_ms, _advance)

    def finish_round(self):
        correct_count = sum(1 for _, _, c in self._results if c)
        total = len(self._results)
        missed = [
            {
                "qnum": qa.qnum,
                "question_text": qa.question_text,
                "user_answer": ua,
                "answer_text": qa.answer_text,
            }
            for qa, ua, c in self._results
            if not c
        ]
        self.results_page.set_results(correct_count, total, missed)
        self.stack.setCurrentWidget(self.results_page)

    def quit_round(self):
        if QMessageBox.question(self, "Quit", "Quit the current round?") == QMessageBox.StandardButton.Yes:
            self.back_to_start()

    def back_to_start(self):
        self._qas = []
        self._results = []
        self._idx = 0
        self.stack.setCurrentWidget(self.start_page)


def main() -> int:
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
