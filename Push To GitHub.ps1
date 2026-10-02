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
    Write-Host "  1. Add the email secrets"
    Write-Host "     $url".Replace(".git", "") + "/settings/secrets/actions"
    Write-Host "     PDL_SMTP_HOST  = smtp.gmail.com"
    Write-Host "     PDL_SMTP_PORT  = 587"
    Write-Host "     PDL_SMTP_USER  = your Google address"
    Write-Host "     PDL_SMTP_PASS  = your 16-character app password, no spaces"
    Write-Host "     PDL_SMTP_FROM  = your Google address"
    Write-Host "     PDL_SMTP_TO    = who to notify"
    Write-Host ""
    Write-Host "  2. Test it: the Actions tab, then 'Run workflow'"
    Write-Host ""
    Write-Host "  A green tick and 'No changes in the rescue glucagon class' means"
    Write-Host "  it works. From tomorrow it runs on its own, laptop on or off."
    Write-Host ""
    Write-Host "Press Enter to close."
    [void](Read-Host)
}
finally {
    Pop-Location
}
