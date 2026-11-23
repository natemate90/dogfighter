param(
    [string]$Res,
    [switch]$Windowed,
    [string]$Wrapper,
    [switch]$NoHdTextures,
    [switch]$Original,
    [ValidateSet(0, 2, 4)][int]$Smooth = 4,
    [switch]$GameIntros,
    [switch]$Setup,
    [switch]$NoFocusfix,
    [switch]$NoAutoJoystick,
    [switch]$MountCd,
    [switch]$Doctor,
    [switch]$Stop,
    [switch]$Help
)
Set-StrictMode -Version 2
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$Usage = @'
Usage: dogfighter.cmd [-Res WxH] [-Windowed] [-Wrapper dgvoodoo|none] [-NoHdTextures] [-Original]
                      [-Smooth 0|2|4] [-GameIntros] [-Setup] [-NoFocusfix] [-NoAutoJoystick] [-MountCd]
       dogfighter.cmd -Doctor | -Stop

Windows version of ./dogfighter. NOT TESTED ON WINDOWS YET; see docs\WINDOWS.md.

  (no option)     Full screen at the largest listed resolution that fits the
                  screen, 32-bit colour, the far draw distance, the larger
                  textures when hd-textures\ holds a complete set, and no intro
                  videos. With dgVoodoo2: 16x anisotropic filtering and 4x
                  smooth edges.
  -Res WxH        Use this game resolution in flight, e.g. -Res 1920x1080.
  -Windowed       Play in a window (dgVoodoo2 only).
  -Wrapper NAME   dgvoodoo (the default when setup fetched it) or none, which
                  uses Windows' own DirectDraw.
  -NoHdTextures   Use the game's own textures.
  -Original       16-bit colour and the game's own draw distance, textures,
                  filtering and edges.
  -Smooth N       Smooth edges with N samples (dgVoodoo2 only). 0 turns it off.
  -GameIntros     Let the game play its own intro videos. They are Indeo 5,
                  which Windows 10 and 11 block, so this may show nothing.
  -Setup          Show the game's setup dialog and wait for OK.
  -NoFocusfix     Start the game without the helper: no larger textures, and
                  the game plays its own intros.
  -NoAutoJoystick Leave the game's Joystick option as it is.
  -MountCd        Mount cd.iso as a CD drive while the game runs. Try this if
                  the game asks for its disc.
  -Doctor         Check the installation and list the controllers.
  -Stop           End a running game.
'@

if ($Help) { Write-Host $Usage; exit 0 }

$Here = $PSScriptRoot
. (Join-Path $Here 'tools\windows-common.ps1')
$Game = Join-Path $Here 'game'
$Build = Join-Path $Here 'build'
$Python = Join-Path $Here 'python\python.exe'
$Ini = Join-Path $Game 'system.ini'
$UserIni = Join-Path $Game 'user.ini'
$PictureBefore = Join-Path $Game 'dogfighter-picture-before.txt'
$HdDir = Join-Path $Here 'hd-textures'
$CacheLink = Join-Path $Game 'cache'
$FocusfixExe = Join-Path $Build 'focusfix.exe'
$FocushookDll = Join-Path $Build 'focushook.dll'
$JoylistExe = Join-Path $Build 'joylist.exe'
$DgVoodoo = Join-Path $Here 'wrappers\dgVoodoo2'
$WrapperFiles = 'DDraw.dll', 'D3DImm.dll'
$WrapperCard = 'dgVoodoo DX API Layer'
$Sizes = '2560x1600', '2560x1440', '1920x1200', '1920x1080', '1680x1050', '1600x1200', '1600x900', '1440x900',
    '1280x1024', '1280x960', '1280x800', '1280x720', '1024x768', '800x600', '640x480'
$Pictures = [ordered]@{ screen_depth = '32'; view_distance = '450'; detail_volumetriclight = '2'; view_portals = '5' }

if ($Res -and $Res -notmatch '^[0-9]+x[0-9]+$') { Write-Host "Bad size: $Res"; exit 2 }
if (-not $Wrapper) { $Wrapper = if (Test-Path -LiteralPath (Join-Path $DgVoodoo 'MS\x86\DDraw.dll')) { 'dgvoodoo' } else { 'none' } }
if ($Wrapper -notin 'dgvoodoo', 'none') { Write-Host "Bad wrapper: $Wrapper. Use dgvoodoo or none."; exit 2 }
if ($Windowed -and $Wrapper -ne 'dgvoodoo') { Write-Host '-Windowed needs dgVoodoo2: leave out -Wrapper none.'; exit 2 }
$HdTextures = -not ($NoHdTextures -or $Original -or $NoFocusfix)

function Get-Controllers {
    if (-not (Test-Path -LiteralPath $JoylistExe)) { return @() }
    $ErrorActionPreference = 'Continue'
    return @(& $JoylistExe 2>$null | Where-Object { $_ -like 'controller *' })
}

if ($Stop) {
    Get-Process -Name 'Dogfighter', 'focusfix' -ErrorAction SilentlyContinue | Stop-Process -Force
    exit 0
}

if ($Doctor) {
    $checks = 0; $failed = 0
    function Check([string]$Name, [string]$Fix, [scriptblock]$Test) {
        $script:checks++
        $ok = $false
        try { $ok = [bool](& $Test) } catch { $ok = $false }
        if ($ok) { Write-Host "ok    $Name" } else { $script:failed++; Write-Host "FAIL  $Name. Fix: $Fix" }
    }
    function Has-Files([string]$Dir, [string[]]$Names) {
        foreach ($n in $Names) { if (-not (Test-Path -LiteralPath (Join-Path $Dir $n))) { return $false } }
        return $true
    }
    Check '64-bit Windows' 'none; this needs 64-bit Windows 10 or 11' { [Environment]::Is64BitOperatingSystem }
    Check 'Game files in game\' 'setup.cmd' { Has-Files $Game @('Dogfighter.exe', 'AfEngine.dll', 'Cc.dll', 'UdsPack.dll', 'gtDirect3D.dll', 'Resource.up') }
    Check 'CD files in cd\ and cd.iso' 'delete cd\ and cd.iso, then setup.cmd' { (Has-Files (Join-Path $Here 'cd') @('.windows-label')) -and (Test-Path -LiteralPath (Join-Path $Here 'cd.iso')) }
    Check 'Ten music tracks in music\' 'setup.cmd' { Has-Files (Join-Path $Here 'music') @('02', '03', '04', '05', '06', '07', '08', '09', '10', '11' | ForEach-Object { "Track$_.ogg" }) }
    Check 'Music player (game\winmm.dll, game\Music)' 'setup.cmd' { Has-Files $Game @('winmm.dll', 'Music\Track02.ogg') }
    Check 'Helper is in build\' 'setup.cmd' { Has-Files $Build @('focusfix.exe', 'focushook.dll', 'joylist.exe', 'oggenc-min.exe', 'winmm.dll') }
    Check 'Helper is the pinned release build, or was built here from the current source' 'setup.cmd' {
        $pinned = @{}
        foreach ($line in (Read-Lines (Join-Path $Here 'tools\windows-helpers.sha256'))) {
            if ($line -match '^([0-9a-f]{64})  (\S+)$') { $pinned[$Matches[2]] = $Matches[1] }
        }
        $released = (Test-Sha256 $FocusfixExe $pinned['focusfix.exe']) -and (Test-Sha256 $FocushookDll $pinned['focushook.dll'])
        $released -or (
            ((Get-Item -LiteralPath $FocusfixExe).LastWriteTime -gt (Get-Item -LiteralPath (Join-Path $Here 'src\focusfix\focusfix.c')).LastWriteTime) -and
            ((Get-Item -LiteralPath $FocushookDll).LastWriteTime -gt (Get-Item -LiteralPath (Join-Path $Here 'src\focusfix\focushook.c')).LastWriteTime))
    }
    Check 'Save folders in game\User' 'setup.cmd' { Has-Files (Join-Path $Game 'User') @('Rosters', 'Save\Levels', 'Save\Photos', 'Save\Stickers') }
    Check 'Python for the texture check in python\' 'setup.cmd' { Test-Path -LiteralPath $Python }
    if ($Wrapper -eq 'dgvoodoo') {
        Check 'dgVoodoo2 in wrappers\dgVoodoo2' 'delete wrappers\dgVoodoo2, then setup.cmd' { Has-Files (Join-Path $DgVoodoo 'MS\x86') $WrapperFiles }
    }
    if (Test-HdSetComplete $Here $Python $HdDir) { Write-Host '      Larger textures: a complete set in hd-textures\.' }
    else { Write-Host '      Larger textures: none. Copy a finished hd-textures folder from a Mac install to use them.' }
    if (-not (Test-Path -LiteralPath $JoylistExe)) {
        Write-Host '      Controllers: not checked. That needs setup.cmd.'
    } else {
        $found = Get-Controllers
        if (-not $found) { Write-Host '      Controllers: no controller found. Connect one, then run this again.' }
        $n = 0
        foreach ($line in $found) {
            $n++
            $name = $line -replace '^controller [0-9]+: ', ''
            if ($n -eq 1) { Write-Host "      Controller 1: $name. The game uses this one." }
            else { Write-Host "      Controller ${n}: $name. Not used: the game takes the first one." }
        }
        if ($found -and (Get-UserSetting $UserIni 'option_joystick') -ne 'true') {
            Write-Host '      Joystick input is off in the game. The next start turns it on, unless it has -NoAutoJoystick.'
        }
    }
    if ($failed -eq 0) { Write-Host "All $checks checks passed. Start the game with: dogfighter.cmd"; exit 0 }
    Write-Host "$failed of $checks checks failed. Do the fixes above, then run this again."
    exit 1
}

if (Get-Process -Name 'Dogfighter' -ErrorAction SilentlyContinue) {
    Write-Host 'Dogfighter is already running. Stop it with: dogfighter.cmd -Stop'
    exit 1
}
if (-not (Test-Path -LiteralPath (Join-Path $Game 'Dogfighter.exe'))) { Write-Host 'game\Dogfighter.exe is missing. Run setup.cmd first.'; exit 1 }
if (-not $NoFocusfix -and -not ((Test-Path -LiteralPath $FocusfixExe) -and (Test-Path -LiteralPath $FocushookDll))) {
    Write-Host 'build\focusfix.exe or build\focushook.dll is missing. Run setup.cmd to build them.'
    exit 1
}

$Logs = Join-Path $Here 'logs'
New-Item -ItemType Directory -Force -Path $Logs | Out-Null
$Log = Join-Path $Logs ("run-{0}.log" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
function Say([string]$Text) { Write-Host $Text; Add-Content -LiteralPath $Log -Value $Text }
Say "Windows launcher, untested on Windows. Wrapper: $Wrapper."

function Set-ConfValue($Lines, [string]$Section, [string]$Key, [string]$Value) {
    $in = $false
    for ($i = 0; $i -lt $Lines.Count; $i++) {
        if ($Lines[$i] -match '^\s*\[') { $in = ($Lines[$i].Trim() -eq "[$Section]"); continue }
        if ($in -and $Lines[$i] -match "^\s*$Key\s*=") { $Lines[$i] = "$Key = $Value"; return }
    }
    throw "dgVoodoo.conf has no $Key in [$Section]."
}

function Install-Wrapper {
    foreach ($name in $WrapperFiles) {
        $from = Join-Path $DgVoodoo "MS\x86\$name"
        $to = Join-Path $Game $name
        if (-not (Test-Path -LiteralPath $to) -or (Get-FileHash -LiteralPath $from).Hash -ne (Get-FileHash -LiteralPath $to).Hash) {
            Copy-Item -LiteralPath $from -Destination $to -Force
        }
    }
    $lines = Read-Lines (Join-Path $DgVoodoo 'dgVoodoo.conf')
    Set-ConfValue $lines 'General' 'FullScreenMode' $(if ($Windowed) { 'false' } else { 'true' })
    Set-ConfValue $lines 'General' 'ScalingMode' 'stretched_ar'
    Set-ConfValue $lines 'DirectX' 'dgVoodooWatermark' 'false'
    Set-ConfValue $lines 'DirectX' 'Filtering' $(if ($Original) { 'appdriven' } else { '16' })
    Set-ConfValue $lines 'DirectX' 'Antialiasing' $(if ($Original -or $Smooth -eq 0) { 'appdriven' } else { "$($Smooth)x" })
    Write-Lines (Join-Path $Game 'dgVoodoo.conf') $lines
    Say "dgVoodoo2 in game\: $(if ($Windowed) { 'window' } else { 'full screen' }), filtering and edges $(if ($Original) { 'as the game sets them' } else { "16x and $($Smooth)x" })."
}

function Remove-Wrapper {
    foreach ($name in $WrapperFiles) {
        $from = Join-Path $DgVoodoo "MS\x86\$name"
        $to = Join-Path $Game $name
        if (-not (Test-Path -LiteralPath $to)) { continue }
        if ((Test-Path -LiteralPath $from) -and (Get-FileHash -LiteralPath $from).Hash -eq (Get-FileHash -LiteralPath $to).Hash) {
            Remove-Item -LiteralPath $to -Force
            Say "Removed game\$name (dgVoodoo2)."
        } else {
            Say "game\$name is not the dgVoodoo2 file setup fetched, so it stays. Windows' own DirectDraw is not used while it is there."
        }
    }
    Remove-Item -LiteralPath (Join-Path $Game 'dgVoodoo.conf') -Force -ErrorAction SilentlyContinue
    if (-not (Test-Path -LiteralPath $Ini) -or -not ((Read-Lines $Ini) -contains "[Direct3D.$WrapperCard]")) { return }
    Remove-IniSection $Ini "Direct3D.$WrapperCard"
    if ((Get-IniValue $Ini 'Direct3D' 'device_card') -eq $WrapperCard) {
        $card = (Read-Lines $Ini) | Where-Object { $_.StartsWith('[Direct3D.') } | Select-Object -First 1
        if ($card) { Set-IniValue $Ini 'Direct3D' 'device_card' $card.Substring(10, $card.Length - 11) }
    }
    Say 'Removed the dgVoodoo2 video card from game\system.ini.'
}

function Set-HdTextures {
    if ($HdTextures -and (Test-Path -LiteralPath $CacheLink) -and -not (Test-Junction $CacheLink)) {
        Say 'game\cache is a folder of your own, so the larger textures stay off. Move it away to use them.'
        $script:HdTextures = $false
    } elseif ($HdTextures -and -not (Test-HdSetComplete $Here $Python $HdDir)) {
        Say 'No complete set of larger textures in hd-textures\. Make it on a Mac and copy it here to use it.'
        $script:HdTextures = $false
    }
    if (-not $HdTextures) {
        if (Test-Junction $CacheLink) { Remove-Junction $CacheLink; Add-Content -LiteralPath $Log -Value 'Removed game\cache, the link to the larger textures.' }
        return
    }
    $limit = ([IO.File]::ReadAllText((Join-Path $HdDir 'texture-limit'))).Trim()
    Set-Junction $CacheLink (Join-Path $HdDir 'cache')
    $env:DOGFIGHTER_TEXTURE_LIMIT = $limit
    Say "Larger textures on: up to $limit pixels a side, from hd-textures\cache."
}

function Get-ScreenSize {
    foreach ($card in @(Get-CimInstance -ClassName Win32_VideoController -ErrorAction SilentlyContinue)) {
        if ($card.CurrentHorizontalResolution -and $card.CurrentVerticalResolution) {
            return "$($card.CurrentHorizontalResolution)x$($card.CurrentVerticalResolution)"
        }
    }
    return ''
}

function Test-Fits([string]$Size, [string]$Limit) {
    $s = $Size -split 'x'; $l = $Limit -split 'x'
    return ([int]$s[0] -le [int]$l[0]) -and ([int]$s[1] -le [int]$l[1])
}

function Get-GameSection {
    $dev = Get-IniValue $Ini 'setup' 'current_device'
    if (-not $dev) { $dev = 'Direct3D' }
    $card = Get-IniValue $Ini $dev 'device_card'
    if ($card) { return "$dev.$card" }
    return ''
}

function Get-Picture([string]$Key) {
    if ($Key -eq 'screen_depth') { return Get-IniValue $Ini $script:Section $Key }
    return Get-UserSetting $UserIni $Key
}

function Set-Picture([string]$Key, [string]$Value) {
    if ($Key -eq 'screen_depth') { Set-IniValue $Ini $script:Section $Key $Value } else { Set-UserSetting $UserIni $Key $Value }
}

function Set-PictureSettings {
    $before = Read-Lines $PictureBefore
    foreach ($key in $Pictures.Keys) {
        $want = $Pictures[$key]
        $now = Get-Picture $key
        if ($now -eq $want) { continue }
        if (-not ($before | Where-Object { $_.StartsWith("$key=") })) { Add-Content -LiteralPath $PictureBefore -Value "$key=$now" }
        Set-Picture $key $want
        Say "Picture setting ${key}: $(if ($now) { $now } else { 'not set' }) -> $want."
    }
}

function Restore-PictureSettings {
    if (-not (Test-Path -LiteralPath $PictureBefore)) { return }
    $before = Read-Lines $PictureBefore
    foreach ($key in $Pictures.Keys) {
        $line = $before | Where-Object { $_.StartsWith("$key=") } | Select-Object -First 1
        if (-not $line -or (Get-Picture $key) -ne $Pictures[$key]) { continue }
        Set-Picture $key $line.Substring($key.Length + 1)
        Say "Picture setting ${key}: back to $(Get-Picture $key)."
    }
    Remove-Item -LiteralPath $PictureBefore -Force
}

function Enable-Joystick {
    if ($NoAutoJoystick -or -not (Test-Path -LiteralPath $UserIni)) { return }
    if ((Get-UserSetting $UserIni 'option_joystick') -eq 'true') { return }
    $first = Get-Controllers | Select-Object -First 1
    if (-not $first) { return }
    Set-UserSetting $UserIni 'option_joystick' 'true'
    Say "Found $($first -replace '^controller 1: ', ''), so Joystick is now on in the game's Options. -NoAutoJoystick leaves it as it is."
}

if ($Wrapper -eq 'dgvoodoo') { Install-Wrapper } else { Remove-Wrapper }
Set-HdTextures
Enable-Joystick

$screen = Get-ScreenSize
if (-not $screen) { $screen = '1024x768'; Say "Could not read the screen size; assuming room for a $screen picture." }
if ($Windowed) {
    $wh = $screen -split 'x'
    $screen = "$([int]$wh[0] - 16)x$([int]$wh[1] - 80)"
}
$fit = ($Sizes | Where-Object { Test-Fits $_ $screen } | Select-Object -First 1)
if (-not $fit) { $fit = '640x480' }
if (-not $Res) { $Res = $fit }
elseif (-not (Test-Fits $Res $screen)) { Say "$Res does not fit on this screen ($screen); using $fit."; $Res = $fit }
$SetupMode = if ($Setup) { 'show' } else { 'accept' }
$Section = Get-GameSection
if (-not $Section) {
    Say "No video card in game\system.ini yet. Press OK in the game's setup dialog; -Res applies from the next start."
    $SetupMode = 'show'
} elseif ("$(Get-IniValue $Ini $Section 'screen_width')x$(Get-IniValue $Ini $Section 'screen_height')" -ne $Res) {
    $wh = $Res -split 'x'
    Set-IniValue $Ini $Section 'screen_width' $wh[0]
    Set-IniValue $Ini $Section 'screen_height' $wh[1]
    Say "Game resolution set to $Res."
}
if ($Section -and (Test-Path -LiteralPath $UserIni)) {
    if ($Original) { Restore-PictureSettings } else { Set-PictureSettings }
}

$mountedIso = $null
if ($MountCd) {
    $iso = Join-Path $Here 'cd.iso'
    try {
        Mount-DiskImage -ImagePath $iso | Out-Null
        $mountedIso = $iso
        Say 'cd.iso is mounted as a CD drive while the game runs.'
    } catch {
        Say "cd.iso could not be mounted: $($_.Exception.Message). Double-click it in Explorer to mount it."
    }
}

foreach ($name in 'DOGFIGHTER_WINDOW', 'DOGFIGHTER_FULL_SIZE', 'DOGFIGHTER_DIAG', 'DOGFIGHTER_PICTURE_WAIT_MS') {
    Remove-Item -LiteralPath "Env:$name" -ErrorAction SilentlyContinue
}
$env:DOGFIGHTER_SETUP = $SetupMode
$env:DOGFIGHTER_HOOK_DLL = $FocushookDll
$env:DOGFIGHTER_LOG_DIR = $Logs
if (-not $GameIntros) { $env:DOGFIGHTER_SKIP_INTROS = '2' } else { Remove-Item Env:DOGFIGHTER_SKIP_INTROS -ErrorAction SilentlyContinue }

Say "Starting Airfix Dogfighter. Log: $Log"
try {
    if ($NoFocusfix) {
        $process = Start-Process -FilePath (Join-Path $Game 'Dogfighter.exe') -WorkingDirectory $Game -Wait -PassThru
    } else {
        $flag = Join-Path $Build 'focusfix.flag'
        $exe = Join-Path $Game 'Dogfighter.exe'
        $process = Start-Process -FilePath $FocusfixExe -ArgumentList "`"$flag`"", "`"$exe`"" -Wait -PassThru
    }
    Say ('The game ended with exit code 0x{0:x8}.' -f $process.ExitCode)
} finally {
    if ($mountedIso) { Dismount-DiskImage -ImagePath $mountedIso | Out-Null }
    foreach ($name in 'dogfighter-focusfix.log', 'dogfighter-focushook.log') {
        $part = Join-Path $Logs $name
        if (Test-Path -LiteralPath $part) {
            Add-Content -LiteralPath $Log -Value (Get-Content -LiteralPath $part)
            Remove-Item -LiteralPath $part -Force
        }
    }
    $music = Join-Path $Game 'winmm.log'
    if (Test-Path -LiteralPath $music) { Copy-Item -LiteralPath $music -Destination ($Log -replace '\.log$', '-music.log') }
}
Say "Done. Log: $Log"
