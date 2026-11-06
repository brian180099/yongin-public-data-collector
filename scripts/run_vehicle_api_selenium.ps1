[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$credentialPath = Join-Path $projectRoot '.runtime\data-go-kr-credential.xml'
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$automationPath = Join-Path $PSScriptRoot 'apply_vehicle_api_selenium.py'

if (-not (Test-Path -LiteralPath $credentialPath)) {
    throw '저장된 로그인 정보가 없습니다. 먼저 scripts\configure_portal_credentials.ps1을 실행하세요.'
}
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw '.venv Python을 찾을 수 없습니다.'
}

$credential = Import-Clixml -LiteralPath $credentialPath
$env:DATA_GO_KR_PORTAL_USERNAME = $credential.UserName
$env:DATA_GO_KR_PORTAL_PASSWORD = $credential.GetNetworkCredential().Password
try {
    & $pythonPath $automationPath
    exit $LASTEXITCODE
}
finally {
    Remove-Item Env:DATA_GO_KR_PORTAL_USERNAME -ErrorAction SilentlyContinue
    Remove-Item Env:DATA_GO_KR_PORTAL_PASSWORD -ErrorAction SilentlyContinue
}
