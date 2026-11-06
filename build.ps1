param([string]$Python='',[string]$OutputDir='')
$ErrorActionPreference='Stop'
$root=$PSScriptRoot
if(-not $Python){$Python=Join-Path $root '.venv\Scripts\python.exe'}
if(-not $OutputDir){$OutputDir=Join-Path $root 'outputs'}
$env:TEMP=Join-Path $root 'work\temp'
$env:TMP=$env:TEMP
$env:PYINSTALLER_CONFIG_DIR=Join-Path $root 'work\pyinstaller-cache'
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PATH="$(Split-Path $Python);$env:SystemRoot\System32;$env:SystemRoot"
New-Item -ItemType Directory -Force -Path $env:TEMP,$env:PYINSTALLER_CONFIG_DIR | Out-Null
& $Python -m PyInstaller --noconfirm --clean --onefile --windowed --noupx --name Reclip --icon "$root\src\resources\Reclip.ico" --add-data "$root\src\resources;resources" --paths "$root\src" --distpath $OutputDir --workpath "$root\work\build" --specpath "$root\work" "$root\src\main.py"
if($LASTEXITCODE -ne 0){throw 'Build failed'}
