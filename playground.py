import tkinter as tk
from tkinter import messagebox
import threading
import time
import json
import os, sys
from datetime import datetime
from pathlib import Path
from pystray import MenuItem, Menu, Icon
from PIL import Image, ImageDraw

try:
    from plyer import notification
    PLYER_AVAILABLE = True
except ImportError:
    PLYER_AVAILABLE = False
    print("Warning: 'plyer' not installed. Startup notification disabled.")
    print("Install with: pip install plyer")

CONFIG_FILE = "grass_config.json"

DEFAULT_CONFIG = {
    "session_duration_minutes": 1,
    "break_duration_minutes": 15,
    "enabled": True
}

class GrassReminderApp:
    def __init__(self):
        self.config = self.load_config()
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.geometry("0x0+0+0")  
        self.root.attributes("-alpha", 0.0)
        self.root.withdraw = lambda : None
        # Break tracking
        self.session_start = None
        self.break_start = None
        self.is_break_active = False
        self.monitoring = False
        self.break_window = None  # Track break window to avoid duplicates @Lunar-vow-crimson
        self.img = self.resource_path("static/grass.png")
        self.root.iconphoto(True, tk.PhotoImage(file=self.img))

        # Create system tray icon
        self.icon = Icon("Grass Reminder", self.create_image(path=self.img), menu=Menu(
            MenuItem("Settings", self.open_settings),
            MenuItem("Exit", self.quit_app)
        ))
        self.icon.run_detached()

        # Show startup notification
        self.show_startup_notification()

        # Start monitoring in background
        self.start_monitoring()

    def show_startup_notification(self):
        if not PLYER_AVAILABLE:
            return

        status = "enabled" if self.config["enabled"] else "disabled"
        try:
            notification.notify(
                title="Grass Reminder Started",
                message=f"Monitoring is now {status}!\nSession: {self.config['session_duration_minutes']} min • Break: {self.config['break_duration_minutes']} min",
                app_name="Grass Reminder",
                timeout=5  # seconds
            )
        except Exception as e:
            print(f"Failed to show notification: {e}")

    @staticmethod
    def create_image(path: str):
        if not path or not os.path.exists(path):
            image = Image.new('RGB', (64, 64), 'green')
            dc = ImageDraw.Draw(image)
            for i in range(0, 64, 8):
                dc.line([(i, 64), (i + 4, 32)], fill='darkgreen', width=3)
            return image
        else:
            return Image.open(path)

    @staticmethod    
    def resource_path(relative_path):
        try:
            base_path = sys._MEIPASS
        except Exception:
            base_path = Path(__file__).parent
        return Path(base_path) / relative_path    

    def open_settings(self):
        # Create settings window with stable parent (self.root is alive!)
        settings_win = tk.Toplevel(self.root)
        settings_win.title("Grass Reminder Settings")
        settings_win.geometry("400x250")
        settings_win.resizable(False, False)
        settings_win.transient(self.root)
        settings_win.grab_set()
        settings_win.focus_set()
        settings_win.lift()
        settings_win.attributes('-topmost', True)

        # Prevent closing via [X] without saving? Optional.
        # settings_win.protocol("WM_DELETE_WINDOW", lambda: None)

        tk.Label(settings_win, text="Session Duration (minutes):", font=("Arial", 12)).pack(pady=(20, 5))
        session_var = tk.StringVar(value=str(self.config["session_duration_minutes"]))
        session_entry = tk.Entry(settings_win, textvariable=session_var, font=("Arial", 12), width=10)
        session_entry.pack()

        tk.Label(settings_win, text="Break Duration (minutes):", font=("Arial", 12)).pack(pady=(15, 5))
        break_var = tk.StringVar(value=str(self.config["break_duration_minutes"]))
        break_entry = tk.Entry(settings_win, textvariable=break_var, font=("Arial", 12), width=10)
        break_entry.pack()

        enabled_var = tk.BooleanVar(value=self.config["enabled"])
        enabled_cb = tk.Checkbutton(
            settings_win,
            text="Enable Grass Reminder",
            variable=enabled_var,
            font=("Arial", 12)
        )
        enabled_cb.pack(pady=15)

        def save_and_close():
            try:
                session = int(session_var.get())
                break_dur = int(break_var.get())
                if session <= 0 or break_dur <= 0:
                    raise ValueError("Values must be positive integers")
                
                self.config["session_duration_minutes"] = session
                self.config["break_duration_minutes"] = break_dur
                self.config["enabled"] = enabled_var.get()
                self.save_config(self.config)

                if not self.config["enabled"]:
                    self.end_break()
                else:
                    if not self.is_break_active:
                        self.session_start = datetime.now()
                
                settings_win.destroy()
                messagebox.showinfo("Success", "Settings saved!")
                if PLYER_AVAILABLE:
                    try:
                        notification.notify(
                            title="Grass Reminder Settings Updated",
                            message=f"Monitoring {'enabled' if self.config['enabled'] else 'disabled'}",
                            app_name="Grass Reminder",
                            timeout=3
                        )
                    except:
                        pass
            except ValueError as e:
                messagebox.showerror("Invalid Input", f"Please enter valid numbers.\n{str(e)}")

        tk.Button(
            settings_win,
            text="Save Settings",
            command=save_and_close,
            font=("Arial", 12),
            bg="green",
            fg="white"
        ).pack(pady=10)

        # CRITICAL: Force focus and keep on top after creation
        settings_win.after(50, lambda: settings_win.focus_force())
        settings_win.after(100, lambda: settings_win.attributes('-topmost', True))

    def quit_app(self):
        self.monitoring = False
        self.icon.stop()
        self.root.quit()
        os._exit(0)

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    config = json.load(f)
                    for key, value in DEFAULT_CONFIG.items():
                        if key not in config:
                            config[key] = value
                    return config
            except Exception:
                return DEFAULT_CONFIG.copy()
        else:
            self.save_config(DEFAULT_CONFIG.copy())
            return DEFAULT_CONFIG.copy()

    def save_config(self, config):
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=4)

    def start_monitoring(self):
        if not self.monitoring:
            self.monitoring = True
            monitor_thread = threading.Thread(target=self.monitor_activity, daemon=True)
            monitor_thread.start()

    def monitor_activity(self):
        while self.monitoring:
            if not self.config["enabled"]:
                time.sleep(5)
                continue

            current_time = datetime.now()

            if not self.is_break_active:
                if self.session_start is None:
                    self.session_start = current_time
                else:
                    session_duration = (current_time - self.session_start).total_seconds() / 60
                    if session_duration >= self.config["session_duration_minutes"]:
                        self.trigger_break()
            else:
                if self.break_start:
                    break_duration = (current_time - self.break_start).total_seconds() / 60
                    if break_duration >= self.config["break_duration_minutes"]:
                        self.root.after(0, self.end_break)

            time.sleep(1)

    def trigger_break(self):
        if self.is_break_active or self.break_window is not None:
            return 
        self.is_break_active = True
        self.break_start = datetime.now()
        self.root.after(0, self.show_break_window)

    def show_break_window(self):
        if self.break_window is not None:
            return

        break_window = tk.Toplevel(self.root)
        self.break_window = break_window
        break_window.title("Touch Grass!")
        break_window.attributes('-fullscreen', True)
        break_window.attributes('-topmost', True)
        break_window.config(bg='green')
        break_window.protocol("WM_DELETE_WINDOW", lambda: None)

        message = (
            "🌿 TOUCH SOME GRASS! 🌿\n\n"
            f"Time for a {self.config['break_duration_minutes']}-minute break!\n\n"
            "Step away from your computer and get some fresh air!\n\n"
            "Or go get a life!\n\n"
        )

        label = tk.Label(
            break_window,
            text=message,
            font=("Arial", 36, "bold"),
            bg='green',
            fg='white',
            justify='center'
        )
        label.pack(expand=True)

        close_btn = tk.Button(
            break_window,
            text="I've Touched Grass!",
            font=("Arial", 24),
            command=lambda: self.attempt_close_break(break_window),
            state='disabled'
        )
        close_btn.pack(pady=20)

        break_ms = int(self.config["break_duration_minutes"] * 60 * 1000)

        self.root.after(break_ms, lambda: close_btn.config(state='normal') if break_window.winfo_exists() else None)
        self.root.after(break_ms, lambda: self.auto_end_break(break_window))

    def attempt_close_break(self, window):
        if window.winfo_exists():
            window.destroy()
        self.break_window = None
        if self.is_break_active:
            self.end_break()

    def auto_end_break(self, window):
        if window.winfo_exists():
            window.destroy()
        self.break_window = None
        if self.is_break_active:
            self.end_break()

    def end_break(self):
        self.is_break_active = False
        self.session_start = None
        self.break_start = None
        self.break_window = None

    def run(self):
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            self.quit_app()


if __name__ == "__main__":
    app = GrassReminderApp()
    app.run()
