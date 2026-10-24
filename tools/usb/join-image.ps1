# Run from the directory containing all image parts and checksum files.
$ErrorActionPreference = 'Stop'
$image = 'fedora-gaokun3-usb.raw.xz'
if ((Test-Path $image) -or (Test-Path "$image.partial")) {
    throw 'Output already exists; move it aside before joining.'
}
$parts = @(Get-Content 'SHA256SUMS.parts' | ForEach-Object {
    if ($_ -notmatch '^([a-fA-F0-9]{64})  (fedora-gaokun3-usb\.raw\.xz\.[0-9]{3})$') {
        throw 'Invalid part manifest'
    }
    $expected = $Matches[1]
    $part = $Matches[2]
    if ((Get-FileHash -LiteralPath $part -Algorithm SHA256).Hash -ne $expected) {
        throw "Checksum failed: $part"
    }
    $part
})
if ($parts.Count -eq 0) { throw 'No image parts listed' }
$output = [IO.File]::Open("$PWD/$image.partial", [IO.FileMode]::CreateNew)
try {
    foreach ($part in $parts) {
        $inputStream = [IO.File]::OpenRead("$PWD/$part")
        try { $inputStream.CopyTo($output) } finally { $inputStream.Dispose() }
    }
} finally { $output.Dispose() }
$line = (Get-Content 'SHA256SUMS' -Raw).Trim()
if ($line -notmatch '^([a-fA-F0-9]{64})  fedora-gaokun3-usb\.raw\.xz$') {
    throw 'Invalid image checksum file'
}
if ((Get-FileHash -LiteralPath "$image.partial" -Algorithm SHA256).Hash -ne $Matches[1]) {
    throw 'Combined image checksum failed'
}
Move-Item -LiteralPath "$image.partial" -Destination $image
Write-Host "Verified $image. Select this file in balenaEtcher."
