#!/usr/bin/env pwsh
# Copyright 2024 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

<#
.SYNOPSIS
  Installs the `science.exe` executable.

.DESCRIPTION
  Downloads and installs the latest version of the science executable by default.
  The download is first verified against the published checksum before being installed.
  The install process will add the science executable to your user PATH environment variable
  if needed as well as to the current shell session PATH for immediate use.

.PARAMETER Help
  Display this help message.

.PARAMETER BinDir
  The directory to install the science binary in.

.PARAMETER NoModifyPath
  Do not automatically add -BinDir to the PATH.

.PARAMETER Version
  The version of the science binary to install, the latest version by default.
  The available versions can be seen at:
    https://github.com/a-scie/lift/releases

.INPUTS
  None

.OUTPUTS
  The path of the installed science executable.

.LINK
  Docs https://science.scie.app

.LINK
  Chat https://scie.app/discord

.LINK
  Source https://github.com/a-scie/lift
#>

param (
  [Alias('h')]
  [switch]$Help,

  [Alias('d')]
  [string]$BinDir = (
    # N.B.: PowerShell>=6 supports varargs, but to retain compatibility with older PowerShell, we
    # just Join-Path twice.
    # See: https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.management/join-path?view=powershell-7.4#-additionalchildpath
    Join-Path (
      Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'Programs'
    ) 'Science'
  ),

  [switch]$NoModifyPath,

  [Alias('V')]
  [string]$Version = 'latest/download'
)

$ErrorActionPreference = 'Stop'

function Green {
  [Parameter(Position=0)]
  param ($Message)

  Write-Host $Message -ForegroundColor Green
}

function Warn {
  [Parameter(Position=0)]
  param ($Message)

  Write-Host $Message -ForegroundColor Yellow
}

function Die {
  [Parameter(Position=0)]
  param ($Message)

  Write-Host $Message -ForegroundColor Red
  exit 1
}

function TemporaryDirectory {
  $Tmp = [System.IO.Path]::GetTempPath()
  $Unique = (New-Guid).ToString('N')
  $TempDir = New-Item -ItemType Directory -Path (Join-Path $Tmp $Unique)
  trap {
    Remove-Item $TempDir -Recurse
  }
  return $TempDir
}

function Fetch {
  param (
    [string]$Url,
    [string]$DestFile
  )

  Invoke-RestMethod -Uri $Url -OutFile $DestFile
}

function InstallFromUrl {
  param (
    [string]$Url,
    [string]$DestDir
  )

  $Sha256Url = "$Url.sha256"

  $Workdir = TemporaryDirectory
  $ScienceExeFile = Join-Path $Workdir 'science.exe'
  $Sha256File = Join-Path $Workdir 'science.exe.sha256'

  Fetch -Url $Url -DestFile $ScienceExeFile
  Fetch -Url $Sha256Url -DestFile $Sha256File
  Green 'Download completed successfully'

  $ExpectedHash = ((Get-Content $Sha256File).Trim().ToLower() -Split '\s+',2)[0]
  $ActualHash = (Get-FileHash $ScienceExeFile -Algorithm SHA256).Hash.ToLower()
  if ($ActualHash -eq $ExpectedHash) {
    Green "Download matched it's expected sha256 fingerprint, proceeding"
  } else {
    Die "Download from $Url did not match the fingerprint at $Sha256Url"
  }

  if (!(Test-Path $BinDir)) {
    New-Item $DestDir -ItemType Directory | Out-Null
  }
  Move-Item $ScienceExeFile $DestDir -Force
  Join-Path $BinDir 'science.exe'
}

if ($Help) {
  Get-Help -Detailed $PSCommandPath
  exit 0
}

$Version = switch ($Version) {
  'latest/download' { 'latest/download' }
  default { "download/v$Version" }
}

$Arch = switch -Wildcard ((Get-CimInstance Win32_operatingsystem).OSArchitecture) {
  'arm*' { 'aarch64' }
  default { 'x86_64' }
}

$DownloadURL = "https://github.com/a-scie/lift/releases/$Version/science-fat-windows-$Arch.exe"

Green "Download URL is: $DownloadURL"
$ScienceExe = InstallFromUrl -Url $DownloadURL -DestDir $BinDir

$User = [System.EnvironmentVariableTarget]::User
$Path = [System.Environment]::GetEnvironmentVariable('Path', $User)
if (!(";$Path;".ToLower() -like "*;$BinDir;*".ToLower())) {
  if ($NoModifyPath) {
    Warn "WARNING: $BinDir is not detected on `$PATH"
    Warn (
      "You'll either need to invoke $ScienceExe explicitly or else add $BinDir to your " +
      "PATH."
    )
  } else {
    [System.Environment]::SetEnvironmentVariable('Path', "$Path;$BinDir", $User)
    $Env:Path += ";$BinDir"
  }
}
