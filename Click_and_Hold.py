from __future__ import annotations

import atexit
import ctypes
import sys
import tkinter as tk
from ctypes import wintypes
from tkinter import ttk

if sys.platform != "win32":
    raise RuntimeError("This app only works on Windows.")

user32 = ctypes.WinDLL("user32", use_last_error=True)

VK_F6 = 0x75
INPUT_MOUSE = 0
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [
        ("type", wintypes.DWORD),
        ("u", INPUT_UNION),
    ]


user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = wintypes.UINT
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short


class MouseHoldController:
    def __init__(self) -> None:
        self.is_holding = False
        atexit.register(self.release_if_needed)

    def _send_mouse(self, flags: int) -> None:
        event = INPUT(type=INPUT_MOUSE, mi=MOUSEINPUT(0, 0, 0, flags, 0, 0))
        sent = user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT))
        if sent != 1:
            raise ctypes.WinError(ctypes.get_last_error())

    def hold(self) -> bool:
        if self.is_holding:
            return False

        self._send_mouse(MOUSEEVENTF_LEFTDOWN)
        self.is_holding = True
        return True

    def release(self) -> bool:
        if not self.is_holding:
            return False

        self._send_mouse(MOUSEEVENTF_LEFTUP)
        self.is_holding = False
        return True

    def toggle(self) -> bool:
        if self.is_holding:
            self.release()
        else:
            self.hold()
        return self.is_holding

    def release_if_needed(self) -> None:
        if self.is_holding:
            self.release()


class ClickHoldApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.closed = False
        self.controller = MouseHoldController()
        self.last_f6_down = False
        self.pending_hold_job: str | None = None

        self.root.title("Left Click Hold")
        self.root.geometry("360x200")
        self.root.minsize(360, 200)
        self.root.configure(bg="#f4f6fb")
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.status_var = tk.StringVar(value="Status: idle")
        self.hotkey_var = tk.StringVar(value="F6: registering...")

        self.configure_styles()
        self.build_ui()

        self.set_ready_message()
        self.refresh_ui()
        self.poll_f6()

    def configure_styles(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("App.TFrame", background="#f4f6fb")
        style.configure("Title.TLabel", background="#f4f6fb", foreground="#182238", font=("Segoe UI", 16, "bold"))
        style.configure("Body.TLabel", background="#f4f6fb", foreground="#182238", font=("Segoe UI", 10))
        style.configure("Status.TLabel", background="#f4f6fb", foreground="#182238", font=("Segoe UI", 11, "bold"))
        style.configure(
            "App.TButton",
            font=("Segoe UI", 10),
            padding=(16, 10),
            relief="flat",
            borderwidth=1,
        )
        style.map(
            "App.TButton",
            background=[("active", "#eef3ff"), ("disabled", "#e6eaf3"), ("!disabled", "#ffffff")],
            foreground=[("disabled", "#73809b"), ("!disabled", "#182238")],
            bordercolor=[("!disabled", "#cad3e4")],
        )

    def build_ui(self) -> None:
        outer = ttk.Frame(self.root, style="App.TFrame", padding=20)
        outer.pack(fill="both", expand=True)

        ttk.Label(outer, text="Left Click Hold", style="Title.TLabel").pack(anchor="w")
        ttk.Label(outer, textvariable=self.status_var, style="Status.TLabel").pack(anchor="w", pady=(10, 0))
        ttk.Label(outer, textvariable=self.hotkey_var, style="Body.TLabel", wraplength=300, justify="left").pack(
            anchor="w", pady=(8, 0)
        )
        ttk.Label(
            outer,
            text="Click Start to hold the left mouse button. Press F6 anywhere to toggle hold and release.",
            style="Body.TLabel",
            wraplength=300,
            justify="left",
        ).pack(anchor="w", pady=(8, 16))

        button_row = ttk.Frame(outer, style="App.TFrame")
        button_row.pack(fill="x")
        button_row.columnconfigure(0, weight=1)
        button_row.columnconfigure(1, weight=1)

        self.start_button = ttk.Button(button_row, text="Start", style="App.TButton", command=self.start_hold)
        self.start_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        self.stop_button = ttk.Button(button_row, text="Release", style="App.TButton", command=self.release_hold)
        self.stop_button.grid(row=0, column=1, sticky="ew", padx=(6, 0))

    def set_ready_message(self) -> None:
        self.hotkey_var.set("F6: ready (global toggle)")

    def set_error_message(self, message: str) -> None:
        self.hotkey_var.set(f"Error: {message}")

    def run_mouse_action(self, action) -> bool:
        try:
            action()
        except OSError as exc:
            self.set_error_message(str(exc))
            return False

        self.set_ready_message()
        return True

    def poll_f6(self) -> None:
        if self.closed:
            return

        f6_down = bool(user32.GetAsyncKeyState(VK_F6) & 0x8000)
        if f6_down and not self.last_f6_down:
            self.toggle_hold()
        self.last_f6_down = f6_down

        self.root.after(25, self.poll_f6)

    def start_hold(self) -> None:
        if self.controller.is_holding or self.pending_hold_job is not None:
            return

        self.pending_hold_job = self.root.after(150, self._hold_from_button)
        self.refresh_ui()

    def _hold_from_button(self) -> None:
        self.pending_hold_job = None
        self.run_mouse_action(self.controller.hold)
        self.refresh_ui()

    def cancel_pending_hold(self) -> None:
        if self.pending_hold_job is not None:
            self.root.after_cancel(self.pending_hold_job)
            self.pending_hold_job = None

    def release_hold(self) -> None:
        self.cancel_pending_hold()
        self.run_mouse_action(self.controller.release)
        self.refresh_ui()

    def toggle_hold(self) -> None:
        if self.pending_hold_job is not None:
            self.cancel_pending_hold()
            self.run_mouse_action(self.controller.hold)
        else:
            self.run_mouse_action(self.controller.toggle)
        self.refresh_ui()

    def refresh_ui(self) -> None:
        if self.pending_hold_job is not None:
            self.status_var.set("Status: arming hold...")
            self.start_button.state(["disabled"])
            self.stop_button.state(["!disabled"])
        elif self.controller.is_holding:
            self.status_var.set("Status: holding left mouse button")
            self.start_button.state(["disabled"])
            self.stop_button.state(["!disabled"])
        else:
            self.status_var.set("Status: idle")
            self.start_button.state(["!disabled"])
            self.stop_button.state(["disabled"])

    def on_close(self) -> None:
        self.closed = True
        self.cancel_pending_hold()
        self.controller.release_if_needed()
        self.root.destroy()


def main() -> int:
    root = tk.Tk()
    ClickHoldApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
