#!/usr/bin/env python3
"""無蝦米開機複習訓練程式。

從 words.txt 加權抽題，用系統的無蝦米輸入法打出中文字作答。
全部答對才能離開；累計答錯達上限（預設 10 次）也可放棄離開。
"""

import json
import random
import time
import tkinter as tk
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
WORDS_FILE = BASE_DIR / "words.txt"
CONFIG_FILE = BASE_DIR / "config.json"
STATS_FILE = BASE_DIR / "stats.json"

DEFAULT_CONFIG = {
    "questions_per_session": 5,
    "max_failures": 3,
    "hint_after_failures": 3,
    "topmost": True,
}


def load_config():
    config = dict(DEFAULT_CONFIG)
    try:
        config.update(json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        pass
    return config


def load_words():
    """讀練習清單，回傳 [(字, 編碼或None), ...]。"""
    words = []
    try:
        lines = WORDS_FILE.read_text(encoding="utf-8").splitlines()
    except OSError:
        return words
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        word = parts[0]
        code = parts[1].upper() if len(parts) > 1 else None
        words.append((word, code))
    return words


def load_stats():
    try:
        return json.loads(STATS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_stats(stats):
    STATS_FILE.write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def pick_questions(words, stats, count):
    """抽題：沒練過的新字一定先排入，剩下名額再加權隨機抽。

    加權抽題時，錯誤率高、久沒練的字權重較高。
    """
    new_words = [item for item in words if not stats.get(item[0], {}).get("attempts")]
    random.shuffle(new_words)
    picked = new_words[:count]
    if len(picked) >= count:
        return picked

    now = time.time()
    weighted = []
    for word, code in words:
        if (word, code) in picked:
            continue
        record = stats.get(word, {})
        attempts = record.get("attempts", 0)
        wrong = record.get("wrong", 0)
        last_seen = record.get("last_seen", 0)
        # 基礎權重 1；錯誤率最多 +4；超過一天沒練，每天 +0.5（上限 +3）
        error_rate = wrong / attempts if attempts else 1.0  # 沒練過視同最需要練
        days_idle = (now - last_seen) / 86400 if last_seen else 7
        weight = 1.0 + error_rate * 4.0 + min(days_idle * 0.5, 3.0)
        weighted.append(((word, code), weight))

    for _ in range(min(count - len(picked), len(weighted))):
        total = sum(w for _, w in weighted)
        r = random.uniform(0, total)
        cursor = 0.0
        for i, (item, w) in enumerate(weighted):
            cursor += w
            if r <= cursor:
                picked.append(item)
                weighted.pop(i)
                break
    random.shuffle(picked)  # 新字不要總是排在最前面
    return picked


class TrainerApp:
    def __init__(self, root, questions, config, stats):
        self.root = root
        self.questions = questions
        self.config = config
        self.stats = stats
        self.index = 0
        self.round = 1
        self.round_wrong = []  # 本輪答錯過的題目，輪末重測
        self.total_failures = 0
        self.current_failures = 0
        self.current_attempts = 0
        self.can_quit = False

        root.title("無蝦米複習")
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        if config["topmost"]:
            root.attributes("-topmost", True)

        self.progress_label = tk.Label(root, font=("sans-serif", 12), fg="#666666")
        self.progress_label.pack(pady=(16, 0))

        self.word_label = tk.Label(root, font=("sans-serif", 72))
        self.word_label.pack(pady=(8, 4))

        self.hint_label = tk.Label(root, font=("sans-serif", 16), fg="#0055aa")
        self.hint_label.pack()

        self.entry = tk.Entry(root, font=("sans-serif", 28), width=12, justify="center")
        self.entry.pack(pady=12)
        self.entry.bind("<Return>", self.check_answer)
        # 防作弊：擋掉各種貼上
        for seq in ("<<Paste>>", "<Control-v>", "<Control-V>", "<Button-2>", "<Shift-Insert>"):
            self.entry.bind(seq, lambda e: "break")

        self.feedback_label = tk.Label(root, font=("sans-serif", 14))
        self.feedback_label.pack()

        self.limit_actions = tk.Frame(root)
        self.review_button = tk.Button(
            self.limit_actions,
            text="複習剛剛打錯的字",
            command=self.review_wrong_questions,
        )
        self.review_button.pack(side=tk.LEFT, padx=4)
        self.quit_button = tk.Button(
            self.limit_actions, text="直接離開", command=self.quit_app
        )
        self.quit_button.pack(side=tk.LEFT, padx=4)

        self.center_window(420, 340)
        self.show_question()
        self.entry.focus_force()

    def center_window(self, width, height):
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() - width) // 2
        y = (self.root.winfo_screenheight() - height) // 2
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    @property
    def current(self):
        return self.questions[self.index]

    def show_question(self):
        word, _ = self.current
        self.current_failures = 0
        self.current_attempts = 0
        round_text = f"第 {self.round} 輪　" if self.round > 1 else ""
        self.progress_label.config(
            text=f"{round_text}第 {self.index + 1} / {len(self.questions)} 題"
        )
        self.word_label.config(text=word, fg="black")
        self.hint_label.config(text="")
        self.feedback_label.config(text="請用無蝦米打出上面的字，按 Enter 送出")
        self.entry.delete(0, tk.END)

    def check_answer(self, _event=None):
        if self.can_quit and self.index >= len(self.questions):
            return
        answer = self.entry.get().strip()
        if not answer:
            return
        word, code = self.current
        self.current_attempts += 1
        if answer == word:
            self.record_result(word, correct=True)
            if code:
                self.feedback_label.config(text=f"答對了！編碼：{code}", fg="#008800")
            else:
                self.feedback_label.config(text="答對了！", fg="#008800")
            self.index += 1
            if self.index >= len(self.questions):
                if self.round_wrong:
                    self.start_retry_round()
                else:
                    self.finish()
            else:
                self.root.after(600, self.show_question)
        else:
            self.total_failures += 1
            self.current_failures += 1
            if self.current not in self.round_wrong:
                self.round_wrong.append(self.current)
            self.entry.delete(0, tk.END)
            remaining = self.config["max_failures"] - self.total_failures
            self.feedback_label.config(
                text=f"答錯了，再試一次（累計錯 {self.total_failures} 次）", fg="#cc0000"
            )
            if code and self.current_failures >= self.config["hint_after_failures"]:
                self.hint_label.config(text=f"提示：{code}")
            if remaining <= 0:
                self.record_result(word, correct=False)
                self.give_up()

    def record_result(self, word, correct):
        record = self.stats.setdefault(word, {"attempts": 0, "wrong": 0, "last_seen": 0})
        record["attempts"] += self.current_attempts
        record["wrong"] += self.current_failures
        record["last_seen"] = time.time()
        save_stats(self.stats)

    def start_retry_round(self):
        """把本輪答錯過的題目再測一輪，直到某一輪完全沒錯。"""
        self.questions = self.round_wrong
        self.round_wrong = []
        self.index = 0
        self.round += 1
        random.shuffle(self.questions)
        self.word_label.config(text="")
        self.feedback_label.config(
            text=f"還有 {len(self.questions)} 個字答錯過，再複習一輪！", fg="#cc6600"
        )
        self.root.after(1200, self.show_question)

    def finish(self):
        self.can_quit = True
        self.word_label.config(text="完成！", fg="#008800")
        self.hint_label.config(text="")
        self.feedback_label.config(text="全部答對，做得好！視窗即將關閉", fg="#008800")
        self.entry.config(state=tk.DISABLED)
        self.root.after(2000, self.quit_app)

    def give_up(self):
        self.can_quit = True
        self.feedback_label.config(
            text=(
                f"已累計答錯 {self.config['max_failures']} 次，"
                "要複習剛剛打錯的字嗎？"
            ),
            fg="#cc0000",
        )
        self.entry.config(state=tk.DISABLED)
        self.limit_actions.pack(pady=8)

    def review_wrong_questions(self):
        """達錯誤上限後，只重新練習剛才答錯過的題目。"""
        self.can_quit = False
        self.total_failures = 0
        self.limit_actions.pack_forget()
        self.entry.config(state=tk.NORMAL)
        self.start_retry_round()

    def on_close(self):
        if self.can_quit:
            self.quit_app()
        # 還沒答完也沒錯滿上限：忽略關閉

    def quit_app(self):
        self.root.destroy()


def main():
    config = load_config()
    words = load_words()
    if not words:
        # 清單是空的就沒東西可練，直接退出（不擋開機）
        print(f"練習清單 {WORDS_FILE} 是空的，請先加入要練的字。")
        return
    stats = load_stats()
    questions = pick_questions(words, stats, config["questions_per_session"])

    root = tk.Tk()
    TrainerApp(root, questions, config, stats)
    root.mainloop()


if __name__ == "__main__":
    main()
