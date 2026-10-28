#Requires -Version 5.1
# Builds dist/younit.mcpb from a clean staging folder (mcpb/build/).
$ErrorActionPreference = 'Stop'

$mcpbDir = $PSScriptRoot
$root    = Split-Path -Parent $mcpbDir
$stage   = Join-Path $mcpbDir 'build'
$distDir = Join-Path $root 'dist'
$output  = Join-Path $distDir 'younit.mcpb'
$utf8    = New-Object System.Text.UTF8Encoding($false)

function Invoke-Native([string]$What, [scriptblock]$Command) {
    & $Command
    if ($LASTEXITCODE -ne 0) { throw "$What failed (exit code $LASTEXITCODE)" }
}

# Version comes from the single source of truth.
$versionText = [IO.File]::ReadAllText((Join-Path $root 'src\younit\_version.py'))
if ($versionText -notmatch '__version__\s*=\s*"([^"]+)"') { throw 'Could not read __version__ from src/younit/_version.py' }
$version = $Matches[1]

# Clean staging.
if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
New-Item -ItemType Directory -Path $stage | Out-Null

# Allow-list of what goes into the bundle.
robocopy (Join-Path $root 'src\younit') (Join-Path $stage 'src\younit') /E /XD __pycache__ /XF *.pyc /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy failed (exit code $LASTEXITCODE)" }
foreach ($f in 'pyproject.toml', 'README.md', 'LICENSE', 'NOTICE') {
    Copy-Item (Join-Path $root $f) $stage
}
Copy-Item (Join-Path $mcpbDir '.mcpbignore') $stage
New-Item -ItemType Directory -Path (Join-Path $stage 'server') | Out-Null
Copy-Item (Join-Path $mcpbDir 'server\main.py') (Join-Path $stage 'server')

# Stamp the version into the staged manifest.
$manifest = [IO.File]::ReadAllText((Join-Path $mcpbDir 'manifest.json'))
$manifest = [regex]::Replace($manifest, '("version"\s*:\s*)"[^"]*"', "`$1`"$version`"", 1)
[IO.File]::WriteAllText((Join-Path $stage 'manifest.json'), $manifest, $utf8)

# Validate and pack.
Invoke-Native 'mcpb validate' { npx --yes @anthropic-ai/mcpb validate (Join-Path $stage 'manifest.json') }
New-Item -ItemType Directory -Force -Path $distDir | Out-Null
if (Test-Path $output) { Remove-Item $output -Force }
Invoke-Native 'mcpb pack' { npx --yes @anthropic-ai/mcpb pack $stage $output }

Write-Host "Built $output (version $version)"
