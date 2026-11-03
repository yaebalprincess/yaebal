[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$ReaderGroup,
    [string]$NetworkRoot = ""
)
$ErrorActionPreference = "Stop"
if (-not $NetworkRoot) { $NetworkRoot = Split-Path -Parent $MyInvocation.MyCommand.Path }
$Identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$Principal = New-Object Security.Principal.WindowsPrincipal($Identity)
if (-not $Principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Run PowerShell as the system administrator."
}
$News = Join-Path $NetworkRoot "UPDATE_NEWS.txt"
if (-not (Test-Path -LiteralPath $News)) { throw "UPDATE_NEWS.txt was not found." }
$Resolved = (Resolve-Path -LiteralPath $News).Path
# Change this TXT only. Keep a recoverable copy of the old ACL.
$Backup = $Resolved + ".acl." + (Get-Date -Format "yyyyMMddHHmmss") + ".txt"
$CurrentAcl = Get-Acl -LiteralPath $Resolved
[IO.File]::WriteAllText($Backup, $CurrentAcl.Sddl, [Text.Encoding]::UTF8)
$Acl = New-Object Security.AccessControl.FileSecurity
$Administrators = New-Object Security.Principal.SecurityIdentifier("S-1-5-32-544")
$System = New-Object Security.Principal.SecurityIdentifier("S-1-5-18")
$Readers = New-Object Security.Principal.NTAccount($ReaderGroup)
$Acl.SetAccessRuleProtection($true, $false)
$Acl.SetOwner($Administrators)
$Acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule($Administrators,"FullControl","Allow")))
$Acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule($System,"FullControl","Allow")))
$Acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule($Readers,"ReadAndExecute","Allow")))
Set-Acl -LiteralPath $Resolved -AclObject $Acl
Write-Host "News protected. Readers: $ReaderGroup. Editing: Windows Administrators. Previous ACL: $Backup"
Write-Host "On SMB, configure these rights on the file server and restrict deletion/creation in the parent folder as well."
