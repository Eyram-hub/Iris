$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $Python)) { throw "Iris .venv not found: $Python" }
if (-not (Test-Path '.\Iris.py')) { throw 'Iris.py not found.' }
if (-not (Test-Path '.\Main.qml')) { throw 'Main.qml not found.' }
if (-not (Test-Path '.\iris_qt_runtime.py')) { throw 'iris_qt_runtime.py not found.' }
if (-not (Test-Path '.\ai\Qwen3-4B-Q6_K.gguf')) { throw 'Qwen3-4B-Q6_K.gguf not found in ai folder.' }
if (-not (Test-Path '.\model')) { throw 'Vosk model folder not found.' }

& $Python -m pip install -U pyinstaller
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller installation failed.' }

Remove-Item '.\build' -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item '.\dist\Iris' -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item '.\dist\Iris.exe' -Force -ErrorAction SilentlyContinue
Remove-Item '.\Iris.spec' -Force -ErrorAction SilentlyContinue

Write-Host 'Building Iris with QML at the app root...' -ForegroundColor Cyan
& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --onedir `
    --contents-directory . `
    --windowed `
    --name Iris `
    --collect-all PySide6 `
    --collect-all shiboken6 `
    --collect-submodules PySide6.QtQml `
    --collect-submodules PySide6.QtQuick `
    --collect-submodules PySide6.QtQuickControls2 `
    --add-data "$ProjectRoot\Main.qml:." `
    --runtime-hook "$ProjectRoot\iris_qt_runtime.py" `
    "$ProjectRoot\Iris.py"

if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed.' }

$app = Join-Path $ProjectRoot 'dist\Iris'
if (-not (Test-Path $app)) { throw "PyInstaller did not create $app" }

# PyInstaller 6.x normally places onedir support files in _internal.
# We explicitly use --contents-directory . above, but also verify/copy QML
# so the app has a deterministic Main.qml next to Iris.exe.
$qmlRoot = Join-Path $app 'Main.qml'
$qmlInternal = Join-Path $app '_internal\Main.qml'
if (-not (Test-Path $qmlRoot) -and (Test-Path $qmlInternal)) {
    Copy-Item $qmlInternal $qmlRoot -Force
}
if (-not (Test-Path $qmlRoot)) {
    Copy-Item '.\Main.qml' $qmlRoot -Force
}
if (-not (Test-Path $qmlRoot)) { throw "Could not place Main.qml in $app" }

New-Item -ItemType Directory -Force -Path (Join-Path $app 'ai') | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $app 'model') | Out-Null

Write-Host 'Copying existing Qwen model...' -ForegroundColor Cyan
Copy-Item '.\ai\Qwen3-4B-Q6_K.gguf' (Join-Path $app 'ai\Qwen3-4B-Q6_K.gguf') -Force

Write-Host 'Copying existing Vosk model...' -ForegroundColor Cyan
Copy-Item '.\model\*' (Join-Path $app 'model') -Recurse -Force

$desktop = [Environment]::GetFolderPath('Desktop')
$shortcut = Join-Path $desktop 'Iris.lnk'
$target = Join-Path $app 'Iris.exe'
$shell = New-Object -ComObject WScript.Shell
$link = $shell.CreateShortcut($shortcut)
$link.TargetPath = $target
$link.WorkingDirectory = $app
$link.IconLocation = $target
$link.Description = 'Iris personal AI assistant'
$link.Save()

Write-Host ''
Write-Host 'IRIS DESKTOP APP CREATED SUCCESSFULLY' -ForegroundColor Green
Write-Host "App:      $target"
Write-Host "QML:      $qmlRoot"
Write-Host "Shortcut: $shortcut"
