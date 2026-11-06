[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$runtimeDirectory = Join-Path $projectRoot '.runtime'
$credentialPath = Join-Path $runtimeDirectory 'data-go-kr-credential.xml'

New-Item -ItemType Directory -Path $runtimeDirectory -Force | Out-Null
$credential = Get-Credential -Message '공공데이터포털 아이디와 비밀번호를 입력하세요. 이 PC의 현재 Windows 사용자만 복호화할 수 있습니다.'
if (-not $credential) {
    throw '자격 증명 입력이 취소되었습니다.'
}

$credential | Export-Clixml -LiteralPath $credentialPath -Force
Write-Output '공공데이터포털 로그인 정보가 Windows DPAPI로 암호화되어 .runtime에 저장되었습니다.'

