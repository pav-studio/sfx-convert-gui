# 🎧 Batch File Converter (FFmpeg GUI)

A simple Python GUI tool to batch convert audio/video files into any format using FFmpeg. Built with tkinter.

![preview image](preview.png)

## ✨ Features
- **Bundled FFmpeg** — no installation needed, just double-click to run
- Select multiple files and batch convert
- Convert to any format (ogg, mp3, wav, flac, aac, etc.)
- Choose output directory
- **Strip original extension** — `sound.wav` → `sound.ogg` instead of `sound.wav.ogg`
- Real-time logging with progress indicator
- Cancel in-progress conversions
- Settings persist between sessions (output folder, format, FFmpeg path)
- Custom FFmpeg path support if you prefer your own FFmpeg build

## 🚀 Run

**Standalone executable (recommended):**
```bash
dist\sfx-convert.exe
```

**From source:**
```bash
python main.py
```

## 📦 Build from Source

```bash
pip install pyinstaller
pyinstaller main.spec --clean
```

Output: `dist/sfx-convert.exe`

## 📸 Usage
1. Click **Add Files** to select audio/video files
2. Enter output format (e.g., `ogg`, `mp3`, `wav`)
3. Optionally check **Strip original ext** to remove source extension
4. Select output folder
5. Click **Start Conversion**

## 💡 Tips
- Use `.ogg` for games (best compression + looping support)
- Use `.wav` for short sound effects
- **Strip original ext** is useful when batch converting files of the same type (e.g., all `.wav` → `.ogg`)

## 🛠 Requirements (development)
- Python 3.x
- FFmpeg (auto-detected: bundled → custom path → system PATH)
- PyInstaller (for building exe)
