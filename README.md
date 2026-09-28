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

## v2.0 Development

The `v2.0-dev` branch is the active development track for the next major Iris release. It is intended for daily testing and improvement before the stable v2.0 release.

Current v2.0 work includes persistent conversation history, a New Chat workflow, improved conversational prompting, compact response behavior for routine questions, and an upgraded animated rainbow interface.

Major release timing and individual features may change as testing and user feedback evolve.

## Roadmap

Iris is planned as a continuously improving project with a major feature-focused release approximately every two months, alongside smaller bug fixes, performance improvements, and maintenance releases.

| Release | Planned focus |
|---|---|
| **v1.0 — Foundation** | Stable AI, voice, memory, commands, and the new interface |
| **v1.1 — Intelligence** | Better conversation handling, context, memory, and response quality |
| **v1.2 — Automation** | More Windows controls, desktop actions, and useful workflows |
| **v1.3 — Voice** | Better wake-word behavior, speech recognition, and natural voice interaction |
| **v1.4 — Visuals** | More advanced orb animation, UI effects, themes, and customization |
| **v1.5 — Productivity** | More tools for files, notes, study, and everyday computer tasks |
| **v2.0 — Next Generation** | A larger architectural and feature expansion based on user feedback |

Release timing and individual features may change as development, testing, and user feedback evolve.

## Support Iris

Iris is an independent project built to explore a practical, private, local-first desktop AI assistant.

If you find Iris useful and want to support continued development, you can support the project through GitHub Sponsors:

**[Support Iris on GitHub Sponsors](https://github.com/sponsors/Eyram-hub)**

Support helps fund continued work on performance, voice interaction, the visual interface, Windows integration, documentation, and new features.

### What supporters can expect

- Development updates as Iris improves
- Early looks at new features
- Acknowledgement in the project when requested
- Continued open-source development

Sponsorship is optional. Iris remains an open-source project, and sponsorship does not guarantee a particular feature or release date.

## Project status

Iris is an active personal project and is still being improved. Interfaces, models, command coverage, and performance may change between versions.

## License

No project license has been selected yet. Model and dependency licenses remain separate from the Iris source code.
