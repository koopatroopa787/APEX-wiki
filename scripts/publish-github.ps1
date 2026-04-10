param(
  [string]$Owner = "yashk",
  [string]$Repo = "APEX-wiki",
  [string]$Visibility = "public"
)

$ErrorActionPreference = "Stop"
Set-Location -Path (Split-Path -Parent $PSScriptRoot)

$gh = "C:\Program Files\GitHub CLI\gh.exe"
if (-not (Test-Path $gh)) {
  throw "GitHub CLI not found at $gh"
}

& $gh auth status | Out-Null
if ($LASTEXITCODE -ne 0) {
  throw "Run 'gh auth login' first, then rerun this script."
}

& $gh repo create "$Owner/$Repo" "--$Visibility" --source . --remote origin --push
