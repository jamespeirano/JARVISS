$ErrorActionPreference = 'Stop'
$installer = Join-Path $env:RUNNER_TEMP 'signed/JARVISS-Windows-x64.exe'
$expected = $env:EXPECTED_SHA256
$actual = (Get-FileHash $installer -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actual -ne $expected) { throw 'Signed installer checksum mismatch' }
function Assert-PersonalSignature([string]$file) {
  $signature = Get-AuthenticodeSignature $file
  if ($signature.Status -ne 'Valid') { throw "Invalid signature on ${file}: $($signature.StatusMessage)" }
  $name = $signature.SignerCertificate.GetNameInfo([System.Security.Cryptography.X509Certificates.X509NameType]::SimpleName, $false)
  if ($name -ne 'James Peirano') { throw "Unexpected signer: $name" }
  if ($null -eq $signature.TimeStamperCertificate) { throw "No timestamp on $file" }
  Write-Host "PASS signed and timestamped: $(Split-Path $file -Leaf) by $name"
}
Assert-PersonalSignature $installer
$installed = Join-Path $env:RUNNER_TEMP 'JarvisSignedTest'
$process = Start-Process -FilePath $installer -ArgumentList "/S /D=$installed" -Wait -PassThru
if ($process.ExitCode -ne 0) { throw "Installer returned $($process.ExitCode)" }
Assert-PersonalSignature (Join-Path $installed 'JARVISS.exe')
Assert-PersonalSignature (Join-Path $installed 'resources/backend/jarviss-service.exe')
$uninstaller = Get-ChildItem $installed -Filter '*Uninstall*.exe' | Select-Object -First 1
if ($null -eq $uninstaller) { throw 'Uninstaller missing' }
Assert-PersonalSignature $uninstaller.FullName
python "$PSScriptRoot/check_installed_backend.py" $installed
if ($LASTEXITCODE -ne 0) { throw 'Installed backend smoke check failed' }
Write-Host 'PASS Windows installation, publisher, file integrity, timestamps and installed backend'
