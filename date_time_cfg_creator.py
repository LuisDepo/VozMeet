#!/usr/bin/env python3
"""
date_time.cfg Creator — Mac/Linux/Windows compatible.
Recreates the original Windows VB6 utility.
Writes the current date and time to date_time.cfg in the same directory.
"""

import os
import sys
import tkinter as tk
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(sys.argv[0]))
CFG_PATH = os.path.join(SCRIPT_DIR, "date_time.cfg")
UPDATE_INTERVAL_MS = 1000


class DateTimeCfgCreator:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("date_time.cfg Creator")
        self.root.resizable(False, False)

        self.running = False
        self.timer_id = None

        frame = tk.Frame(self.root, padx=20, pady=20)
        frame.pack()

        self.label = tk.Label(
            frame,
            text="",
            font=("Arial Unicode MS", 14),
            width=24,
            anchor="center",
        )
        self.label.pack(pady=(0, 12))

        self.button = tk.Button(
            frame,
            text="Start",
            font=("Arial Unicode MS", 12),
            width=10,
            command=self.toggle,
        )
        self.button.pack()

        self._update_label()

    def _now_display(self) -> str:
        return datetime.now().strftime("%Y  %m  %d  %H  %M  %S")

    def _now_cfg(self) -> str:
        return datetime.now().strftime("%Y:%m:%d:%H:%M:%S")

    def _update_label(self):
        self.label.config(text=self._now_display())
        self.timer_id = self.root.after(UPDATE_INTERVAL_MS, self._update_label)

    def _write_cfg(self):
        if not self.running:
            return
        with open(CFG_PATH, "w") as f:
            f.write(self._now_cfg() + "\n")
        self.root.after(UPDATE_INTERVAL_MS, self._write_cfg)

    def toggle(self):
        if self.running:
            self.running = False
            self.button.config(text="Start")
        else:
            self.running = True
            self.button.config(text="Stop")
            self._write_cfg()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    DateTimeCfgCreator().run()
