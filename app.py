"""Auto Clicker - single-file Windows app.

Clicks wherever your cursor is, at whatever speed you set.
F6 toggles it on/off from anywhere. The window has START/STOP too.
No install, no settings saved anywhere, closes clean.
"""
import ctypes
import threading
import time
import tkinter as tk
from tkinter import ttk

user32 = ctypes.windll.user32

WM_HOTKEY = 0x0312
HOTKEY_ID = 1
VK_F6 = 0x75

# mouse_event flags
DOWN_UP = {
    "Left": (0x0002, 0x0004),
    "Right": (0x0008, 0x0010),
    "Middle": (0x0020, 0x0040),
}

clicking = False
click_count = 0
stop_event = threading.Event()


def do_click(button):
    down, up = DOWN_UP[button]
    user32.mouse_event(down, 0, 0, 0, 0)
    user32.mouse_event(up, 0, 0, 0, 0)


def click_loop(interval_s, button, on_tick):
    global click_count
    while not stop_event.is_set():
        if clicking:
            do_click(button)
            click_count += 1
            on_tick(click_count)
            # sleep in small slices so STOP reacts fast
            slept = 0.0
            while slept < interval_s and clicking and not stop_event.is_set():
                time.sleep(0.005)
                slept += 0.005
        else:
            time.sleep(0.01)


def hotkey_loop(toggle_cb):
    # Global F6 toggle via the documented RegisterHotKey API (no keyboard hook).
    import ctypes.wintypes as wt
    if not user32.RegisterHotKey(None, HOTKEY_ID, 0, VK_F6):
        return
    try:
        msg = wt.MSG()
        while not stop_event.is_set():
            ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if ret == 0 or ret == -1:
                break
            if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                toggle_cb()
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
    finally:
        user32.UnregisterHotKey(None, HOTKEY_ID)


class App:
    def __init__(self, root):
        self.root = root
        root.title("Auto Clicker")
        root.geometry("300x265")
        root.resizable(False, False)

        self.button_var = tk.StringVar(value="Left")
        self.cps_var = tk.StringVar(value="1")
        self.delay_var = tk.StringVar(value="1000")
        self.status_var = tk.StringVar(value="Stopped — press F6 or START")
        self._syncing = False
        self.cps_var.trace_add("write", self._cps_changed)
        self.delay_var.trace_add("write", self._delay_changed)

        frm = ttk.Frame(root, padding=16)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text="Clicks per second:").grid(row=0, column=0, sticky="w")
        ttk.Entry(frm, textvariable=self.cps_var, width=10).grid(row=0, column=1, sticky="w", padx=8)

        ttk.Label(frm, text="Delay between clicks (ms):").grid(row=1, column=0, sticky="w", pady=8)
        ttk.Entry(frm, textvariable=self.delay_var, width=10).grid(row=1, column=1, sticky="w", padx=8)

        ttk.Label(frm, text="Mouse button:").grid(row=2, column=0, sticky="w", pady=8)
        ttk.Combobox(frm, textvariable=self.button_var, values=["Left", "Right", "Middle"],
                     width=8, state="readonly").grid(row=2, column=1, sticky="w", padx=8)

        self.toggle_btn = ttk.Button(frm, text="START", command=self.toggle)
        self.toggle_btn.grid(row=3, column=0, columnspan=2, pady=10, sticky="ew")

        ttk.Label(frm, textvariable=self.status_var, wraplength=260).grid(
            row=4, column=0, columnspan=2, sticky="w")
        ttk.Label(frm, text="F6 toggles clicking anywhere.", foreground="gray").grid(
            row=5, column=0, columnspan=2, sticky="w", pady=(6, 0))

    @staticmethod
    def _fmt_cps(cps):
        return f"{cps:.2f}".rstrip("0").rstrip(".")

    def _cps_changed(self, *a):
        if self._syncing:
            return
        try:
            cps = float(self.cps_var.get())
        except ValueError:
            return
        if cps <= 0:
            return
        cps = min(cps, 1000.0)
        self._syncing = True
        self.delay_var.set(str(int(round(1000.0 / cps))))
        self._syncing = False

    def _delay_changed(self, *a):
        if self._syncing:
            return
        try:
            delay = int(float(self.delay_var.get()))
        except ValueError:
            return
        if delay <= 0:
            return
        delay = max(1, delay)
        self._syncing = True
        self.cps_var.set(self._fmt_cps(1000.0 / delay))
        self._syncing = False

    def start_worker(self, interval_s, button):
        self.worker = threading.Thread(
            target=click_loop, args=(interval_s, button, self.on_tick), daemon=True)
        self.worker.start()

    def on_tick(self, n):
        self.root.after(0, lambda: self.status_var.set(f"Clicking… {n} clicks (F6 or STOP to stop)"))

    def set_clicking(self, on):
        global clicking, click_count
        clicking = on
        if on:
            try:
                interval_ms = max(1, int(float(self.delay_var.get())))
            except ValueError:
                interval_ms = 1000
                self.delay_var.set("1000")
            click_count = 0
            self.start_worker(interval_ms / 1000.0, self.button_var.get())
            self.toggle_btn.config(text="STOP")
            self.status_var.set("Clicking… (F6 or STOP to stop)")
        else:
            self.toggle_btn.config(text="START")
            total = click_count
            self.status_var.set(f"Stopped — {total} clicks. Press F6 or START")

    def toggle(self):
        self.set_clicking(not clicking)

    def on_close(self):
        global clicking
        clicking = False
        stop_event.set()
        # wake the hotkey thread's GetMessage so it can exit
        tid = getattr(self, "hk_thread_id", None)
        if tid:
            user32.PostThreadMessageW(tid, 0x0012, 0, 0)  # WM_QUIT
        self.root.destroy()


def main():
    root = tk.Tk()
    app = App(root)
    hk_thread = threading.Thread(target=hotkey_loop, args=(app.toggle,), daemon=True)
    hk_thread.start()
    app.hk_thread_id = hk_thread.native_id
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
