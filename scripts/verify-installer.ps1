param([string]$AnalysisModel = '', [switch]$Mcp, [switch]$Multiformat, [switch]$BulkMetadata, [switch]$SmartDiscovery, [switch]$Unity, [string]$UnityEditor = '', [switch]$Upgrade, [string]$BaselineInstaller = '', [switch]$ReleaseChecks)
$ErrorActionPreference = 'Stop'
$taskRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$taskProofPython = Join-Path $taskRoot '.artifacts/core-build-venv/Scripts/python.exe'
$taskChecks = @()
if ($Mcp) { $taskChecks += 'mcp' }; if ($Unity) { $taskChecks += 'unity' }; if ($Multiformat) { $taskChecks += 'multiformat' }
if ($BulkMetadata) { $taskChecks += 'bulk' }; if ($SmartDiscovery) { $taskChecks += 'smart' }; if ($Upgrade) { $taskChecks += 'upgrade' }; if ($ReleaseChecks) { $taskChecks += 'release' }
if ($taskChecks.Count) {
    & $taskProofPython -B (Join-Path $taskRoot 'scripts/artifact_proof.py') --phase begin --checks ($taskChecks -join ',')
} else {
    & $taskProofPython -B (Join-Path $taskRoot 'scripts/artifact_proof.py') --phase begin
}
if ($LASTEXITCODE -ne 0) { throw 'Build/artifact proof failed before installation.' }
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
if ($Upgrade) {
    if (!(Test-Path -LiteralPath $BaselineInstaller -PathType Leaf)) { throw 'An actual previous isolated verification installer is required.' }
    $taskUpgradeRoot = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'local.aiassethub.m02verification'
    if (Test-Path -LiteralPath $taskUpgradeRoot) { throw 'Do not reuse an existing isolated AppData root.' }
    $taskOwnership = [guid]::NewGuid().ToString()
    New-Item -ItemType Directory -Path $taskUpgradeRoot | Out-Null
    Set-Content -LiteralPath (Join-Path $taskUpgradeRoot '.m10-owned') -Value $taskOwnership -Encoding ascii
    $taskUpgradeData = Join-Path $taskUpgradeRoot 'data'
    $taskUpgradeState = Join-Path $taskRoot '.artifacts/m10-upgrade-state.json'
    $taskUpgradeSource = Join-Path $taskRoot ('.artifacts/m10-upgrade-source-' + [guid]::NewGuid().ToString())
    $taskHarnessPython = Join-Path $taskRoot '.artifacts/core-build-venv/Scripts/python.exe'
    $taskProcess = Start-Process -FilePath $BaselineInstaller -ArgumentList "/S /NS /D=$taskInstallDir" -PassThru -WindowStyle Hidden
    if (!$taskProcess.WaitForExit(60000) -or $taskProcess.ExitCode -ne 0) { throw 'Baseline silent installation failed.' }
    & $taskHarnessPython -B (Join-Path $taskRoot 'scripts/verify-release-data.py') --mode seed --core (Join-Path $taskInstallDir 'ai-asset-hub-core.exe') --data $taskUpgradeData --state $taskUpgradeState --source $taskUpgradeSource
    if ($LASTEXITCODE -ne 0) { throw 'Baseline data fixture failed.' }
}
$taskProcess = Start-Process -FilePath $taskInstaller -ArgumentList "/S /NS /D=$taskInstallDir" -PassThru -WindowStyle Hidden
if (!$taskProcess.WaitForExit(60000) -or $taskProcess.ExitCode -ne 0) { throw 'Silent verification installation failed.' }
$taskRegistry = Get-ItemProperty -LiteralPath $taskKey
if ($taskRegistry.DisplayVersion -ne '0.5.0') { throw 'Installed version mismatch.' }
$taskSourceCore = Join-Path $taskRoot 'src-tauri/binaries/ai-asset-hub-core-x86_64-pc-windows-msvc.exe'
$taskInstalledCore = Join-Path $taskInstallDir 'ai-asset-hub-core.exe'
if ((Get-FileHash -LiteralPath $taskSourceCore).Hash -ne (Get-FileHash -LiteralPath $taskInstalledCore).Hash) { throw 'Installed Sidecar hash mismatch.' }
if ($Upgrade) {
    & $taskHarnessPython -B (Join-Path $taskRoot 'scripts/verify-release-data.py') --mode check --core $taskInstalledCore --data $taskUpgradeData --state $taskUpgradeState
    if ($LASTEXITCODE -ne 0) { throw 'Same-version update did not preserve data.' }
    # Exercise the version comparison branch with an explicitly synthetic older registration.
    Set-ItemProperty -LiteralPath $taskKey -Name DisplayVersion -Value '0.4.9'
    $taskProcess = Start-Process -FilePath $taskInstaller -ArgumentList "/S /NS /UPDATE /D=$taskInstallDir" -PassThru -WindowStyle Hidden
    if (!$taskProcess.WaitForExit(60000) -or $taskProcess.ExitCode -ne 0) { throw 'Synthetic older-version registration update failed.' }
    & $taskHarnessPython -B (Join-Path $taskRoot 'scripts/verify-release-data.py') --mode check --core $taskInstalledCore --data $taskUpgradeData --state $taskUpgradeState
    if ($LASTEXITCODE -ne 0) { throw 'Version-branch update did not preserve data.' }
    try {
        Set-ItemProperty -LiteralPath $taskKey -Name DisplayVersion -Value '0.6.0'
        $taskProcess = Start-Process -FilePath $taskInstaller -ArgumentList "/S /NS /D=$taskInstallDir" -PassThru -WindowStyle Hidden
        if (!$taskProcess.WaitForExit(60000) -or $taskProcess.ExitCode -eq 0) { throw 'Downgrade should be rejected.' }
        if ((Get-FileHash -LiteralPath $taskInstalledCore).Hash -ne (Get-FileHash -LiteralPath $taskSourceCore).Hash) { throw 'Downgrade modified the installed payload.' }
    } finally { Set-ItemProperty -LiteralPath $taskKey -Name DisplayVersion -Value '0.5.0' }
}
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
if (!$taskHealth.ok -or $taskHealth.data.database.status -ne 'ready' -or $taskHealth.data.database.schema_version -ne @(Get-ChildItem -LiteralPath (Join-Path $taskRoot 'db/migrations') -Filter '*.sql').Count) { throw 'Installed Core/DB not ready.' }
if ((Get-Item -LiteralPath $taskStderr).Length -ne 0) { throw 'Unexpected installed Core stderr.' }
if (Get-Process -Id $taskHealth.data.core.pid -ErrorAction SilentlyContinue) { throw 'Core remained alive after verification.' }
$taskResult = @{ installation = $taskInstallDir; core_pid = $taskHealth.data.core.pid; database = $taskHealth.data.database; sidecar_sha256 = (Get-FileHash -LiteralPath $taskInstalledCore).Hash; gui_opened = $false }
$taskResult | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $taskRoot '.artifacts/r02-05-installed-result.json') -Encoding UTF8
if ($AnalysisModel) {
    $taskHarnessPython = Join-Path $taskRoot '.artifacts/core-build-venv/Scripts/python.exe'
    & $taskHarnessPython (Join-Path $taskRoot 'scripts/verify-local-analysis.py') --model $AnalysisModel --sidecar $taskInstalledCore --report (Join-Path $taskRoot '.artifacts/m06-installed-analysis.json')
    if ($LASTEXITCODE -ne 0) { throw 'Installed real model analysis verification failed.' }
}
if ($Mcp) {
    $taskHarnessPython = Join-Path $taskRoot '.artifacts/core-build-venv/Scripts/python.exe'
    & $taskHarnessPython -B (Join-Path $taskRoot 'scripts/verify-mcp.py') --core $taskInstalledCore --report (Join-Path $taskRoot '.artifacts/m08-installed-host.json')
    if ($LASTEXITCODE -ne 0) { throw 'Installed MCP reference Host verification failed.' }
}
if ($Unity) {
    if (!(Test-Path -LiteralPath $UnityEditor -PathType Leaf)) { throw 'An explicit installed Unity Editor executable is required for headless verification.' }
    $taskHarnessPython = Join-Path $taskRoot '.artifacts/core-build-venv/Scripts/python.exe'
    $taskUnityPackage = Join-Path $taskInstallDir 'unity-package'
    if ((Get-FileHash -LiteralPath (Join-Path $taskRoot 'unity-package/Editor/Connector.cs')).Hash -ne (Get-FileHash -LiteralPath (Join-Path $taskUnityPackage 'Editor/Connector.cs')).Hash) { throw 'Installed Unity connector hash mismatch.' }
    & $taskHarnessPython -B (Join-Path $taskRoot 'scripts/verify-unity-host.py') --editor $UnityEditor --core $taskInstalledCore --package $taskUnityPackage --report (Join-Path $taskRoot '.artifacts/m09-installed-unity-host.json')
    if ($LASTEXITCODE -ne 0) { throw 'Installed Core/Host/Unity headless verification failed.' }
}
if ($Multiformat) {
    $taskHarnessPython = Join-Path $taskRoot '.artifacts/core-build-venv/Scripts/python.exe'
    & $taskHarnessPython -B (Join-Path $taskRoot 'scripts/verify-multiformat.py') --core $taskInstalledCore --report (Join-Path $taskRoot '.artifacts/m08f-installed-multiformat.json')
    if ($LASTEXITCODE -ne 0) { throw 'Installed multiformat verification failed.' }
}
if ($BulkMetadata) {
    $taskHarnessPython = Join-Path $taskRoot '.artifacts/core-build-venv/Scripts/python.exe'
    & $taskHarnessPython -B (Join-Path $taskRoot 'scripts/verify-bulk-metadata.py') --core $taskInstalledCore --report (Join-Path $taskRoot '.artifacts/m08g-installed-metadata.json')
    if ($LASTEXITCODE -ne 0) { throw 'Installed bulk metadata verification failed.' }
}
if ($SmartDiscovery) {
    $taskHarnessPython = Join-Path $taskRoot '.artifacts/core-build-venv/Scripts/python.exe'
    & $taskHarnessPython -B (Join-Path $taskRoot 'scripts/verify-smart-discovery.py') --core $taskInstalledCore --report (Join-Path $taskRoot '.artifacts/m08i-installed-discovery.json')
    if ($LASTEXITCODE -ne 0) { throw 'Installed smart discovery verification failed.' }
}
# Retain test reports/data; uninstall only the isolated verification payload.
if ($ReleaseChecks) {
    $taskHarnessPython = Join-Path $taskRoot '.artifacts/core-build-venv/Scripts/python.exe'
    & $taskHarnessPython -B (Join-Path $taskRoot 'scripts/verify-release.py') --core $taskInstalledCore --report (Join-Path $taskRoot '.artifacts/m10-installed-acceptance.json')
    if ($LASTEXITCODE -ne 0) { throw 'Installed maintenance/background-scan acceptance failed.' }
}
$taskUninstaller = Join-Path $taskInstallDir 'uninstall.exe'
$taskProcess = Start-Process -FilePath $taskUninstaller -ArgumentList '/S' -PassThru -WindowStyle Hidden
if (!$taskProcess.WaitForExit(60000) -or $taskProcess.ExitCode -ne 0) { throw 'Verification uninstall failed.' }
$taskUninstallDeadline = [DateTime]::UtcNow.AddSeconds(10)
while ((Test-Path -LiteralPath $taskKey) -and [DateTime]::UtcNow -lt $taskUninstallDeadline) { Start-Sleep -Milliseconds 100 }
if (Test-Path -LiteralPath $taskKey) { throw 'Verification registry entry remained.' }
if ($Upgrade) {
    & $taskHarnessPython -B (Join-Path $taskRoot 'scripts/verify-release-data.py') --mode retained --data $taskUpgradeData --state $taskUpgradeState
    if ($LASTEXITCODE -ne 0) { throw 'Silent uninstall removed or modified user-data fixtures.' }
    @{ passed=$true; actualPreviousPayload='M09 0.5.0'; sameVersionUpdated=$true; syntheticOlderVersionBranch=$true; downgradeBlocked=$true; uninstallRetainedData=$true; guiOpened=$false; baselineSha256=(Get-FileHash -LiteralPath $BaselineInstaller).Hash } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskRoot '.artifacts/m10-upgrade-result.json') -Encoding UTF8
    # Preserve the newly created, ownership-marked AppData fixture under workspace artifacts.
    $taskExpectedUpgradeRoot = [IO.Path]::GetFullPath((Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'local.aiassethub.m02verification'))
    $taskResolvedUpgradeRoot = (Get-Item -LiteralPath $taskUpgradeRoot).FullName
    if ($taskResolvedUpgradeRoot -ne $taskExpectedUpgradeRoot -or ((Get-Item -LiteralPath $taskUpgradeRoot).Attributes -band [IO.FileAttributes]::ReparsePoint) -or (Get-Content -LiteralPath (Join-Path $taskUpgradeRoot '.m10-owned') -Raw).Trim() -ne $taskOwnership) { throw 'AppData fixture cleanup scope failed.' }
    $taskRetainedArchive = [IO.Path]::GetFullPath((Join-Path $taskRoot ('.artifacts/m10-retained-appdata-' + [guid]::NewGuid().ToString())))
    if (!$taskRetainedArchive.StartsWith($taskArtifactPrefix, [StringComparison]::OrdinalIgnoreCase) -or (Test-Path -LiteralPath $taskRetainedArchive)) { throw 'Retained fixture archive scope failed.' }
    Move-Item -LiteralPath $taskResolvedUpgradeRoot -Destination $taskRetainedArchive
}
if ($taskOriginal) {
    $taskAfter = Get-ItemProperty -LiteralPath $taskOriginalKey
    if ($taskAfter.InstallLocation -ne $taskOriginal.InstallLocation -or $taskAfter.DisplayVersion -ne $taskOriginal.DisplayVersion) { throw 'Original installation registration changed.' }
}
& $taskProofPython -B (Join-Path $taskRoot 'scripts/artifact_proof.py') --phase finish
if ($LASTEXITCODE -ne 0) { throw 'Artifacts changed during installation verification.' }
Write-Output 'Installed headless Core/SQLite verification passed; original installation preserved.'
