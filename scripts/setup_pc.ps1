# One-time setup for daily sourcing on Sam's Windows PC (see docs/SOURCING.md).
# In PowerShell, from the folder where you want the project:
#   powershell -ExecutionPolicy Bypass -File setup_pc.ps1        (or run it from inside the repo)
# It installs nothing system-wide except Python packages, sends nothing to anyone,
# and never touches your keys: you paste them into .env yourself.

$ErrorActionPreference = "Stop"
$branch = "claude/tender-ritchie-1yitvw"

foreach ($tool in "git", "python") {
  if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
    Write-Host "Missing: $tool. Install it first (git-scm.com / python.org, tick 'Add to PATH'), then rerun." -ForegroundColor Red
    exit 1
  }
}

# 1. Get the code (clone if needed, otherwise update)
if (Test-Path ".git") { $repo = (Get-Location).Path }
elseif (Test-Path "instagram-lead-pipeline\.git") { $repo = (Resolve-Path "instagram-lead-pipeline").Path }
else {
  git clone https://github.com/samvexbusiness-sudo/instagram-lead-pipeline
  $repo = (Resolve-Path "instagram-lead-pipeline").Path
}
Set-Location $repo
git fetch origin $branch
git checkout $branch
git pull --ff-only origin $branch

# 2. Python packages
python -m pip install -U yt-dlp requests anthropic

# 3. .env for your keys (never overwritten if it already exists)
if (-not (Test-Path ".env")) {
  Copy-Item ".env.example" ".env"
  Write-Host "Created .env - paste your keys into it." -ForegroundColor Yellow
} else {
  Write-Host ".env already exists, left as is."
}

# 4. Quick checks (free, offline)
python -m unittest discover tests
yt-dlp --version
python run.py status

Write-Host ""
Write-Host "Setup done in $repo" -ForegroundColor Green
Write-Host "Next:"
Write-Host "  1. Open .env in Notepad and paste NOTION_TOKEN, ANTHROPIC_API_KEY, APIFY_TOKEN (HUNTER_API_KEY optional)."
Write-Host "  2. In Notion: Outreach HQ -> ... -> Connections -> add your integration."
Write-Host "  3. Dry run (writes nothing to Notion):  python run.py source --max-channels 40 --approve-spend"
