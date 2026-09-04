<#
.SYNOPSIS
  Run the whole Kinetiq v3 live prototype LOCALLY with a real webcam -- API + PWA, one command.

.DESCRIPTION
  Starts two processes and leaves them running until you press Ctrl+C:
    1. prototype_api  (this repo)          -> http://localhost:<ApiPort>
    2. kinetiq-demo3  (the sibling PWA repo) -> http://localhost:<PwaPort>

  It sets PROTOTYPE_API_CORS_ORIGINS to the PWA's local origin(s) so the browser's CORS check
  passes, waits for /health, and prints the URL to open.

  WHY THIS WORKS WITHOUT HTTPS: http://localhost (and http://127.0.0.1) is a SECURE CONTEXT by
  browser spec, so getUserMedia/camera works and there is no mixed-content problem -- an HTTP page
  calling an HTTP API is same-scheme. That is only true for localhost; the moment you want this on
  a PHONE (a different device, reached by LAN IP or a public URL) both sides must be HTTPS -- see
  ../../../../kinetiq v3/DEPLOY_RUNBOOK.md.

  Needs an internet connection on first run: the PWA fetches the MediaPipe pose model from a CDN.

.PARAMETER ApiPort
  Port for prototype_api. Default 8000.

.PARAMETER PwaPort
  Port for the kinetiq-demo3 static server. Default 8080.

.PARAMETER Demo3Path
  Path to the kinetiq-demo3 repo. Defaults to the sibling checkout next to kinetiq-v2.

.EXAMPLE
  .\run_local.ps1
  .\run_local.ps1 -ApiPort 8001 -PwaPort 8081
#>
[CmdletBinding()]
param(
    [int]$ApiPort = 8000,
    [int]$PwaPort = 8080,
    [string]$Demo3Path
)

$ErrorActionPreference = 'Stop'

# --- resolve paths -----------------------------------------------------------------------------
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path   # .../evals/gate0/prototype_api
$Gate0Dir  = Split-Path -Parent $ScriptDir                      # .../evals/gate0
$RepoRoot  = Split-Path -Parent (Split-Path -Parent $Gate0Dir)  # .../kinetiq-v2
$Workspace = Split-Path -Parent $RepoRoot                       # .../product-workspace

if (-not $Demo3Path) { $Demo3Path = Join-Path $Workspace 'kinetiq-demo3' }

if (-not (Test-Path (Join-Path $Demo3Path 'index.html'))) {
    Write-Host "ERROR: kinetiq-demo3 not found at: $Demo3Path" -ForegroundColor Red
    Write-Host "       (looked for index.html there). kinetiq-demo3 is a SEPARATE git repo that" -ForegroundColor Red
    Write-Host "       normally sits next to kinetiq-v2. Pass -Demo3Path <path> to point at it." -ForegroundColor Red
    exit 1
}

# --- find python -------------------------------------------------------------------------------
$Py = $null
foreach ($candidate in @('python', 'py')) {
    try { & $candidate --version *> $null; if ($LASTEXITCODE -eq 0) { $Py = $candidate; break } } catch { }
}
if (-not $Py) {
    Write-Host "ERROR: no 'python' or 'py' on PATH. Install Python 3.12+ and re-run." -ForegroundColor Red
    exit 1
}

# --- fail early on ports already in use --------------------------------------------------------
foreach ($p in @(@{n='API'; v=$ApiPort}, @{n='PWA'; v=$PwaPort})) {
    $inUse = Get-NetTCPConnection -State Listen -LocalPort $p.v -ErrorAction SilentlyContinue
    if ($inUse) {
        Write-Host "ERROR: port $($p.v) ($($p.n)) is already in use." -ForegroundColor Red
        Write-Host "       Stop whatever is on it, or re-run with -$($p.n)Port <other>." -ForegroundColor Red
        exit 1
    }
}

# --- CORS: allow BOTH localhost and 127.0.0.1 forms of the PWA origin ---------------------------
# They are DIFFERENT origins to the browser. Allowing both means it works whichever one you type.
$env:PROTOTYPE_API_CORS_ORIGINS = "http://localhost:$PwaPort,http://127.0.0.1:$PwaPort"

Write-Host ""
Write-Host "Kinetiq v3 live prototype -- LOCAL run" -ForegroundColor Cyan
Write-Host "  API  : $Gate0Dir"
Write-Host "  PWA  : $Demo3Path"
Write-Host "  CORS : $env:PROTOTYPE_API_CORS_ORIGINS"
Write-Host ""

$procs = @()
try {
    # --- 1. prototype_api ----------------------------------------------------------------------
    # Same invocation shape as the container CMD (uvicorn console entry, CWD=evals/gate0 so that
    # `import gate_config` / `detector.*` / `golden_loader` resolve).
    Write-Host "Starting prototype_api on http://localhost:$ApiPort ..." -ForegroundColor Yellow
    $api = Start-Process -FilePath $Py `
        -ArgumentList @('-m', 'uvicorn', 'prototype_api.main:app', '--host', '127.0.0.1', '--port', "$ApiPort") `
        -WorkingDirectory $Gate0Dir -PassThru -NoNewWindow
    $procs += $api

    # --- 2. kinetiq-demo3 static server ---------------------------------------------------------
    Write-Host "Starting kinetiq-demo3 on http://localhost:$PwaPort ..." -ForegroundColor Yellow
    $pwa = Start-Process -FilePath $Py `
        -ArgumentList @('-m', 'http.server', "$PwaPort", '--bind', '127.0.0.1') `
        -WorkingDirectory $Demo3Path -PassThru -NoNewWindow
    $procs += $pwa

    # --- wait for the API to answer -------------------------------------------------------------
    $healthUrl = "http://127.0.0.1:$ApiPort/health"
    $ok = $false
    foreach ($attempt in 1..30) {
        Start-Sleep -Milliseconds 500
        if ($api.HasExited) { throw "prototype_api exited early (exit code $($api.ExitCode)) -- see its output above." }
        try {
            $r = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 3
            if ($r.status -eq 'ok') { $ok = $true; break }
        } catch { }
    }
    if (-not $ok) { throw "prototype_api did not answer $healthUrl within ~15s." }

    Write-Host ""
    Write-Host "  /health OK -- supported exercises: $($r.supported_exercises -join ', ')" -ForegroundColor Green
    Write-Host ""
    Write-Host "==================================================================" -ForegroundColor Green
    Write-Host "  OPEN THIS IN YOUR BROWSER:  http://localhost:$PwaPort" -ForegroundColor Green
    Write-Host "==================================================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "  First time only -- on the home screen, paste this into 'API URL' and Save:"
    Write-Host "      http://localhost:$ApiPort" -ForegroundColor Cyan
    Write-Host "  (stored in this browser's localStorage; it overrides config.js, so setting it"
    Write-Host "   here does NOT disturb the deployed Render URL baked into config.js.)"
    Write-Host ""
    Write-Host "  Then: allow camera -> pick Squat -> Start -> ~5 reps -> Stop -> Validate"
    Write-Host "        -> enter your real rep count -> Summary -> Export bundle (.zip)"
    Write-Host ""
    Write-Host "  Full click-by-click + how to score the export: prototype_api/README.md"
    Write-Host "  section 'Running the whole prototype locally (real webcam)'."
    Write-Host ""
    Write-Host "  Press Ctrl+C to stop both servers." -ForegroundColor Yellow
    Write-Host ""

    while ($true) {
        Start-Sleep -Seconds 1
        if ($api.HasExited) { Write-Host "prototype_api exited (code $($api.ExitCode))." -ForegroundColor Red; break }
        if ($pwa.HasExited) { Write-Host "PWA static server exited (code $($pwa.ExitCode))." -ForegroundColor Red; break }
    }
}
finally {
    Write-Host ""
    Write-Host "Shutting down..." -ForegroundColor Yellow
    foreach ($p in $procs) {
        if ($p -and -not $p.HasExited) {
            try { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue } catch { }
        }
    }
    Remove-Item Env:\PROTOTYPE_API_CORS_ORIGINS -ErrorAction SilentlyContinue
    Write-Host "Stopped." -ForegroundColor Yellow
}
