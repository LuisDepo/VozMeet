#!/usr/bin/env python3
"""
date_time.cfg Creator — macOS port of the Windows VB6 original.

Sets the clock on a USB voice recorder. The recorder reads date_time.cfg
from the root of its drive at power-on and sets its internal clock to the
timestamp inside (format: yyyy:mm:dd:hh:mm:ss, same as the original tool).

Usage:
  1. Plug the recorder in — it mounts as a USB drive under /Volumes.
  2. Run:  python3 date_time_cfg_creator.py
  3. Pick the recorder volume and click Start. The current time is
     rewritten to date_time.cfg once a second so it stays fresh.
  4. Click "Stop & Eject" (writes one final timestamp, then ejects),
     unplug the recorder and power it on — it applies the time.

Headless mode (write once and exit):
  python3 date_time_cfg_creator.py --once [target_dir]
"""

import argparse
import os
import subprocess
import sys
from datetime import datetime

CFG_NAME = "date_time.cfg"
UPDATE_INTERVAL_MS = 1000
DISPLAY_FORMAT = "%Y %m %d %H %M %S"  # original label format: yyyy mm dd hh mm ss
CFG_FORMAT = "%Y:%m:%d:%H:%M:%S"      # original file format:  yyyy:mm:dd:hh:mm:ss
SCRIPT_DIR = os.path.dirname(os.path.abspath(sys.argv[0]))


def cfg_timestamp(now=None):
    return (now or datetime.now()).strftime(CFG_FORMAT)


def write_cfg(directory, now=None):
    """Write date_time.cfg with a CRLF ending (as VB6's Print # produced)
    and fsync so the data reaches the device even if it's unplugged."""
    path = os.path.join(directory, CFG_NAME)
    with open(path, "wb") as f:
        f.write((cfg_timestamp(now) + "\r\n").encode("ascii"))
        f.flush()
        os.fsync(f.fileno())
    return path


def removable_volumes():
    """Mounted volumes under /Volumes, excluding the boot volume."""
    base = "/Volumes"
    if not os.path.isdir(base):
        return []
    vols = []
    for name in sorted(os.listdir(base)):
        path = os.path.join(base, name)
        if os.path.islink(path) and os.path.realpath(path) == "/":
            continue  # boot volume symlink
        if os.path.isdir(path):
            vols.append(path)
    return vols


class App:
    def __init__(self):
        import tkinter as tk
        from tkinter import filedialog, ttk

        self.tk = tk
        self.filedialog = filedialog

        self.root = tk.Tk()
        self.root.title("date_time.cfg Creator")
        self.root.resizable(False, False)
        self.running = False

        frame = tk.Frame(self.root, padx=20, pady=16)
        frame.pack()

        self.clock_label = tk.Label(frame, text="", font=("Helvetica", 20))
        self.clock_label.pack(pady=(0, 12))

        vol_row = tk.Frame(frame)
        vol_row.pack(fill="x", pady=(0, 12))
        tk.Label(vol_row, text="Recorder:").pack(side="left")
        self.volume_var = tk.StringVar()
        self.volume_box = ttk.Combobox(
            vol_row, textvariable=self.volume_var, state="readonly", width=28
        )
        self.volume_box.pack(side="left", padx=6)
        tk.Button(vol_row, text="Refresh", command=self.refresh_volumes).pack(side="left")
        tk.Button(vol_row, text="Browse…", command=self.browse).pack(side="left", padx=(6, 0))

        btn_row = tk.Frame(frame)
        btn_row.pack(pady=(0, 8))
        self.start_button = tk.Button(btn_row, text="Start", width=10, command=self.toggle)
        self.start_button.pack(side="left")
        if sys.platform == "darwin":
            tk.Button(btn_row, text="Stop & Eject", width=12, command=self.eject).pack(
                side="left", padx=(8, 0)
            )

        self.status = tk.Label(frame, text="Select the recorder volume, then press Start.",
                               fg="gray", wraplength=360, justify="left")
        self.status.pack(fill="x")

        self.refresh_volumes()
        self._tick_clock()

    # -- helpers ---------------------------------------------------------

    def refresh_volumes(self):
        vols = removable_volumes()
        # If the script itself lives on a removable volume (original usage:
        # copy onto the recorder and run from there), preselect it.
        preferred = next((v for v in vols if SCRIPT_DIR.startswith(v)), None)
        self.volume_box["values"] = vols
        if preferred:
            self.volume_var.set(preferred)
        elif vols and self.volume_var.get() not in vols:
            self.volume_var.set(vols[0])
        elif not vols:
            self.volume_var.set("")
            self.status.config(text="No USB volume found — plug in the recorder and press Refresh.")

    def browse(self):
        chosen = self.filedialog.askdirectory(title="Select the recorder volume")
        if chosen:
            values = list(self.volume_box["values"])
            if chosen not in values:
                self.volume_box["values"] = values + [chosen]
            self.volume_var.set(chosen)

    def _tick_clock(self):
        self.clock_label.config(text=datetime.now().strftime(DISPLAY_FORMAT))
        self.root.after(UPDATE_INTERVAL_MS, self._tick_clock)

    def _write(self):
        path = write_cfg(self.volume_var.get())
        self.status.config(
            text=f"Writing {path}\nLast write: {datetime.now().strftime('%H:%M:%S')}"
        )
        return path

    def _write_loop(self):
        if not self.running:
            return
        try:
            self._write()
        except OSError as e:
            self._stop()
            self.status.config(text=f"Write failed (volume removed?): {e}")
            return
        self.root.after(UPDATE_INTERVAL_MS, self._write_loop)

    def _stop(self):
        self.running = False
        self.start_button.config(text="Start")
        self.volume_box.config(state="readonly")

    # -- actions ---------------------------------------------------------

    def toggle(self):
        if self.running:
            self._stop()
            return
        if not self.volume_var.get():
            self.status.config(text="Select the recorder volume first.")
            return
        self.running = True
        self.start_button.config(text="Stop")
        self.volume_box.config(state="disabled")
        self._write_loop()

    def eject(self):
        volume = self.volume_var.get()
        if not volume:
            self.status.config(text="Select the recorder volume first.")
            return
        self._stop()
        try:
            self._write()  # final, freshest timestamp
        except OSError as e:
            self.status.config(text=f"Final write failed: {e}")
            return
        result = subprocess.run(
            ["diskutil", "eject", volume], capture_output=True, text=True
        )
        if result.returncode == 0:
            self.status.config(text=f"Ejected {volume} — safe to unplug.\n"
                                    "The recorder will set its clock at next power-on.")
            self.refresh_volumes()
        else:
            self.status.config(text=f"Eject failed: {result.stderr.strip()}")

    def run(self):
        self.root.mainloop()


def main():
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument(
        "--once", nargs="?", const=SCRIPT_DIR, metavar="TARGET_DIR",
        help="write date_time.cfg once to TARGET_DIR (default: script directory) and exit",
    )
    args = parser.parse_args()

    if args.once is not None:
        path = write_cfg(args.once)
        print(f"Wrote {path}: {cfg_timestamp()}")
        return

    App().run()


if __name__ == "__main__":
    main()
