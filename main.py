import os
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, ttk, scrolledtext, messagebox

# ---------------------- CONFIG ----------------------
FFMPEG_CMD = "ffmpeg"  # Ensure ffmpeg is in PATH or provide full path

# ---------------------- APP ----------------------
class ConverterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Batch File Converter (FFmpeg)")
        self.root.geometry("700x500")

        self.files = []

        # UI Elements
        frame = ttk.Frame(root, padding=10)
        frame.pack(fill="both", expand=True)

        # File list
        self.file_list = tk.Listbox(frame, height=10)
        self.file_list.pack(fill="x", pady=5)

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill="x", pady=5)

        ttk.Button(btn_frame, text="Add Files", command=self.add_files).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Clear", command=self.clear_files).pack(side="left", padx=5)

        # Output format
        format_frame = ttk.Frame(frame)
        format_frame.pack(fill="x", pady=5)

        ttk.Label(format_frame, text="Convert to format (e.g. ogg, mp3, wav):").pack(side="left")
        self.format_entry = ttk.Entry(format_frame, width=10)
        self.format_entry.pack(side="left", padx=5)
        self.format_entry.insert(0, "ogg")

        # Output folder
        folder_frame = ttk.Frame(frame)
        folder_frame.pack(fill="x", pady=5)

        ttk.Label(folder_frame, text="Output Folder:").pack(side="left")
        self.output_dir = tk.StringVar()
        ttk.Entry(folder_frame, textvariable=self.output_dir, width=40).pack(side="left", padx=5)
        ttk.Button(folder_frame, text="Browse", command=self.select_output_dir).pack(side="left")

        # Convert button
        ttk.Button(frame, text="Start Conversion", command=self.start_conversion).pack(pady=10)

        # Log box
        self.log_box = scrolledtext.ScrolledText(frame, height=12)
        self.log_box.pack(fill="both", expand=True)

    def log(self, message):
        self.log_box.insert(tk.END, message + "\n")
        self.log_box.see(tk.END)

    def add_files(self):
        files = filedialog.askopenfilenames(title="Select files")
        for f in files:
            if f not in self.files:
                self.files.append(f)
                self.file_list.insert(tk.END, f)

    def clear_files(self):
        self.files.clear()
        self.file_list.delete(0, tk.END)

    def select_output_dir(self):
        folder = filedialog.askdirectory()
        if folder:
            self.output_dir.set(folder)

    def start_conversion(self):
        if not self.files:
            messagebox.showwarning("No files", "Please add files first.")
            return

        out_format = self.format_entry.get().strip()
        if not out_format:
            messagebox.showwarning("No format", "Please enter output format.")
            return

        output_dir = self.output_dir.get().strip()
        if not output_dir:
            messagebox.showwarning("No folder", "Please select output folder.")
            return

        thread = threading.Thread(target=self.convert_files, args=(out_format, output_dir))
        thread.start()

    def convert_files(self, out_format, output_dir):
        for file_path in self.files:
            try:
                base = os.path.splitext(os.path.basename(file_path))[0]
                output_path = os.path.join(output_dir, f"{base}.{out_format}")

                cmd = [FFMPEG_CMD, "-y", "-i", file_path, output_path]

                self.log(f"Converting: {file_path}")
                result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

                if result.returncode == 0:
                    self.log(f"✔ Success: {output_path}")
                else:
                    self.log(f"✖ Failed: {file_path}")
                    self.log(result.stderr)

            except Exception as e:
                self.log(f"Error: {str(e)}")

        self.log("--- Conversion Complete ---")


# ---------------------- MAIN ----------------------
if __name__ == "__main__":
    root = tk.Tk()
    app = ConverterApp(root)
    root.mainloop()
