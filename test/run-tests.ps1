param(
    [ValidateSet('x64', 'Win32')]
    [string]$Platform = 'x64',
    [string]$PlatformToolset,
    [ValidateRange(1, 600)]
    [int]$TimeoutSeconds = 60
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
$outputDir = Join-Path $repoRoot "msbuild/tests/$Platform"
$project = Join-Path $PSScriptRoot 'TestResponseParser/TestResponseParser.vcxproj'
$arguments = @(
    $project, '/t:Build', '/nologo', '/verbosity:minimal',
    '/p:Configuration=Release', "/p:Platform=$Platform",
    "/p:SolutionDir=$repoRoot/", "/p:OutDir=$outputDir/"
)
if ($PlatformToolset) {
    $arguments += "/p:PLATFORM_TOOLSET=$PlatformToolset"
}
if ($env:SDKVER) {
    $arguments += "/p:WindowsTargetPlatformVersion=$env:SDKVER"
}

& msbuild @arguments
if ($LASTEXITCODE -ne 0) {
    throw "Test build failed with exit code $LASTEXITCODE."
}

$stdout = Join-Path $outputDir 'test.stdout.log'
$stderr = Join-Path $outputDir 'test.stderr.log'
$process = Start-Process -FilePath (Join-Path $outputDir 'TestResponseParser.exe') `
    -WorkingDirectory $repoRoot -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput $stdout -RedirectStandardError $stderr
try {
    if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
        Stop-Process -Id $process.Id -Force
        throw "IPC tests exceeded the $TimeoutSeconds second timeout."
    }
    $process.WaitForExit()
    if ($process.ExitCode -ne 0) {
        throw "IPC tests failed with exit code $($process.ExitCode)."
    }
} finally {
    Get-Content $stdout, $stderr -ErrorAction SilentlyContinue
    $process.Dispose()
}
