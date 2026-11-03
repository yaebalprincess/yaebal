[CmdletBinding()]
param([switch]$ForceUpdate)
$ErrorActionPreference = "Stop"

function Popup([string]$Text,[int]$Icon=64) {
    try { $w=New-Object -ComObject WScript.Shell; $null=$w.Popup($Text,0,"SmartOrder",$Icon) } catch {}
}
function Resolve-Unc([string]$Path) {
    $full=[IO.Path]::GetFullPath($Path)
    if ($full -match '^([A-Za-z]):\\(.*)$') {
        $drive=$Matches[1]; $tail=$Matches[2]
        try {
            $ps=Get-PSDrive -Name $drive -ErrorAction Stop
            if ($ps.DisplayRoot) { return (Join-Path $ps.DisplayRoot $tail).TrimEnd('\') }
        } catch {}
    }
    return $full.TrimEnd('\')
}
try {
    $Here=Split-Path -Parent $MyInvocation.MyCommand.Path
    if (Test-Path (Join-Path $Here "SmartOrderApp.exe")) {
        $SourceDirMapped=$Here; $NetworkRootMapped=Split-Path -Parent $Here
    } elseif (Test-Path (Join-Path $Here "SmartOrderApp\SmartOrderApp.exe")) {
        $NetworkRootMapped=$Here; $SourceDirMapped=Join-Path $Here "SmartOrderApp"
    } elseif (Test-Path (Join-Path $Here "release\SmartOrderApp\SmartOrderApp.exe")) {
        $NetworkRootMapped=Join-Path $Here "release"; $SourceDirMapped=Join-Path $Here "release\SmartOrderApp"
    } else { throw "SmartOrderApp.exe not found. Build the Windows release first." }
    $NetworkRoot=Resolve-Unc $NetworkRootMapped
    $SourceDir=Resolve-Unc $SourceDirMapped
    $ServerLauncher=Join-Path $SourceDir "SmartOrder.exe"
    if (-not (Test-Path -LiteralPath $ServerLauncher)) { throw "Native SmartOrder.exe launcher not found." }
    if (-not (Test-Path (Join-Path $SourceDir "manifest.sha256"))) { throw "manifest.sha256 not found. Use a complete release." }

    $Sha=[Security.Cryptography.SHA256]::Create()
    try { $ShareKey=([BitConverter]::ToString($Sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($NetworkRoot.ToLowerInvariant())))).Replace('-','').ToLowerInvariant().Substring(0,16) }
    finally { $Sha.Dispose() }
    $UserBase=Join-Path $env:LOCALAPPDATA "SmartOrder"
    $LauncherDir=Join-Path (Join-Path $UserBase "Launcher") $ShareKey
    New-Item -ItemType Directory -Force -Path $LauncherDir | Out-Null
    $LocalLauncher=Join-Path $LauncherDir "SmartOrder.exe"
    # Only this small launcher is installed here. It prepares the verified,
    # immutable local GUI cache and checks server version/build on each launch.
    $TempLauncher=Join-Path $LauncherDir ("SmartOrder."+[Guid]::NewGuid().ToString("N")+".tmp")
    try {
        Copy-Item -LiteralPath $ServerLauncher -Destination $TempLauncher -Force
        $Expected=(Get-FileHash -LiteralPath $ServerLauncher -Algorithm SHA256).Hash
        if ((Get-FileHash -LiteralPath $TempLauncher -Algorithm SHA256).Hash -ne $Expected) { throw "Launcher copy checksum mismatch." }
        Move-Item -LiteralPath $TempLauncher -Destination $LocalLauncher -Force
    } finally { if(Test-Path -LiteralPath $TempLauncher){Remove-Item -LiteralPath $TempLauncher -Force} }
    [IO.File]::WriteAllText((Join-Path $LauncherDir "network_root.txt"),$NetworkRoot,[Text.Encoding]::UTF8)

    $desktop=[Environment]::GetFolderPath("Desktop")
    $shortcut=Join-Path $desktop "SmartOrder.lnk"
    $ws=New-Object -ComObject WScript.Shell
    $lnk=$ws.CreateShortcut($shortcut)
    $lnk.TargetPath=$LocalLauncher
    $lnk.WorkingDirectory=$LauncherDir
    $lnk.IconLocation=$LocalLauncher+",0"
    $lnk.Description="SmartOrder local launcher with verified updates"
    $lnk.Save()
    # Per-user association; normal installation needs no administrator rights.
    $Classes="HKCU:\Software\Classes"
    New-Item -Path ($Classes+"\.sorder") -Force | Out-Null
    Set-Item -Path ($Classes+"\.sorder") -Value "SmartOrder.Order"
    New-Item -Path ($Classes+"\SmartOrder.Order\shell\open\command") -Force | Out-Null
    Set-Item -Path ($Classes+"\SmartOrder.Order") -Value "Smart Order work order"
    Set-Item -Path ($Classes+"\SmartOrder.Order\shell\open\command") -Value ('"'+$LocalLauncher+'" "%1"')
    New-Item -Path ($Classes+"\SmartOrder.Order\DefaultIcon") -Force | Out-Null
    Set-Item -Path ($Classes+"\SmartOrder.Order\DefaultIcon") -Value ('"'+$LocalLauncher+'",0')
    Start-Process -FilePath $LocalLauncher -WorkingDirectory $LauncherDir
    Popup "SmartOrder installed. Use the desktop shortcut: GUI is local, databases remain on the server." 64
} catch {
    Popup ("SmartOrder installation failed.`n`n"+$_.Exception.Message) 16
    throw
}
