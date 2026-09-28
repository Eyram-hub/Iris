IRIS DESKTOP APP — QML FIX 2

Replace the old build_iris.ps1 with this one and keep these files together in:
C:\Users\Eyram\Desktop\Iris.eyram

Required:
  Iris.py
  Main.qml
  iris_qt_runtime.py
  build_iris.ps1
  ai\Qwen3-4B-Q6_K.gguf
  model\<Vosk files>
  .venv\

Run PowerShell:
  cd C:\Users\Eyram\Desktop\Iris.eyram
  Set-ExecutionPolicy -Scope Process Bypass
  .\build_iris.ps1

The build explicitly uses PyInstaller's --contents-directory . so the QML/data
layout is compatible with current PyInstaller onedir behavior. It also verifies
and, if needed, copies Main.qml beside Iris.exe after the build.
