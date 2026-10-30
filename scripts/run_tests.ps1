param([Parameter(Mandatory=$true)][string]$Blender)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$testNames = @('test_blender.py','test_efficiency.py','test_capture.py','test_capture_assembly.py','test_ai.py','test_repair.py','test_reconstruction.py','test_ui.py','test_sdk.py')
foreach ($testName in $testNames) {
    $testPath = Join-Path $projectRoot "tests/$testName"
    $logPath = Join-Path $projectRoot "tests/$($testName.Replace('.py','.log'))"
    & $Blender --background --factory-startup --python-exit-code 1 --python $testPath *> $logPath
    if ($LASTEXITCODE -ne 0) { throw "Test failed: $testName. See $logPath" }
    Write-Output "PASS $testName"
}
