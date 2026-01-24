from __future__ import annotations

import random
import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QKeySequence, QShortcut
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
    QProgressBar,
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


def is_multi_select_question(question_text: str) -> bool:
    t = (question_text or "").lower()
    return (
        "pick two" in t
        or "pick 2" in t
        or "choose two" in t
        or "choose 2" in t
        or "select two" in t
        or "select 2" in t
        or "select all that apply" in t
        or "choose all that apply" in t
    )


def _split_csv_list(s: str) -> list[str]:
    return [p.strip() for p in (s or "").split(",") if p.strip()]


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
        self.shuffle_options = QCheckBox("Shuffle multiple-choice options")
        form.addRow("", self.case_sensitive)
        form.addRow("", self.show_answer)
        form.addRow("", self.shuffle_options)

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
            bool(self.shuffle_options.isChecked()),
        )


class QuizPage(QWidget):
    """Quiz page with:
    - (1) in-question highlight of correct/incorrect choices after submit
    - (2) submit disabled until input is valid
    - (3) keyboard shortcuts (Enter to submit, 1-9 to choose/toggle options, Ctrl+F to flag)
    - (7) progress bar
    - (9) randomized option display order (controlled by MainWindow)
    - (5) flag for review
    """

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

        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setMaximumHeight(10)
        layout.addWidget(self.progress_bar)

        self.q_text = QTextEdit()
        self.q_text.setReadOnly(True)
        self.q_text.setMinimumHeight(260)
        layout.addWidget(self.q_text, 1)

        self.answer_box = QGroupBox("Your Answer")
        self.answer_layout = QVBoxLayout(self.answer_box)
        layout.addWidget(self.answer_box)

        self.flag_box = QCheckBox("Flag for review")
        layout.addWidget(self.flag_box)

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
        self._mc_buttons: list[QRadioButton] = []
        self._mc_checks: list[QCheckBox] = []
        self._text_input: Optional[QLineEdit] = None
        self._current_qa: Optional[QA] = None
        self._shuffle_options = False
        self._round_seed: Optional[int] = None

        # Keyboard shortcuts
        QShortcut(QKeySequence(Qt.Key.Key_Return), self, activated=self._submit_clicked)
        QShortcut(QKeySequence(Qt.Key.Key_Enter), self, activated=self._submit_clicked)
        QShortcut(QKeySequence("Ctrl+F"), self, activated=self._toggle_flag)
        for i in range(1, 10):
            QShortcut(QKeySequence(str(i)), self, activated=lambda i=i: self._select_option_by_index(i - 1))

        # initial submit disabled
        self.submit_btn.setEnabled(False)

    def set_round_config(self, *, shuffle_options: bool, seed: Optional[int]):
        self._shuffle_options = bool(shuffle_options)
        self._round_seed = seed

    def reset_round(self):
        self.round_list.clear()

    def append_result(self, q_index: int, correct: bool):
        label = f"Question {q_index}: " + ("Correct" if correct else "Incorrect")
        item = QListWidgetItem(label)
        item.setForeground(Qt.GlobalColor.darkGreen if correct else Qt.GlobalColor.red)
        self.round_list.addItem(item)
        self.round_list.scrollToBottom()

    def is_flagged(self) -> bool:
        return bool(self.flag_box.isChecked())

    def _toggle_flag(self):
        self.flag_box.setChecked(not self.flag_box.isChecked())

    def set_question(self, idx: int, total: int, qa: QA):
        self.progress.setText(f"Question {idx}/{total} (Source question #{qa.qnum})")
        self.progress_bar.setRange(0, max(total, 1))
        self.progress_bar.setValue(idx)
        self.q_text.setPlainText(qa.question_text)
        self.feedback.setText("")
        self.flag_box.setChecked(False)

        self._current_qa = qa

        # clear answer layout
        while self.answer_layout.count():
            item = self.answer_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        # clear input refs
        self._mode = "text"
        self._mc_group = None
        self._mc_buttons = []
        self._mc_checks = []
        self._text_input = None

        options = extract_mc_options(qa.question_text)

        # disable submit until valid
        self.submit_btn.setEnabled(False)

        if options:
            multi = is_multi_select_question(qa.question_text)
            self._mode = "mc_multi" if multi else "mc"

            # deterministic shuffle per round/question, so shortcuts map consistently per question
            opts = list(options)
            if self._shuffle_options:
                base = (self._round_seed or 0)
                rng = random.Random((base * 1_000_003) + int(qa.qnum))
                rng.shuffle(opts)

            if multi:
                for letter, text in opts:
                    cb = QCheckBox(f"{letter} - {text}")
                    cb.setProperty("letter", letter)
                    cb.setProperty("opt_text", text)
                    cb.toggled.connect(self._update_submit_enabled)
                    self._mc_checks.append(cb)
                    self.answer_layout.addWidget(cb)

                hint = QLabel("Select all applicable options, then click Submit.")
                hint.setStyleSheet("color: #666;")
                self.answer_layout.addWidget(hint)
            else:
                self._mc_group = QButtonGroup(self)
                self._mc_group.setExclusive(True)

                for letter, text in opts:
                    rb = QRadioButton(f"{letter} - {text}")
                    rb.setProperty("letter", letter)
                    rb.setProperty("opt_text", text)
                    rb.toggled.connect(self._update_submit_enabled)
                    self._mc_group.addButton(rb)
                    self._mc_buttons.append(rb)
                    self.answer_layout.addWidget(rb)

                hint = QLabel("Select one option, then click Submit.")
                hint.setStyleSheet("color: #666;")
                self.answer_layout.addWidget(hint)

            self._update_submit_enabled()
        else:
            self._mode = "text"
            self._text_input = QLineEdit()
            self._text_input.setPlaceholderText("Type your answer…")
            self._text_input.textChanged.connect(self._update_submit_enabled)
            self._text_input.returnPressed.connect(self._submit_clicked)
            self.answer_layout.addWidget(self._text_input)

            hint = QLabel("Fill-in questions are graded against the stored answer (case handling is a setting).")
            hint.setStyleSheet("color: #666;")
            self.answer_layout.addWidget(hint)

            self._update_submit_enabled()

    def _select_option_by_index(self, idx0: int):
        # 1–9 shortcut: select by display index for current question
        if self._mode == "mc" and 0 <= idx0 < len(self._mc_buttons):
            self._mc_buttons[idx0].setChecked(True)
            return
        if self._mode == "mc_multi" and 0 <= idx0 < len(self._mc_checks):
            self._mc_checks[idx0].toggle()
            return

    def _update_submit_enabled(self):
        enabled = False
        if self._mode == "mc" and self._mc_group:
            enabled = self._mc_group.checkedButton() is not None
        elif self._mode == "mc_multi":
            enabled = any(cb.isChecked() for cb in self._mc_checks)
        else:
            enabled = bool(self._text_input and self._text_input.text().strip())
        self.submit_btn.setEnabled(enabled)

    def _expected_mc_texts(self) -> set[str]:
        """Return expected option text values for the current question when possible."""
        qa = self._current_qa
        if not qa:
            return set()
        if qa.answer_value and "," in qa.answer_value:
            return set(_split_csv_list(qa.answer_value))
        if qa.answer_value and qa.answer_value.strip():
            return {qa.answer_value.strip()}
        return set()

    def get_user_answer(self) -> str:
        # Single-select multiple choice
        if self._mode == "mc" and self._mc_group:
            btn = self._mc_group.checkedButton()
            if not btn:
                return ""

            qa = self._current_qa
            if qa and qa.answer_option:
                return str(btn.property("letter") or "").strip()

            return str(btn.property("opt_text") or "").strip()

        # Multi-select multiple choice (submit option text list)
        if self._mode == "mc_multi":
            picked = [
                (
                    str(cb.property("letter") or "").strip(),
                    str(cb.property("opt_text") or "").strip(),
                )
                for cb in self._mc_checks
                if cb.isChecked()
            ]
            if not picked:
                return ""

            qtxt = (self._current_qa.question_text if self._current_qa else "") or ""
            qlow = qtxt.lower()

            if "reverse alphabetical" in qlow:
                picked.sort(key=lambda t: t[1].lower(), reverse=True)
            elif "alphabetical order" in qlow:
                picked.sort(key=lambda t: t[1].lower())
            else:
                picked.sort(key=lambda t: t[0].upper())

            return ", ".join(text for _letter, text in picked)

        # Free-text / fill-in
        if self._text_input:
            return self._text_input.text().strip()
        return ""

    def _set_widgets_enabled(self, enabled: bool):
        for rb in self._mc_buttons:
            rb.setEnabled(enabled)
        for cb in self._mc_checks:
            cb.setEnabled(enabled)
        if self._text_input:
            self._text_input.setEnabled(enabled)

    def _clear_option_styles(self):
        for rb in self._mc_buttons:
            rb.setStyleSheet("")
        for cb in self._mc_checks:
            cb.setStyleSheet("")

    def highlight_answers(self, correct: bool):
        """Highlight correct choice(s) and user's incorrect selection(s)."""
        self._clear_option_styles()
        qa = self._current_qa
        if not qa:
            return

        # Multi-select highlighting
        if self._mode == "mc_multi":
            expected = self._expected_mc_texts()
            expected_norm = {e.strip().lower() for e in expected}
            for cb in self._mc_checks:
                t = str(cb.property("opt_text") or "").strip()
                if t.strip().lower() in expected_norm:
                    cb.setStyleSheet("color: #0a7a0a; font-weight: 600;")
                elif cb.isChecked():
                    cb.setStyleSheet("color: #b00020; font-weight: 600;")
            return

        # Single-select multiple choice highlighting
        if self._mode == "mc" and self._mc_group:
            selected = self._mc_group.checkedButton()
            if qa.answer_option:
                expected_letter = qa.answer_option.strip().upper()
                for rb in self._mc_buttons:
                    if str(rb.property("letter") or "").strip().upper() == expected_letter:
                        rb.setStyleSheet("color: #0a7a0a; font-weight: 600;")
                if selected and not correct:
                    selected.setStyleSheet("color: #b00020; font-weight: 600;")
                return

            # answer_option missing -> match by answer_value against option text
            expected = self._expected_mc_texts()
            expected_norm = {e.strip().lower() for e in expected}
            for rb in self._mc_buttons:
                t = str(rb.property("opt_text") or "").strip()
                if t.strip().lower() in expected_norm:
                    rb.setStyleSheet("color: #0a7a0a; font-weight: 600;")
            if selected and not correct:
                selected.setStyleSheet("color: #b00020; font-weight: 600;")
            return

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
        # Guard against shortcut firing when disabled
        if not self.submit_btn.isEnabled():
            return
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
        lyt.addWidget(QLabel("Questions (this round)"))
        self.q_list = QListWidget()
        lyt.addWidget(self.q_list, 1)
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

        self.q_list.currentItemChanged.connect(self._on_selected)
        self._payload: list[dict] = []

    def set_results(self, correct_count: int, total: int, payload: list[dict]):
        pct = (correct_count / total) * 100 if total else 0.0
        self.summary.setText(
            f"<b>Correct:</b> {correct_count}/{total}<br>"
            f"<b>Score:</b> {pct:.2f}%"
        )

        self._payload = payload
        self.q_list.clear()
        self.details.clear()

        if not payload:
            self.q_list.addItem(QListWidgetItem("No questions."))
            self.q_list.setEnabled(False)
            self.details.setPlainText("No questions in this round.")
            return

        self.q_list.setEnabled(True)
        for m in payload:
            is_ok = bool(m.get("correct", False))
            flagged = bool(m.get("flagged", False))
            prefix = "★ " if flagged else ""
            item = QListWidgetItem(f"{prefix}#{m['qnum']}")
            item.setForeground(Qt.GlobalColor.darkGreen if is_ok else Qt.GlobalColor.red)
            self.q_list.addItem(item)

        self.q_list.setCurrentRow(0)

    def _on_selected(self, current, _prev):
        if not current or not self._payload:
            return
        idx = self.q_list.currentRow()
        if idx < 0 or idx >= len(self._payload):
            return

        m = self._payload[idx]
        is_ok = bool(m.get("correct", False))
        flagged = bool(m.get("flagged", False))

        status = (
            '<span style="color:#0a7a0a; font-weight:600;">CORRECT</span>'
            if is_ok
            else '<span style="color:#b00020; font-weight:600;">INCORRECT</span>'
        )
        flag_txt = '<span style="color:#333; font-weight:600;"> — FLAGGED</span>' if flagged else ""
        your_color = "#0a7a0a" if is_ok else "#b00020"

        qnum = escape_html(str(m.get("qnum", "")))
        qtxt = escape_html(m.get("question_text", "") or "")
        ua = escape_html(repr(m.get("user_answer", "")))
        ans = escape_html(m.get("answer_text", "") or "")

        html = f"""
        <div>
          <div style="margin-bottom:8px;"><b>Source question #{qnum}</b> — {status}{flag_txt}</div>
          <pre style="white-space:pre-wrap; font-family:Segoe UI, Consolas, monospace;">{qtxt}</pre>
          <div style="margin-top:10px;">
            <b>Your answer:</b> <span style="color:{your_color}; font-weight:600;">{ua}</span>
          </div>
          <div style="margin-top:8px;">
            <b>Answer:</b><br>
            <span style="color:#0a7a0a; font-weight:600;">{ans}</span>
          </div>
        </div>
        """
        self.details.setHtml(html)


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
        self._shuffle_options = False
        self._seed: Optional[int] = None

        # Store per-question results, including flagged
        self._results: list[tuple[QA, str, bool, bool]] = []
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

    def start_round(
        self,
        db_path: Path,
        count: int,
        seed: Optional[int],
        case_sensitive: bool,
        always_show_answer: bool,
        shuffle_options: bool,
    ):
        if not db_path.exists():
            QMessageBox.warning(self, "Database", f"DB not found:\n{db_path}")
            return

        try:
            self._qas = load_random_questions(db_path, count, seed)
        except Exception as e:
            QMessageBox.critical(self, "Load Questions Failed", str(e))
            return

        self._idx = 0
        self._seed = seed
        self._case_sensitive = case_sensitive
        self._always_show_answer = always_show_answer
        self._shuffle_options = shuffle_options
        self._results = []

        self.quiz_page.set_round_config(shuffle_options=shuffle_options, seed=seed)

        self.stack.setCurrentWidget(self.quiz_page)
        self.quiz_page.reset_round()
        self._show_question()

    def _show_question(self):
        qa = self._qas[self._idx]
        self.quiz_page.set_question(self._idx + 1, len(self._qas), qa)

    def submit_current(self, user_answer: str):
        qa = self._qas[self._idx]
        flagged = self.quiz_page.is_flagged()

        correct = is_correct(user_answer, qa, self._case_sensitive)
        self._results.append((qa, user_answer, correct, flagged))

        # Highlight immediately in-question
        self.quiz_page.highlight_answers(correct)

        # Disable inputs and submit while showing feedback, then advance
        self.quiz_page._set_widgets_enabled(False)
        self.quiz_page.submit_btn.setEnabled(False)

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
        correct_count = sum(1 for _, _, c, _ in self._results if c)
        total = len(self._results)

        review = [
            {
                "qnum": qa.qnum,
                "question_text": qa.question_text,
                "user_answer": ua,
                "answer_text": qa.answer_text,
                "correct": c,
                "flagged": flagged,
            }
            for qa, ua, c, flagged in self._results
        ]

        self.results_page.set_results(correct_count, total, review)
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
