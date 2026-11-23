$script:Latin1 = [Text.Encoding]::GetEncoding(28591)

function Read-Lines([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return ,@() }
    $text = [IO.File]::ReadAllText($Path, $script:Latin1)
    if ($text.EndsWith("`n")) { $text = $text.Substring(0, $text.Length - 1) }
    $lines = $text -split "`n" | ForEach-Object { $_.TrimEnd("`r") }
    return ,@($lines)
}

function Write-Lines([string]$Path, $Lines) {
    $part = "$Path.part"
    [IO.File]::WriteAllText($part, (($Lines -join "`r`n") + "`r`n"), $script:Latin1)
    Move-Item -LiteralPath $part -Destination $Path -Force
}

function Get-IniValue([string]$Path, [string]$Section, [string]$Key) {
    $in = $false
    foreach ($line in (Read-Lines $Path)) {
        if ($line.StartsWith('[')) { $in = ($line -eq "[$Section]"); continue }
        if ($in -and $line.StartsWith("$Key=")) { return $line.Substring($Key.Length + 1) }
    }
    return ''
}

function Set-IniValue([string]$Path, [string]$Section, [string]$Key, [string]$Value) {
    $out = New-Object Collections.Generic.List[string]
    $in = $false; $seen = $false; $done = $false
    foreach ($line in (Read-Lines $Path)) {
        if ($line.StartsWith('[')) {
            if ($in -and -not $done) { $out.Add("$Key=$Value"); $done = $true }
            $in = ($line -eq "[$Section]")
            if ($in) { $seen = $true }
        }
        if ($in -and $line.StartsWith("$Key=")) {
            if (-not $done) { $out.Add("$Key=$Value") }
            $done = $true
            continue
        }
        $out.Add($line)
    }
    if (-not $seen) { $out.Add("[$Section]") }
    if (-not $done) { $out.Add("$Key=$Value") }
    Write-Lines $Path $out
}

function Remove-IniSection([string]$Path, [string]$Section) {
    $out = New-Object Collections.Generic.List[string]
    $in = $false
    foreach ($line in (Read-Lines $Path)) {
        if ($line.StartsWith('[')) { $in = ($line -eq "[$Section]") }
        if (-not $in) { $out.Add($line) }
    }
    Write-Lines $Path $out
}

function Get-UserSetting([string]$Path, [string]$Key) {
    foreach ($line in (Read-Lines $Path)) {
        $word = $line -split '\s+'
        if ($word.Count -ge 3 -and $word[0] -eq 'sets' -and $word[1] -eq $Key) { return $word[2].Replace('"', '') }
    }
    return ''
}

function Set-UserSetting([string]$Path, [string]$Key, [string]$Value) {
    $out = New-Object Collections.Generic.List[string]
    $done = $false
    foreach ($line in (Read-Lines $Path)) {
        $word = $line -split '\s+'
        if ($word.Count -ge 2 -and $word[0] -eq 'sets' -and $word[1] -eq $Key) {
            if ($Value -ne '' -and -not $done) { $out.Add("sets $Key `"$Value`"") }
            $done = $true
            continue
        }
        $out.Add($line)
    }
    if ($Value -ne '' -and -not $done) { $out.Add("sets $Key `"$Value`"") }
    Write-Lines $Path $out
}

function Test-Sha256([string]$Path, [string]$Sha) {
    (Test-Path -LiteralPath $Path) -and ((Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash -eq $Sha.ToUpperInvariant())
}

function Invoke-Checked([string]$Exe, [string[]]$Arguments) {
    & $Exe @Arguments | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "$(Split-Path -Leaf $Exe) failed with exit code $LASTEXITCODE" }
}

function Test-Junction([string]$Path) {
    $item = Get-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
    return [bool]($item -and ($item.Attributes -band [IO.FileAttributes]::ReparsePoint))
}

function Remove-Junction([string]$Path) {
    if (Test-Junction $Path) { [IO.Directory]::Delete($Path, $false) }
}

function Set-Junction([string]$Path, [string]$Target) {
    Remove-Junction $Path
    New-Item -ItemType Junction -Path $Path -Target $Target | Out-Null
}

function Test-HdSetComplete([string]$Here, [string]$Python, [string]$Dir) {
    if (-not (Test-Path -LiteralPath (Join-Path $Dir 'manifest.json'))) { return $false }
    if (-not (Test-Path -LiteralPath $Python)) { return $false }
    $ErrorActionPreference = 'Continue'
    & $Python -I -B (Join-Path $Here 'tools\upscale-textures.py') --check --out $Dir 2>$null | Out-Null
    return ($LASTEXITCODE -eq 0)
}
