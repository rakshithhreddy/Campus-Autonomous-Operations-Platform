$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location (Join-Path $root "frontend")
npm run dev -- --host 0.0.0.0 --port 3006
