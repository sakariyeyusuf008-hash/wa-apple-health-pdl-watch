# Pushes this folder to a new GitHub repository.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File ".\Push To GitHub.ps1"
#
# Works from any directory. Handles the fiddly bits: the noreply commit address
# has to contain your GitHub username, and the remote has to point at the repo
# you created.

$ErrorActionPreference = "Stop"

$git = @(
    "$env:ProgramFiles\Git\cmd\git.exe",
    "${env:ProgramFiles(x86)}\Git\cmd\git.exe",
    "$env:LOCALAPPDATA\Programs\Git\cmd\git.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $git) {
    Write-Host "Git not found. Install it from https://git-scm.com/download/win" -ForegroundColor Red
    exit 1
}

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $here

try {
    Write-Host ""
    Write-Host "STEP 1 of 2 - create the repository on GitHub"
    Write-Host ""
    Write-Host "  Open https://github.com/new"
    Write-Host ""
    Write-Host "    Repository name : wa-apple-health-pdl-watch"
    Write-Host "    Visibility      : Public"
    Write-Host "    Do NOT tick 'Add a README' - it creates a branch that will"
    Write-Host "    conflict with this one."
    Write-Host ""

    $user = Read-Host "  Your GitHub username (the part after github.com/)"
    if (-not $user) { throw "No username given." }
    $user = $user.Trim().TrimStart('@').Trim()

    $repo = Read-Host "  Repository name [wa-apple-health-pdl-watch]"
    if (-not $repo) { $repo = "wa-apple-health-pdl-watch" }
    $repo = $repo.Trim()

    $url = "https://github.com/$user/$repo.git"

    Write-Host ""
    Write-Host "  Committing as $user (noreply address, so nothing personal is published)"

    # Repo-local, not global: this does not change how any other repo commits.
    & $git config user.name  $user
    & $git config user.email "$user@users.noreply.github.com"

    & $git add -A
    if (-not $(& $git diff --cached --quiet)) {
        & $git commit -q -m "WA Apple Health PDL watcher"
        Write-Host "  Committed."
    }
    else {
        Write-Host "  Nothing new to commit."
    }

    if ((& $git remote) -contains "origin") {
        & $git remote set-url origin $url
        Write-Host "  Updated the existing 'origin'."
    }
    else {
        & $git remote add origin $url
    }
    Write-Host "  Remote set to $url"
    Write-Host ""
    Write-Host "STEP 2 of 2 - pushing"
    Write-Host ""
    Write-Host "  GitHub will ask for your username, then a password."
    Write-Host "  For the password use a PERSONAL ACCESS TOKEN, not your account"
    Write-Host "  password. Create one at https://github.com/settings/tokens with"
    Write-Host "  the 'repo' scope. If this fails, open the URL above in a browser"
    Write-Host "  and sign in first."
    Write-Host ""

    & $git push -u origin main
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "The push did not go through. Nothing is lost - everything is"
        Write-Host "committed locally and you can retry whenever you like."
        throw "git push failed"
    }

    Write-Host ""
    Write-Host "Pushed." -ForegroundColor Green
    Write-Host ""
    Write-Host "  Nothing left to configure. No secrets, no passwords."
    Write-Host ""
    Write-Host "  The job runs by itself every morning and posts any change to"
    Write-Host "  an issue in the repo. GitHub emails you when that happens."
    Write-Host ""
    Write-Host "  It will next run at 15:20 UTC - 08:20 Pacific today if that"
    Write-Host "  has not passed, otherwise tomorrow morning."
    Write-Host ""
    Write-Host "  Optional, if you want to prove it works now:"
    Write-Host "    $url".Replace(".git", "") + "/actions"
    Write-Host "    click 'WA Apple Health PDL Watch', then 'Run workflow'"
    Write-Host ""
    Write-Host "  Optional, to be sure GitHub emails you:"
    Write-Host "    open the repo, click 'Watch' top right, choose 'Custom',"
    Write-Host "    tick 'Issues' only. That is what triggers the notification."
    Write-Host ""
    Write-Host "Press Enter to close."
    [void](Read-Host)
}
finally {
    Pop-Location
}
