$ErrorActionPreference = 'Stop'
$taskRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$taskNsis = Join-Path $taskRoot 'src-tauri/target/release/nsis/x64'
$taskProduct = 'AI Asset Hub M02 Verification'
$taskKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\$taskProduct"
if (Test-Path -LiteralPath $taskKey) { throw 'A verification installation already exists; do not overwrite it.' }
$taskOriginalKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\AI Asset Hub'
$taskOriginal = Get-ItemProperty -LiteralPath $taskOriginalKey -ErrorAction SilentlyContinue
$taskSource = Get-Content -LiteralPath (Join-Path $taskNsis 'installer.nsi') -Raw
if (!$taskSource.Contains('!define PRODUCTNAME "AI Asset Hub"')) { throw 'Unexpected NSIS template.' }
$taskInstaller = Join-Path $taskRoot '.artifacts/m02-verification-setup.exe'
$taskSource = $taskSource.Replace('!define PRODUCTNAME "AI Asset Hub"', "!define PRODUCTNAME `"$taskProduct`"")
$taskSource = $taskSource.Replace('!define BUNDLEID "local.aiassethub.dev"', '!define BUNDLEID "local.aiassethub.m02verification"')
$taskSource = $taskSource.Replace('!define OUTFILE "nsis-output.exe"', "!define OUTFILE `"$taskInstaller`"")
$taskScript = Join-Path $taskNsis 'verification.nsi'
Set-Content -LiteralPath $taskScript -Value $taskSource -Encoding UTF8
$taskCompiler = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'tauri/NSIS/makensis.exe'
Push-Location $taskNsis
try {
    & $taskCompiler /V2 $taskScript
    if ($LASTEXITCODE -ne 0) { throw 'Verification NSIS compilation failed.' }
} finally { Pop-Location }
$taskInstallDir = Join-Path $taskRoot ('.artifacts/m02-installed-' + [guid]::NewGuid().ToString())
$taskArtifactPrefix = [IO.Path]::GetFullPath((Join-Path $taskRoot '.artifacts')) + [IO.Path]::DirectorySeparatorChar
if (![IO.Path]::GetFullPath($taskInstallDir).StartsWith($taskArtifactPrefix, [StringComparison]::OrdinalIgnoreCase)) { throw 'Verification install escaped workspace artifacts.' }
if (Test-Path -LiteralPath $taskInstallDir) { throw 'Verification destination must be new.' }
$taskProcess = Start-Process -FilePath $taskInstaller -ArgumentList "/S /NS /D=$taskInstallDir" -PassThru -WindowStyle Hidden
if (!$taskProcess.WaitForExit(60000) -or $taskProcess.ExitCode -ne 0) { throw 'Silent verification installation failed.' }
$taskRegistry = Get-ItemProperty -LiteralPath $taskKey
if ($taskRegistry.DisplayVersion -ne '0.5.0') { throw 'Installed version mismatch.' }
$taskSourceCore = Join-Path $taskRoot 'src-tauri/binaries/ai-asset-hub-core-x86_64-pc-windows-msvc.exe'
$taskInstalledCore = Join-Path $taskInstallDir 'ai-asset-hub-core.exe'
if ((Get-FileHash -LiteralPath $taskSourceCore).Hash -ne (Get-FileHash -LiteralPath $taskInstalledCore).Hash) { throw 'Installed Sidecar hash mismatch.' }
if (!(Test-Path -LiteralPath (Join-Path $taskInstallDir '_internal/migrations/001_initial.sql'))) { throw 'Packaged migrations missing.' }
$taskData = Join-Path $taskRoot ('.artifacts/core-verification-' + [guid]::NewGuid().ToString())
$taskStdout = Join-Path $taskRoot '.artifacts/installed-core-health.json'
$taskStderr = Join-Path $taskRoot '.artifacts/installed-core-stderr.txt'
$taskOldPath = $env:PATH
$taskOldPythonHome = $env:PYTHONHOME
$taskOldPythonPath = $env:PYTHONPATH
try {
    $env:PATH = Join-Path $env:SystemRoot 'System32'
    $env:PYTHONHOME = 'fixture-missing-python'
    $env:PYTHONPATH = 'fixture-missing-python'
    $taskProcess = Start-Process -FilePath (Join-Path $taskInstallDir 'ai-asset-hub.exe') -ArgumentList "--verify-core `"$taskData`"" -PassThru -WindowStyle Hidden -RedirectStandardOutput $taskStdout -RedirectStandardError $taskStderr
    if (!$taskProcess.WaitForExit(15000) -or $taskProcess.ExitCode -ne 0) { throw 'Installed headless Core verification failed.' }
} finally {
    $env:PATH = $taskOldPath
    $env:PYTHONHOME = $taskOldPythonHome
    $env:PYTHONPATH = $taskOldPythonPath
}
$taskHealth = Get-Content -LiteralPath $taskStdout -Raw | ConvertFrom-Json
if (!$taskHealth.ok -or $taskHealth.data.database.status -ne 'ready' -or $taskHealth.data.database.schema_version -ne 3) { throw 'Installed Core/DB not ready.' }
if ((Get-Item -LiteralPath $taskStderr).Length -ne 0) { throw 'Unexpected installed Core stderr.' }
if (Get-Process -Id $taskHealth.data.core.pid -ErrorAction SilentlyContinue) { throw 'Core remained alive after verification.' }
$taskResult = @{ installation = $taskInstallDir; core_pid = $taskHealth.data.core.pid; database = $taskHealth.data.database; sidecar_sha256 = (Get-FileHash -LiteralPath $taskInstalledCore).Hash; gui_opened = $false }
$taskResult | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $taskRoot '.artifacts/r02-05-installed-result.json') -Encoding UTF8
# Retain test reports/data; uninstall only the isolated verification payload.
$taskUninstaller = Join-Path $taskInstallDir 'uninstall.exe'
$taskProcess = Start-Process -FilePath $taskUninstaller -ArgumentList '/S' -PassThru -WindowStyle Hidden
if (!$taskProcess.WaitForExit(60000) -or $taskProcess.ExitCode -ne 0) { throw 'Verification uninstall failed.' }
$taskUninstallDeadline = [DateTime]::UtcNow.AddSeconds(10)
while ((Test-Path -LiteralPath $taskKey) -and [DateTime]::UtcNow -lt $taskUninstallDeadline) { Start-Sleep -Milliseconds 100 }
if (Test-Path -LiteralPath $taskKey) { throw 'Verification registry entry remained.' }
if ($taskOriginal) {
    $taskAfter = Get-ItemProperty -LiteralPath $taskOriginalKey
    if ($taskAfter.InstallLocation -ne $taskOriginal.InstallLocation -or $taskAfter.DisplayVersion -ne $taskOriginal.DisplayVersion) { throw 'Original installation registration changed.' }
}
Write-Output 'Installed headless Core/SQLite verification passed; original installation preserved.'
