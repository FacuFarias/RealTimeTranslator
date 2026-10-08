$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $pythonPath)) { throw 'Primero crea .venv e instala el proyecto con las dependencias build. Consulta README.md.' }
if (!(Test-Path -LiteralPath 'models\manifest.json')) { throw 'Ejecuta scripts\prepare_models.py primero.' }
& $pythonPath -m PyInstaller --noconfirm Traductor.spec
if ($LASTEXITCODE -ne 0) { throw 'Falló PyInstaller.' }
$portablePath = Join-Path $projectRoot 'dist\Traductor'
& $pythonPath scripts\build_portable.py
if ($LASTEXITCODE -ne 0) { throw 'Falló el empaquetado con Python integrado.' }
Copy-Item -LiteralPath (Join-Path $projectRoot 'models') -Destination $portablePath -Recurse -Force
Copy-Item -LiteralPath (Join-Path $projectRoot 'README.md') -Destination $portablePath -Force
Copy-Item -LiteralPath (Join-Path $projectRoot 'licenses') -Destination $portablePath -Recurse -Force
Copy-Item -LiteralPath (Join-Path $projectRoot 'scripts\Probar-Compatibilidad.cmd') -Destination $portablePath -Force
Copy-Item -LiteralPath (Join-Path $projectRoot 'diagnostics') -Destination $portablePath -Recurse -Force
Write-Output "Aplicación portable: $portablePath\Traductor.exe"
