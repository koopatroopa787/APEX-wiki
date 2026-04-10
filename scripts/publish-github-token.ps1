param(
  [string]$Owner = "yashk",
  [string]$Repo = "APEX-wiki",
  [switch]$Private
)

$ErrorActionPreference = "Stop"
Set-Location -Path (Split-Path -Parent $PSScriptRoot)

if (-not $env:GH_TOKEN -and -not $env:GITHUB_TOKEN) {
  throw "Set GH_TOKEN or GITHUB_TOKEN first."
}
$token = if ($env:GH_TOKEN) { $env:GH_TOKEN } else { $env:GITHUB_TOKEN }
$isPrivate = [bool]$Private

$headers = @{
  Authorization = "token $token"
  Accept = "application/vnd.github+json"
  "X-GitHub-Api-Version" = "2022-11-28"
}

$body = @{
  name = $Repo
  private = $isPrivate
  description = "APEX-wiki Obsidian + MCP knowledge graph system"
} | ConvertTo-Json

try {
  Invoke-RestMethod -Method Post -Uri "https://api.github.com/user/repos" -Headers $headers -Body $body -ContentType "application/json" | Out-Null
} catch {
  $msg = $_.Exception.Message
  if ($msg -notmatch "422") { throw }
}

$tokenRemote = "https://$token@github.com/$Owner/$Repo.git"
$remotes = git remote
if ($LASTEXITCODE -eq 0 -and ($remotes -contains "origin")) {
  git remote remove origin
}
git remote add origin $tokenRemote
git push -u origin master
git remote set-url origin "https://github.com/$Owner/$Repo.git"
