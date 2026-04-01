import os
import subprocess
import sys
import threading
from pathlib import Path
from tkinter import BooleanVar, END, Listbox, StringVar, filedialog, ttk, scrolledtext, messagebox
from tkinter import Tk as tk_Tk

_config_lock = threading.Lock()


# ---------------------- CONFIG ----------------------
def _find_ffmpeg() -> tuple[str, bool]:
    """Find FFmpeg path and whether it's valid. Returns (path, is_valid).

    Checks bundled paths first (with subprocess validation), then falls back to PATH.
    Subprocess is called exactly once per candidate until a valid one is found.
    """
    candidates: list[str] = []

    if getattr(sys, 'frozen', False):
        if hasattr(sys, '_MEIPASS'):
            candidates.append(os.path.join(sys._MEIPASS, "ffmpeg", "ffmpeg.exe"))
        exe_dir = os.path.dirname(sys.executable)
        candidates.append(os.path.join(exe_dir, "ffmpeg", "ffmpeg.exe"))

    candidates.append("ffmpeg")  # PATH fallback

    for path in candidates:
        try:
            result = subprocess.run(
                [path, "-version"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                return path, True
        except (OSError, subprocess.TimeoutExpired):
            pass

    return candidates[-1], False


def _get_config_path() -> Path:
    """Get config file path in user's app data directory (not next to exe)."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "sfx-convert" / "sfx-convert.ini"


def _load_config() -> dict[str, str]:
    """Load config from ini file."""
    cfg_path = _get_config_path()
    if cfg_path.exists():
        cfg: dict[str, str] = {}
        try:
            content = cfg_path.read_text(encoding="utf-8", errors="replace")
            for line in content.splitlines():
                line = line.strip()
                if '=' in line:
                    key, _, value = line.partition('=')
                    cfg[key.strip()] = value.strip()
        except OSError:
            cfg = {}
        return cfg
    return {}


def _save_config(cfg: dict[str, str], key: str, value: str) -> bool:
    """Save a single config key to ini file. Returns True on success.

    Uses a lock to prevent concurrent writes from multiple threads/processes.
    Also reloads from disk before writing to avoid overwriting changes from
    other instances that may have written since our last read.
    """
    cfg_path = _get_config_path()
    with _config_lock:
        # Reload to avoid overwriting concurrent changes from other instances
        latest = _load_config()
        latest[key] = value
        try:
            cfg_path.parent.mkdir(parents=True, exist_ok=True)
            cfg_path.write_text(
                "\n".join(f"{k} = {v}" for k, v in latest.items()),
                encoding="utf-8"
            )
            cfg.clear()
            cfg.update(latest)
            return True
        except OSError:
            return False


def _validate_ffmpeg(path: str) -> bool:
    """Check if FFmpeg at given path is executable."""
    try:
        result = subprocess.run(
            [path, "-version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


FFMPEG_CMD, FFMPEG_VALID = _find_ffmpeg()


# ---------------------- APP ----------------------
class ConverterApp:
    def __init__(self, root: tk_Tk) -> None:
        self.root = root
        self.root.title("Batch File Converter (FFmpeg)")
        self.root.geometry("700x520")

        self.files: list[str] = []
        self._files_set: set[str] = set()  # O(1) duplicate lookup
        self._cancel_flag = threading.Event()
        self._conversion_thread: threading.Thread | None = None
        self._current_process: subprocess.Popen | None = None
        self._max_log_lines = 500
        self._custom_ffmpeg_valid: bool | None = None

        # Load saved config
        self._config = _load_config()
        saved_folder = self._config.get("output_folder", "")
        saved_ffmpeg = self._config.get("ffmpeg_path", "")
        saved_format = self._config.get("output_format", "ogg")
        saved_strip_ext = self._config.get("strip_extension", "0") == "1"

        # UI Elements
        frame = ttk.Frame(root, padding=10)
        frame.pack(fill="both", expand=True)

        # File list
        self.file_list = Listbox(frame, height=10)
        self.file_list.pack(fill="x", pady=5)

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill="x", pady=5)

        ttk.Button(btn_frame, text="Add Files", command=self.add_files).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Remove Selected", command=self.remove_selected).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Clear", command=self.clear_files).pack(side="left", padx=5)

        # Output format
        format_frame = ttk.Frame(frame)
        format_frame.pack(fill="x", pady=5)

        ttk.Label(format_frame, text="Convert to format:").pack(side="left")
        self.format_entry = ttk.Entry(format_frame, width=10)
        self.format_entry.pack(side="left", padx=5)
        self.format_entry.insert(0, saved_format)
        self.strip_ext_var = BooleanVar(value=saved_strip_ext)
        ttk.Checkbutton(
            format_frame, text="Strip original ext",
            variable=self.strip_ext_var,
        ).pack(side="left", padx=5)

        # Output folder
        folder_frame = ttk.Frame(frame)
        folder_frame.pack(fill="x", pady=5)

        ttk.Label(folder_frame, text="Output Folder:").pack(side="left")
        self.output_dir = StringVar(value=saved_folder)
        ttk.Entry(folder_frame, textvariable=self.output_dir, width=40).pack(side="left", padx=5)
        ttk.Button(folder_frame, text="Browse", command=self.select_output_dir).pack(side="left")

        # FFmpeg path
        ffmpeg_frame = ttk.Frame(frame)
        ffmpeg_frame.pack(fill="x", pady=5)

        ttk.Label(ffmpeg_frame, text="FFmpeg path:").pack(side="left")
        self.ffmpeg_path_var = StringVar(value=saved_ffmpeg if saved_ffmpeg else FFMPEG_CMD)
        ffmpeg_entry = ttk.Entry(ffmpeg_frame, textvariable=self.ffmpeg_path_var, width=40)
        ffmpeg_entry.pack(side="left", padx=5)
        ffmpeg_entry.bind("<FocusOut>", lambda _: self._on_ffmpeg_path_change())

        # Progress label
        self.progress_label = ttk.Label(frame, text="", anchor="center")
        self.progress_label.pack(fill="x", pady=2)

        # Convert button row
        action_frame = ttk.Frame(frame)
        action_frame.pack(fill="x", pady=5)

        self.start_btn = ttk.Button(action_frame, text="Start Conversion", command=self.start_conversion)
        self.start_btn.pack(side="left", padx=5)
        self.cancel_btn = ttk.Button(action_frame, text="Cancel", command=self.cancel_conversion, state="disabled")
        self.cancel_btn.pack(side="left", padx=5)

        # Log box
        self.log_box = scrolledtext.ScrolledText(frame, height=10)
        self.log_box.pack(fill="both", expand=True, pady=5)

        # Validate FFmpeg on startup
        self._validate_ffmpeg_ui()

        # Handle window close during conversion
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Reload config when window is deiconified (brought to front from minimized)
        self.root.bind("<Map>", lambda _: self._reload_config())

    def _validate_ffmpeg_ui(self) -> None:
        """Validate FFmpeg availability and show status."""
        custom = self.ffmpeg_path_var.get().strip()
        ffmpeg_to_use = custom if custom else FFMPEG_CMD
        if custom:
            self._custom_ffmpeg_valid = _validate_ffmpeg(custom)
            is_valid = self._custom_ffmpeg_valid
        else:
            self._custom_ffmpeg_valid = None
            is_valid = FFMPEG_VALID
        if is_valid:
            self.log(f"[FFmpeg found: {ffmpeg_to_use}]")
        else:
            self.log(f"[WARNING] FFmpeg not found at: {ffmpeg_to_use}")

    def _on_ffmpeg_path_change(self) -> None:
        """Save custom FFmpeg path when user edits it and validate it."""
        path = self.ffmpeg_path_var.get().strip()
        _save_config(self._config, "ffmpeg_path", path)
        if path:
            self._custom_ffmpeg_valid = _validate_ffmpeg(path)
            if not self._custom_ffmpeg_valid:
                self.log(f"[WARNING] FFmpeg not found at custom path: {path}")
        else:
            self._custom_ffmpeg_valid = None

    def _on_close(self) -> None:
        """Handle window close - cancel conversion, kill subprocess, then destroy."""
        if self._current_process is not None:
            self._cancel_flag.set()
            try:
                self._current_process.kill()
            except OSError:
                pass
        if self._conversion_thread and self._conversion_thread.is_alive():
            self._cancel_flag.set()
            self._conversion_thread.join(timeout=3)
        self.root.destroy()

    def _reload_config(self) -> None:
        """Reload config from disk to pick up external changes."""
        new_config = _load_config()
        # Sync folder if changed externally
        old_val = self._config.get("output_folder") or ""
        new_val = new_config.get("output_folder") or ""
        if new_val != old_val:
            self.output_dir.set(new_config.get("output_folder", ""))
        # Sync FFmpeg path if changed externally
        old_ffmpeg = self._config.get("ffmpeg_path") or ""
        new_ffmpeg = new_config.get("ffmpeg_path") or ""
        if new_ffmpeg != old_ffmpeg:
            self.ffmpeg_path_var.set(new_config.get("ffmpeg_path", ""))
            self._custom_ffmpeg_valid = None
        # Sync format if changed externally
        old_fmt = self._config.get("output_format") or ""
        new_fmt = new_config.get("output_format") or ""
        if new_fmt != old_fmt:
            self.format_entry.delete(0, END)
            self.format_entry.insert(0, new_config.get("output_format", ""))
        # Sync strip extension if changed externally
        if (new_config.get("strip_extension") or "") != (self._config.get("strip_extension") or ""):
            self.strip_ext_var.set(new_config.get("strip_extension") == "1")
        self._config = new_config

    def _schedule_log(self, message: str) -> None:
        """Thread-safe logging via root.after()."""
        self.root.after(0, lambda msg=message: self._append_log(msg))

    def _append_log(self, message: str) -> None:
        """Append message to log box (must be called on main thread)."""
        self.log_box.insert(END, message + "\n")
        self.log_box.see(END)
        # Periodically trim to max lines to prevent unbounded growth
        count = int(self.log_box.index("end-1c").split(".")[0])
        if count > self._max_log_lines * 2:
            self.log_box.delete("1.0", f"{count - self._max_log_lines}.0")

    def log(self, message: str) -> None:
        """Log message - thread-safe wrapper."""
        self._schedule_log(message)

    def add_files(self) -> None:
        files = filedialog.askopenfilenames(title="Select files")
        for f in files:
            if f not in self._files_set:
                self._files_set.add(f)
                self.files.append(f)
                self.file_list.insert(END, f)

    def remove_selected(self) -> None:
        """Remove selected file(s) from the list."""
        selection = self.file_list.curselection()
        if not selection:
            return
        # Remove in reverse order to preserve indices
        for idx in reversed(selection):
            file_path = self.files[idx]
            self._files_set.discard(file_path)
            del self.files[idx]
            self.file_list.delete(idx)

    def clear_files(self) -> None:
        self.files.clear()
        self._files_set.clear()
        self.file_list.delete(0, END)

    def select_output_dir(self) -> None:
        folder = filedialog.askdirectory()
        if folder:
            self.output_dir.set(folder)
            _save_config(self._config, "output_folder", folder)

    def _get_ffmpeg_to_use(self) -> tuple[str, bool]:
        """Return (FFmpeg path, is_custom)."""
        custom = self.ffmpeg_path_var.get().strip()
        return (custom, True) if custom else (FFMPEG_CMD, False)

    def start_conversion(self) -> None:
        if not self.files:
            messagebox.showwarning("No files", "Please add files first.")
            return

        out_format = self.format_entry.get().strip()
        if not out_format:
            messagebox.showwarning("No format", "Please enter output format.")
            return

        if out_format != self._config.get("output_format", ""):
            _save_config(self._config, "output_format", out_format)

        strip_ext = self.strip_ext_var.get()
        if (strip_ext and self._config.get("strip_extension") != "1") or (not strip_ext and self._config.get("strip_extension") == "1"):
            _save_config(self._config, "strip_extension", "1" if strip_ext else "0")

        output_dir = self.output_dir.get().strip()
        if not output_dir:
            messagebox.showwarning("No folder", "Please select output folder.")
            return

        if not os.path.isdir(output_dir):
            messagebox.showwarning("Invalid folder", "Output folder does not exist or is not a directory.")
            return

        ffmpeg_to_use, is_custom = self._get_ffmpeg_to_use()
        if is_custom:
            is_valid = self._custom_ffmpeg_valid if self._custom_ffmpeg_valid is not None else _validate_ffmpeg(ffmpeg_to_use)
            if not is_valid:
                messagebox.showerror("FFmpeg not found",
                    f"FFmpeg not found or not executable at:\n{ffmpeg_to_use}\n\n"
                    "Please check the path or leave blank to use bundled FFmpeg.")
                return

        self._cancel_flag.clear()
        self.start_btn.config(state="disabled")
        self.cancel_btn.config(state="normal")
        self.progress_label.config(text="")

        strip_ext = self.strip_ext_var.get()

        self._conversion_thread = threading.Thread(
            target=self._convert_files,
            args=(out_format, output_dir, ffmpeg_to_use, strip_ext),
            daemon=True,
        )
        self._conversion_thread.start()

    def cancel_conversion(self) -> None:
        """Set cancel flag to stop conversion after current file."""
        self._cancel_flag.set()
        self.log("[Cancelled - will stop after current file]")

    def _convert_files(self, out_format: str, output_dir: str, ffmpeg_cmd: str, strip_ext: bool) -> None:
        # Snapshot files to avoid race with clear_files() during conversion
        files_to_convert = list(self.files)
        total = len(files_to_convert)
        for idx, file_path in enumerate(files_to_convert):
            if self._cancel_flag.is_set():
                self._schedule_log("--- Conversion Cancelled ---")
                break

            self._schedule_log(f"[{idx + 1}/{total}] Converting: {file_path}")
            self.root.after(0, lambda i=idx, t=total: self.progress_label.config(text=f"Converting {i + 1} of {t}..."))

            try:
                if strip_ext:
                    base = os.path.splitext(os.path.basename(file_path))[0]
                    output_path = os.path.join(output_dir, f"{base}.{out_format}")
                else:
                    original_name = os.path.basename(file_path)
                    output_path = os.path.join(output_dir, f"{original_name}.{out_format}")

                cmd = [ffmpeg_cmd, "-y", "-i", file_path, output_path]

                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                self._current_process = proc

                try:
                    stderr_output, _ = proc.communicate(timeout=3600)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.communicate()
                    self._schedule_log(f"  Error: FFmpeg timed out after 3600s: {file_path}")
                    self._current_process = None
                    continue
                finally:
                    self._current_process = None

                if self._cancel_flag.is_set():
                    self._schedule_log("--- Conversion Cancelled ---")
                    break

                if proc.returncode == 0:
                    self._schedule_log(f"  Success: {output_path}")
                else:
                    error_msg = stderr_output.strip().splitlines()
                    self._schedule_log(f"  Failed: {file_path}")
                    # Show last 5 lines of error
                    for line in error_msg[-5:]:
                        if line.strip():
                            self._schedule_log(f"    {line.strip()}")

            except FileNotFoundError:
                self._schedule_log(f"  Error: input file not found: {file_path}")
            except PermissionError:
                self._schedule_log(f"  Error: permission denied: {output_path}")
            except OSError as e:
                self._schedule_log(f"  Error: {str(e)}")

        self._schedule_log("--- Conversion Complete ---")
        self.root.after(0, self._set_converting_state)

    def _set_converting_state(self) -> None:
        self.start_btn.config(state="normal")
        self.cancel_btn.config(state="disabled")
        self.progress_label.config(text="")
        self._conversion_thread = None


# ---------------------- MAIN ----------------------
if __name__ == "__main__":
    root = tk_Tk()
    app = ConverterApp(root)
    root.mainloop()
