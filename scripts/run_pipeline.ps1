$ErrorActionPreference = "Stop"
Set-Location -Path (Split-Path -Parent $PSScriptRoot)

python .\scripts\apex-wiki.py lint
python .\scripts\apex-wiki.py graph
python .\scripts\apex-wiki.py dashboards

