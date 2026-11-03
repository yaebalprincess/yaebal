[CmdletBinding()]
param([string]$NetworkRoot = "")
$ErrorActionPreference = "Stop"
if (-not $NetworkRoot) { $NetworkRoot = Split-Path -Parent $MyInvocation.MyCommand.Path }
$NetworkRoot = (Resolve-Path -LiteralPath $NetworkRoot).Path
# Elevated accounts may not see the user's mapped drive. Prefer its UNC root.
$DriveLetter = [IO.Path]::GetPathRoot($NetworkRoot).TrimEnd('\').TrimEnd(':')
if ($DriveLetter.Length -eq 1) {
    $Drive = Get-PSDrive -Name $DriveLetter -ErrorAction SilentlyContinue
    if ($Drive -and $Drive.DisplayRoot) {
        $NetworkRoot = $Drive.DisplayRoot.TrimEnd('\') + $NetworkRoot.Substring(2)
    }
}
$Identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$Principal = New-Object Security.Principal.WindowsPrincipal($Identity)
if (-not $Principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    # UAC requests the administrator's Windows account. No password is saved.
    $Script = Join-Path $NetworkRoot "Edit_Update_News.ps1"
    $Arguments = '-NoProfile -ExecutionPolicy RemoteSigned -File "' + $Script + '" -NetworkRoot "' + $NetworkRoot + '"'
    Start-Process powershell.exe -Verb RunAs -ArgumentList $Arguments -Wait
    exit
}
$News = Join-Path $NetworkRoot "UPDATE_NEWS.txt"
if (-not (Test-Path -LiteralPath $News)) { throw "UPDATE_NEWS.txt was not found in $NetworkRoot" }
Start-Process notepad.exe -ArgumentList ('"' + $News + '"') -Wait
