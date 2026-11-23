param(
    [string]$Image,
    [string]$Language,
    [switch]$NoWrapper,
    [switch]$Help
)
Set-StrictMode -Version 2
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$Usage = @'
Usage: setup.cmd [-Language English|French|German|Italian] [-NoWrapper] [path\to\Dogfighter.bin]

Windows version of setup.sh. NOT TESTED ON WINDOWS YET; see docs\WINDOWS.md.
Builds the game from your own Airfix Dogfighter CD image, a raw .bin with
2352-byte sectors (the .bin of a BIN/CUE pair). It defaults to Dogfighter.bin
in this folder. Run it again after an error: finished steps are skipped.

It downloads, each checked against a pinned SHA-256 checksum:
  llvm-mingw (builds the music player and the helper), Python's embeddable
  package (runs the repo's disc tools), libogg, libvorbis, ogg-winmm, and
  dgVoodoo2 (a DirectDraw and Direct3D 7 replacement). -NoWrapper leaves
  dgVoodoo2 out; the game then uses Windows' own DirectDraw.

It does not make the larger textures. Copy a finished hd-textures folder
from a Mac install to use them.
'@

if ($Help) { Write-Host $Usage; exit 0 }

$Languages = 'English', 'French', 'German', 'Italian'
if ($Language) {
    $match = $Languages | Where-Object { $_ -eq $Language }
    if (-not $match) { Write-Host $Usage; exit 2 }
    $Language = $match
}

$Here = $PSScriptRoot
. (Join-Path $Here 'tools\windows-common.ps1')
if (-not $Image) { $Image = Join-Path $Here 'Dogfighter.bin' }
if (Test-Path -LiteralPath $Image) { $Image = (Resolve-Path -LiteralPath $Image).ProviderPath }
$Downloads = Join-Path $Here 'downloads'
$Work = Join-Path $Here 'build\setup-work'
$ToolchainName = 'llvm-mingw-20261117-ucrt-x86_64'
$Toolchain = Join-Path $Here "toolchain\$ToolchainName"
$Cc = Join-Path $Toolchain 'bin\i686-w64-mingw32-clang.exe'
$PythonDir = Join-Path $Here 'python'
$Python = Join-Path $PythonDir 'python.exe'
$Build = Join-Path $Here 'build'
$Game = Join-Path $Here 'game'
$Music = Join-Path $Here 'music'
$OggWinmmCommit = '09859f0cedf074c705fd56d29056d254e667a17d'
$Tracks = '02', '03', '04', '05', '06', '07', '08', '09', '10', '11'
$DgVoodoo = Join-Path $Here 'wrappers\dgVoodoo2'

function Step([string]$Text) { Write-Host "`n==> $Text" }

trap {
    Write-Host "`nsetup: $_" -ForegroundColor Red
    Write-Host 'A step failed. Fix the error above, then run setup again.'
    if (Test-Path -LiteralPath $Work) { Remove-Item -LiteralPath $Work -Recurse -Force -ErrorAction SilentlyContinue }
    exit 1
}

function Fail([string]$Text) { throw $Text }

function Test-Requirements {
    if (-not [Environment]::Is64BitOperatingSystem) { Fail 'This needs 64-bit Windows 10 or 11.' }
    if ([Environment]::OSVersion.Version.Build -lt 17763) { Fail 'This needs Windows 10 version 1809 or later, for tar.exe and curl.exe.' }
    foreach ($tool in 'tar.exe', 'curl.exe') {
        if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) { Fail "$tool is missing; it normally ships with Windows 10 and 11." }
    }
    $arch = $env:PROCESSOR_ARCHITEW6432
    if (-not $arch) { $arch = $env:PROCESSOR_ARCHITECTURE }
    if ($arch -eq 'ARM64') {
        Write-Host 'This is Windows on ARM. The x64 tools run through Windows 11 emulation; Windows 10 on ARM cannot run them.'
    }
}

function Test-Space([int]$Gb) {
    $qualifier = Split-Path -Qualifier $Here -ErrorAction SilentlyContinue
    if (-not $qualifier) { return }
    $drive = Get-PSDrive -Name $qualifier.TrimEnd(':') -ErrorAction SilentlyContinue
    if ($drive -and $drive.Free -lt $Gb * 1GB) { Fail "Setup needs about $Gb GB of free disk space." }
}

function Test-Image {
    if (-not (Test-Path -LiteralPath $Image -PathType Leaf)) {
        Fail "CD image not found: $Image`nMake a raw BIN/CUE image of your own disc first (see docs\WINDOWS.md), or pass the .bin: setup.cmd path\to\Dogfighter.bin"
    }
    $size = (Get-Item -LiteralPath $Image).Length
    if ($size % 2352 -ne 0) {
        if ($size % 2048 -eq 0) { Fail "$Image looks like an .iso. It has no music; make a raw .bin/.cue image instead." }
        Fail "$Image is not a raw CD image (its size is not a multiple of 2352 bytes)."
    }
    $stream = [IO.File]::OpenRead($Image)
    try { $head = New-Object byte[] 12; [void]$stream.Read($head, 0, 12) } finally { $stream.Close() }
    if ((($head | ForEach-Object { $_.ToString('x2') }) -join '') -ne '00ffffffffffffffffffff00') {
        Fail "$Image does not start with a data track. Is it the Airfix Dogfighter CD?"
    }
}

function Get-Pinned([string]$Name, [string]$Url, [string]$Sha) {
    $file = Join-Path $Downloads $Name
    if (Test-Sha256 $file $Sha) { return $file }
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $file) | Out-Null
    Write-Host "Downloading $Name"
    & curl.exe -fL --retry 3 --progress-bar -o "$file.part" $Url
    if ($LASTEXITCODE -ne 0) { Fail "Download failed: $Url" }
    if (-not (Test-Sha256 "$file.part" $Sha)) {
        Remove-Item -LiteralPath "$file.part" -Force
        Fail "$Name does not match its pinned SHA-256 checksum. Delete downloads\ and try again; if it keeps failing, the file on the server has changed."
    }
    Move-Item -LiteralPath "$file.part" -Destination $file -Force
    return $file
}

function Expand-Pinned([string]$Archive, [string]$Inner, [string]$Dest) {
    if (Test-Path -LiteralPath $Work) { Remove-Item -LiteralPath $Work -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $Work, (Split-Path -Parent $Dest) | Out-Null
    Invoke-Checked 'tar.exe' @('-xf', $Archive, '-C', $Work)
    if (Test-Path -LiteralPath $Dest) { Remove-Item -LiteralPath $Dest -Recurse -Force }
    if ($Inner) { Move-Item -LiteralPath (Join-Path $Work $Inner) -Destination $Dest }
    else { Move-Item -LiteralPath $Work -Destination $Dest }
    if (Test-Path -LiteralPath $Work) { Remove-Item -LiteralPath $Work -Recurse -Force }
}

function Get-Toolchain {
    if (Test-Path -LiteralPath $Cc) { return }
    Step 'llvm-mingw (builds the music player and the helper)'
    $zip = Get-Pinned "$ToolchainName.zip" "https://github.com/mstorsjo/llvm-mingw/releases/download/20261117/$ToolchainName.zip" `
        '4d002e330a0f703625aa5ccbc37e96f8f824413e163bfc7336774aabd2c3a412'
    Expand-Pinned $zip $ToolchainName $Toolchain
}

function Get-Python {
    if (Test-Path -LiteralPath $Python) { return }
    Step 'Python 3.14.9, embeddable package (runs the disc tools in tools\)'
    $zip = Get-Pinned 'python-3.14.9-embed-amd64.zip' 'https://www.python.org/ftp/python/3.14.9/python-3.14.9-embed-amd64.zip' `
        '3c01d7cfc666f746a6f064f60fb2156ab0ec464d3d738ab796371a46a9bb24a2'
    Expand-Pinned $zip '' $PythonDir
}

function Get-Sources {
    $sources = @(
        @('ogg-1.3.6', 'libogg 1.3.6', 'libogg-1.3.6.tar.gz', 'https://github.com/xiph/ogg/archive/refs/tags/v1.3.6.tar.gz',
            '95b643da661155d79db9de2fca55daed3a8d491039829def246aacb3d9201c81', 'ogg-1.3.6'),
        @('vorbis-1.3.7', 'libvorbis 1.3.7', 'libvorbis-1.3.7.tar.gz', 'https://github.com/xiph/vorbis/archive/refs/tags/v1.3.7.tar.gz',
            '270c76933d0934e42c5ee0a54a36280e2d87af1de3cc3e584806357e237afd13', 'vorbis-1.3.7'),
        @('ogg-winmm', 'ogg-winmm (plays the CD music from .ogg files)', 'ogg-winmm-09859f0.tar.gz',
            "https://github.com/dippy-dipper/ogg-winmm/archive/$OggWinmmCommit.tar.gz",
            'aa8c260fedb2aacc4f3c79899645039ab08a36f3a2ef4005de1f9a245bcc1fb2', "ogg-winmm-$OggWinmmCommit")
    )
    foreach ($s in $sources) {
        $dest = Join-Path $Here "src\$($s[0])"
        if (Test-Path -LiteralPath $dest) { continue }
        Step $s[1]
        $archive = Get-Pinned $s[2] $s[3] $s[4]
        Expand-Pinned $archive $s[5] $dest
    }
}

function Get-Wrapper {
    if ($NoWrapper -or (Test-Path -LiteralPath (Join-Path $DgVoodoo 'MS\x86\DDraw.dll'))) { return }
    Step 'dgVoodoo2 2.87.6 (DirectDraw and Direct3D 7 on Direct3D 11)'
    $zip = Get-Pinned 'dgVoodoo2_87_6.zip' 'https://github.com/dege-diosg/dgVoodoo2/releases/download/2.87.6/dgVoodoo2_87_6.zip' `
        '9afa493396feec7108f42a2d97661eef96bbaac5addf0dfb5cfbc3001cd76a0a'
    Expand-Pinned $zip '' $DgVoodoo
}

function Expand-DataTrack([string]$Iso, [string]$Dest) {
    New-Item -ItemType Directory -Force -Path $Dest | Out-Null
    & tar.exe -xf $Iso -C $Dest
    if ($LASTEXITCODE -eq 0) { return }
    Write-Host 'tar.exe could not read the data track; mounting it with Windows instead.'
    $mounted = Mount-DiskImage -ImagePath $Iso -PassThru
    try {
        $letter = ($mounted | Get-Volume).DriveLetter
        Copy-Item -Path "$($letter):\*" -Destination $Dest -Recurse -Force
    } finally {
        Dismount-DiskImage -ImagePath $Iso | Out-Null
    }
}

function New-Cd {
    $cd = Join-Path $Here 'cd'
    if ((Test-Path -LiteralPath (Join-Path $cd '.windows-label')) -and (Test-Path -LiteralPath (Join-Path $Here 'cd.iso'))) { return }
    Test-Image
    Step "Copying the CD's data track to cd\ and cd.iso"
    foreach ($old in $Work, $cd) { if (Test-Path -LiteralPath $old) { Remove-Item -LiteralPath $old -Recurse -Force } }
    New-Item -ItemType Directory -Force -Path $Work | Out-Null
    $iso = Join-Path $Work 'data.iso'
    Invoke-Checked $Python @('-I', (Join-Path $Here 'tools\scan.py'), $Image, $iso)
    Expand-DataTrack $iso (Join-Path $Work 'cd')
    foreach ($name in 'data1.hdr', 'data2.cab') {
        if (-not (Test-Path -LiteralPath (Join-Path $Work "cd\$name"))) {
            Fail 'The data track has no data1.hdr or data2.cab. Is this the Airfix Dogfighter CD?'
        }
    }
    Get-ChildItem -LiteralPath (Join-Path $Work 'cd') -Recurse -File | ForEach-Object { $_.IsReadOnly = $false }
    [IO.File]::WriteAllText((Join-Path $Work 'cd\.windows-label'), "Dogfighter`n")
    Move-Item -LiteralPath (Join-Path $Work 'cd') -Destination $cd
    Move-Item -LiteralPath $iso -Destination (Join-Path $Here 'cd.iso') -Force
    Remove-Item -LiteralPath $Work -Recurse -Force
}

function Get-InstalledLanguage {
    foreach ($line in (Read-Lines (Join-Path $Game 'system.ini'))) {
        if ($line.StartsWith('current_language=')) { return $line.Substring(17) }
    }
    return ''
}

function Set-Language {
    $ini = Join-Path $Game 'system.ini'
    $out = New-Object Collections.Generic.List[string]
    foreach ($line in (Read-Lines $ini)) {
        if ($line.StartsWith('current_language=')) { continue }
        $out.Add($line)
        if ($line -eq '[setup]') { $out.Add("current_language=$Language") }
    }
    Write-Lines $ini $out
    if ((Get-InstalledLanguage) -ne $Language) { Fail 'game\system.ini has no [setup] section.' }
}

function Install-Game {
    $was = $Languages | Where-Object { $_ -eq (Get-InstalledLanguage) }
    if (-not $script:Language) { $script:Language = if ($was) { $was } else { 'English' } }
    Step "Installing the $Language game files in game\"
    if ($was -ne $Language) { Remove-Item -LiteralPath (Join-Path $Game 'readme.txt') -Force -ErrorAction SilentlyContinue }
    Invoke-Checked $Python @('-I', (Join-Path $Here 'tools\iscab.py'), (Join-Path $Here 'cd'), $Game, $Language)
    foreach ($name in 'Dogfighter.exe', 'Resource.up', "$Language.up", "$Language.loc") {
        if (-not (Test-Path -LiteralPath (Join-Path $Game $name))) { Fail 'game\ is incomplete after unpacking the cabs.' }
    }
    foreach ($other in $Languages) {
        if ($other -eq $Language) { continue }
        foreach ($ext in 'up', 'loc') { Remove-Item -LiteralPath (Join-Path $Game "$other.$ext") -Force -ErrorAction SilentlyContinue }
    }
    if ((Get-InstalledLanguage) -ne $Language) { Set-Language }
    foreach ($dir in 'User\Rosters', 'User\Save\Levels', 'User\Save\Photos', 'User\Save\Stickers', 'ScreenShots') {
        New-Item -ItemType Directory -Force -Path (Join-Path $Game $dir) | Out-Null
    }
}

function New-OggConfig([string]$Dir) {
    $in = Join-Path $Here 'src\ogg-1.3.6\include\ogg\config_types.h.in'
    $text = [IO.File]::ReadAllText($in) -replace '@INCLUDE_[A-Z_]*@', '1'
    $text = $text.Replace('@SIZE16@', 'int16_t').Replace('@USIZE16@', 'uint16_t').Replace('@SIZE32@', 'int32_t')
    $text = $text.Replace('@USIZE32@', 'uint32_t').Replace('@SIZE64@', 'int64_t').Replace('@USIZE64@', 'uint64_t')
    New-Item -ItemType Directory -Force -Path (Join-Path $Dir 'inc\ogg') | Out-Null
    [IO.File]::WriteAllText((Join-Path $Dir 'inc\ogg\config_types.h'), $text)
}

function Get-OggIncludes([string]$Dir) {
    return @("-I$Dir\inc", "-I$Here\src\ogg-1.3.6\include", "-I$Here\src\vorbis-1.3.7\include", "-I$Here\src\vorbis-1.3.7\lib")
}

function Build-Encoder {
    $exe = Join-Path $Build 'oggenc-min.exe'
    if (Test-Path -LiteralPath $exe) { return $exe }
    $dir = Join-Path $Build 'oggenc-work'
    if (Test-Path -LiteralPath $dir) { Remove-Item -LiteralPath $dir -Recurse -Force }
    New-OggConfig $dir
    $example = [IO.File]::ReadAllText("$Here\src\vorbis-1.3.7\examples\encoder_example.c")
    $source = $example.Replace('vorbis_encode_init_vbr(&vi,2,44100,0.1)', 'vorbis_encode_init_vbr(&vi,2,44100,0.5)')
    if ($source -eq $example) { Fail 'encoder_example.c has changed; the music quality setting was not found.' }
    [IO.File]::WriteAllText("$dir\enc.c", $source)
    $files = @("$dir\enc.c", "$Here\src\ogg-1.3.6\src\bitwise.c", "$Here\src\ogg-1.3.6\src\framing.c")
    foreach ($n in 'mdct', 'smallft', 'block', 'envelope', 'window', 'lsp', 'lpc', 'analysis', 'synthesis', 'psy', 'info',
        'floor1', 'floor0', 'res0', 'mapping0', 'registry', 'codebook', 'sharedbook', 'lookup', 'bitrate', 'vorbisenc') {
        $files += "$Here\src\vorbis-1.3.7\lib\$n.c"
    }
    Invoke-Checked $Cc (@('-O2', '-w') + (Get-OggIncludes $dir) + @('-o', $exe) + $files)
    Remove-Item -LiteralPath $dir -Recurse -Force
    return $exe
}

function Copy-Music {
    $missing = $Tracks | Where-Object { -not (Test-Path -LiteralPath (Join-Path $Music "Track$_.ogg")) }
    if ($missing) {
        Test-Image
        Step 'Ripping the CD music to music\ (a few minutes)'
        $encoder = Build-Encoder
        $ranges = @(& $Python -I (Join-Path $Here 'tools\find_tracks.py') $Image)
        if ($LASTEXITCODE -ne 0) { Fail 'find_tracks.py failed.' }
        if ($ranges.Count -ne $Tracks.Count) {
            Fail "Found $($ranges.Count) music tracks in $Image, expected $($Tracks.Count): $($ranges -join ' ')"
        }
        Invoke-Checked $Python (@('-I', (Join-Path $Here 'tools\rip_tracks.py'), $Image, $encoder, $Music) + $ranges)
    }
    $link = Join-Path $Game 'Music'
    if ((Test-Path -LiteralPath $link) -and -not (Test-Junction $link)) {
        Write-Host 'game\Music is a folder of your own, so it is kept. The music player reads it, not music\.'
        return
    }
    Set-Junction $link $Music
}

function Build-Winmm {
    $dll = Join-Path $Build 'winmm.dll'
    if (-not (Test-Path -LiteralPath $dll)) {
        Step 'Building winmm.dll (CD music player)'
        $dir = Join-Path $Build 'winmm-work'
        if (Test-Path -LiteralPath $dir) { Remove-Item -LiteralPath $dir -Recurse -Force }
        New-OggConfig $dir
        $inc = Get-OggIncludes $dir
        $objs = @()
        foreach ($f in "$Here\src\ogg-1.3.6\src\bitwise.c", "$Here\src\ogg-1.3.6\src\framing.c") {
            $o = "$dir\ogg_$([IO.Path]::GetFileNameWithoutExtension($f)).o"
            Invoke-Checked $Cc (@('-O2', '-std=gnu99', '-w') + $inc + @('-c', $f, '-o', $o))
            $objs += $o
        }
        foreach ($n in 'mdct', 'smallft', 'block', 'envelope', 'window', 'lsp', 'lpc', 'analysis', 'synthesis', 'psy', 'info',
            'floor1', 'floor0', 'res0', 'mapping0', 'registry', 'codebook', 'sharedbook', 'lookup', 'bitrate', 'vorbisfile') {
            $o = "$dir\vorbis_$n.o"
            Invoke-Checked $Cc (@('-O2', '-std=gnu99', '-w') + $inc + @('-c', "$Here\src\vorbis-1.3.7\lib\$n.c", '-o', $o))
            $objs += $o
        }
        Invoke-Checked (Join-Path $Toolchain 'bin\i686-w64-mingw32-ar.exe') (@('rcs', "$dir\libvorbisfile.a") + $objs)
        $w = Join-Path $Here 'src\ogg-winmm'
        $rc = [IO.File]::ReadAllText("$w\ogg-winmm.rc.in").Replace('__REV__', '09859f0').Replace('__FILE__', 'ogg-winmm')
        [IO.File]::WriteAllText("$dir\ogg-winmm.rc", $rc)
        Invoke-Checked (Join-Path $Toolchain 'bin\i686-w64-mingw32-windres.exe') @('-O', 'coff', '-o', "$dir\ogg-winmm.rc.o", "$dir\ogg-winmm.rc")
        Invoke-Checked $Cc (@('-std=gnu99', '-O2', '-shared', '-s', '-w', '-D_DEBUG') + $inc + @('-Wl,--enable-stdcall-fixup',
            '-o', $dll, "$w\ogg-winmm.c", "$w\player.c", "$w\stubs.c", "$w\ogg-winmm.def", "$dir\ogg-winmm.rc.o",
            "-L$dir", '-lvorbisfile', '-lwinmm', '-static'))
        Remove-Item -LiteralPath $dir -Recurse -Force
    }
    $installed = Join-Path $Game 'winmm.dll'
    if (-not (Test-Path -LiteralPath $installed) -or (Get-FileHash $dll).Hash -ne (Get-FileHash $installed).Hash) {
        Copy-Item -LiteralPath $dll -Destination $installed -Force
    }
}

function Build-Helpers {
    $src = Join-Path $Here 'src\focusfix'
    $helpers = @(
        @('focusfix.exe', 'focusfix.c', @('-mwindows')),
        @('focushook.dll', 'focushook.c', @('-shared', '-lgdi32')),
        @('joylist.exe', 'joylist.c', @('-mconsole', '-ldinput', '-ldxguid'))
    )
    $said = $false
    foreach ($h in $helpers) {
        $out = Join-Path $Build $h[0]
        $c = Join-Path $src $h[1]
        if ((Test-Path -LiteralPath $out) -and (Get-Item -LiteralPath $out).LastWriteTime -gt (Get-Item -LiteralPath $c).LastWriteTime) { continue }
        if (-not $said) { Step 'Building the helper (focusfix.exe, focushook.dll) and joylist.exe'; $said = $true }
        $flags = $h[2]
        $libs = @($flags | Where-Object { $_.StartsWith('-l') })
        $mode = @($flags | Where-Object { -not $_.StartsWith('-l') })
        Invoke-Checked $Cc (@('-std=gnu99', '-O2', '-s', '-Wall') + $mode + @('-o', $out, $c) + $libs)
    }
}

function Test-HdTextures {
    $dir = Join-Path $Here 'hd-textures'
    if (Test-HdSetComplete $Here $Python $dir) {
        Step 'Larger textures'
        Write-Host 'hd-textures\ holds a complete set. dogfighter.cmd uses it.'
    } else {
        Write-Host "`nNo complete set of larger textures in hd-textures\. Setup on Windows does not make them."
        Write-Host 'To use them, make them with setup.sh on a Mac and copy that hd-textures folder here.'
    }
}

Test-Requirements
if (-not (Test-Path -LiteralPath (Join-Path $Game 'Resource.up'))) { Test-Space 3 }
New-Item -ItemType Directory -Force -Path $Build | Out-Null
Get-Toolchain
Get-Python
Get-Sources
Get-Wrapper
New-Cd
Install-Game
Copy-Music
Build-Winmm
Build-Helpers
Test-HdTextures

Write-Host "`nSetup is done. Start the game with dogfighter.cmd."
Write-Host 'This Windows version is untested. Please report what happens; see docs\WINDOWS.md.'
