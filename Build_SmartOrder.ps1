[CmdletBinding()]
param(
    [switch]$Clean,
    [string]$ResourcesDir = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$VersionFile = Join-Path $Root "version.txt"
if (-not (Test-Path $VersionFile)) { throw "version.txt not found: $VersionFile" }
$Version = (Get-Content $VersionFile -Raw).Trim()
$BuildVenv = Join-Path $env:LOCALAPPDATA "SmartOrder\build-venv-py312"
$Python = Join-Path $BuildVenv "Scripts\python.exe"

if (-not (Test-Path $Python)) {
    Write-Host "Creating Python 3.12 build environment..." -ForegroundColor Cyan
    & py.exe -3.12 -m venv $BuildVenv
    if ($LASTEXITCODE -ne 0) { throw "Python 3.12 venv creation failed." }
}

Write-Host "Installing/updating build dependencies..." -ForegroundColor Cyan
& $Python -m pip install --disable-pip-version-check --no-cache-dir -r (Join-Path $Root "requirements-build.txt")
if ($LASTEXITCODE -ne 0) { throw "Build dependency installation failed." }

# Resource lookup order. The project ZIP intentionally does not fabricate user artwork.
# Existing SmartOrder resources are discovered and then bundled into both PyInstaller
# internal data and an external resources fallback next to the EXE.
if (-not $ResourcesDir) {
    $Candidates = @()
    if ($env:SMARTORDER_RESOURCES_DIR) { $Candidates += $env:SMARTORDER_RESOURCES_DIR }
    $Candidates += (Join-Path $Root "resources")
    $Parent = Split-Path -Parent $Root
    if ($Parent) { $Candidates += (Join-Path $Parent "resources") }
    $Candidates += "C:\smart order\resources"
    $ResourcesDir = $Candidates | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
}

if (-not $ResourcesDir -or -not (Test-Path $ResourcesDir)) {
    throw "SmartOrder resources folder was not found. Put the original assets in C:\smart order\resources or pass -ResourcesDir <path>."
}
$ResourcesDir = (Resolve-Path $ResourcesDir).Path
Write-Host ("Resources: " + $ResourcesDir) -ForegroundColor Cyan

$RequiredResources = @(
    "login_background.gif",
    "loading2.gif",
    "smartorder_app_icon.ico"
)
$Missing = @()
foreach ($Name in $RequiredResources) {
    if (-not (Test-Path (Join-Path $ResourcesDir $Name))) { $Missing += $Name }
}
if ($Missing.Count -gt 0) {
    throw ("Required SmartOrder resources are missing: " + ($Missing -join ", ") + ". Build stopped so GIFs/icon cannot silently disappear.")
}

$Icon = Join-Path $ResourcesDir "smartorder_app_icon.ico"
$LogoCandidates = @(
    "smartorder_logo_icon_light.png",
    "smartorder_logo_icon.png",
    "smartorder_logo_white.png",
    "smartorder_logo.png"
)
$LogoFound = $false
foreach ($Name in $LogoCandidates) {
    if (Test-Path (Join-Path $ResourcesDir $Name)) { $LogoFound = $true; break }
}
if (-not $LogoFound) {
    Write-Host "WARNING: no SmartOrder logo PNG found. The UI will use its fallback logo." -ForegroundColor Yellow
}

if ($Clean) {
    foreach ($Folder in @("build","dist","release")) {
        $Path=Join-Path $Root $Folder
        if(Test-Path $Path){Remove-Item $Path -Recurse -Force}
    }
}

Write-Host "Building local SmartOrderApp (PyInstaller onedir)..." -ForegroundColor Cyan
$AppArgs=@("--noconfirm","--windowed","--onedir","--noupx","--name","SmartOrderApp")
if($Clean){$AppArgs+="--clean"}
$AppArgs+=@("--add-data",($ResourcesDir+";resources"))
$AppArgs+=@("--add-data",((Join-Path $Root "smartorder\glass")+";smartorder\glass"))
$AppArgs+=@("--hidden-import","PyQt5.QtWebEngineWidgets","--hidden-import","PyQt5.QtWebChannel","--hidden-import","PyQt5.QtPrintSupport")
$AppArgs+=@("--icon",$Icon)
$AppArgs+=@("--add-data",((Join-Path $Root "UPDATE_NEWS.txt")+";."))
$AppArgs+=@("--add-data",((Join-Path $Root "README_RU.txt")+";."))
$AppArgs+=(Join-Path $Root "main.py")
& $Python -m PyInstaller @AppArgs
if($LASTEXITCODE -ne 0){throw "PyInstaller SmartOrderApp build failed."}

$Dist = Join-Path $Root "dist\SmartOrderApp"
if (-not (Test-Path (Join-Path $Dist "SmartOrderApp.exe"))) { throw "SmartOrderApp.exe was not created." }

# External fallback copy as well as PyInstaller --add-data. This makes GIF/icon lookup
# deterministic even if PyInstaller changes its onedir internal layout.
$DistResources = Join-Path $Dist "resources"
if (Test-Path $DistResources) { Remove-Item $DistResources -Recurse -Force }
New-Item -ItemType Directory -Force -Path $DistResources | Out-Null
Copy-Item (Join-Path $ResourcesDir "*") $DistResources -Recurse -Force

foreach ($Name in $RequiredResources) {
    if (-not (Test-Path (Join-Path $DistResources $Name))) {
        throw ("Resource verification failed after build: " + $Name)
    }
}

$Release=Join-Path $Root "release\SmartOrderApp"
if(Test-Path $Release){Remove-Item $Release -Recurse -Force}
New-Item -ItemType Directory -Force -Path (Split-Path $Release -Parent) | Out-Null
Copy-Item $Dist $Release -Recurse -Force
Set-Content (Join-Path $Release "version.txt") $Version -Encoding ASCII
$BuildId=$Version+"|"+(Get-Date).ToUniversalTime().ToString("yyyyMMddHHmmss")
Set-Content (Join-Path $Release "build.id") $BuildId -Encoding ASCII

foreach ($Name in @("UPDATE_NEWS.txt","Edit_Update_News.ps1","Edit_Update_News.cmd","Protect_Update_News.ps1","Install_and_Start_SmartOrder.ps1","Install_and_Start_SmartOrder.cmd","README_RU.txt")) {
    $Target=Join-Path (Split-Path $Release -Parent) $Name
    if ($Name -ne "UPDATE_NEWS.txt" -or -not (Test-Path -LiteralPath $Target)) { Copy-Item (Join-Path $Root $Name) $Target -Force }
}

Write-Host "Building native network launcher with SmartOrder icon..." -ForegroundColor Cyan
$candidates=@(
    (Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\csc.exe"),
    (Join-Path $env:WINDIR "Microsoft.NET\Framework\v4.0.30319\csc.exe")
)
$csc=$candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if(-not $csc){throw "C# compiler csc.exe was not found. .NET Framework 4.x is required."}
$LauncherExe=Join-Path $Release "SmartOrder.exe"
$CsArgs=@(
    "/nologo",
    "/target:winexe",
    "/optimize+",
    "/platform:anycpu",
    "/reference:System.Windows.Forms.dll",
    ("/out:"+$LauncherExe),
    ("/win32icon:"+$Icon),
    (Join-Path $Root "NativeLauncher.cs")
)
& $csc @CsArgs
if($LASTEXITCODE -ne 0 -or -not(Test-Path $LauncherExe)){throw "Native SmartOrder launcher build failed."}

Write-Host "Verifying release resources..." -ForegroundColor Cyan
foreach ($Name in $RequiredResources) {
    if (-not (Test-Path (Join-Path $Release ("resources\"+$Name)))) {
        throw ("Release resource verification failed: " + $Name)
    }
}

# SHA-256 manifest covers the complete app payload; the launcher verifies
# it in a staging directory before publishing a new local cache.
$ManifestLines = Get-ChildItem -LiteralPath $Release -File -Recurse |
    Where-Object { $_.Name -ne "manifest.sha256" } |
    Sort-Object FullName |
    ForEach-Object {
        $Relative = $_.FullName.Substring($Release.Length + 1).Replace('\', '/')
        $Hash = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        $Hash + " *" + $Relative
    }
[IO.File]::WriteAllLines((Join-Path $Release "manifest.sha256"), [string[]]$ManifestLines, [Text.Encoding]::UTF8)

Write-Host ""
Write-Host "BUILD COMPLETE" -ForegroundColor Green
Write-Host ("Release folder: "+$Release) -ForegroundColor Green
Write-Host "GIF resources: VERIFIED" -ForegroundColor Green
Write-Host "SmartOrderApp.exe icon source: VERIFIED" -ForegroundColor Green
Write-Host "SmartOrder.exe icon source: VERIFIED" -ForegroundColor Green
Write-Host ""
Write-Host "Copy the ENTIRE release folder (app, installer, news and guide) to the server root." -ForegroundColor Cyan
Write-Host "Daily fastest start: desktop shortcut created by Install_and_Start_SmartOrder.ps1" -ForegroundColor Cyan
Write-Host "Direct server start: SmartOrder.exe" -ForegroundColor Cyan
Write-Host "Do not run SmartOrderApp.exe directly from the network share." -ForegroundColor Yellow
