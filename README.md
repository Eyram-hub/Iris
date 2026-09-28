# Iris

Iris is a local-first Windows desktop AI assistant built with Python, PySide6/QML, Qwen GGUF models, Vosk speech recognition, and Windows text-to-speech.

## Included

- PySide6 + QML interface
- Animated rainbow Iris orb
- Local Qwen3 GGUF chat brain
- Conversation context and local memory
- Voice wake word: "Iris"
- Spoken startup greeting and spoken answers
- Keyboard input, Enter, and SEND
- Windows desktop commands
- YouTube/web launching helpers
- Vosk-based local speech recognition

## Requirements

- Windows 10/11
- Python 3.14
- A compatible C/C++ build or prebuilt `llama-cpp-python` package for your Python version
- PySide6
- sounddevice
- Vosk
- pyttsx3

Install the Python packages with a command appropriate for your environment.

## Local model files

This repository does **not** include model files.

Place your existing Qwen model at:

`ai/Qwen3-4B-Q6_K.gguf`

Place your existing Vosk model under:

`model/`

Do not commit large GGUF model files or private memory files to the repository.

## Run from source

```powershell
cd C:\Users\Eyram\Desktop\Iris.eyram
.\.venv\Scripts\python.exe Iris.py
```

## Project status

Iris is an active personal project and is still being improved. Interfaces, models, command coverage, and performance may change between versions.

## License

No project license has been selected yet. Model and dependency licenses remain separate from the Iris source code.
