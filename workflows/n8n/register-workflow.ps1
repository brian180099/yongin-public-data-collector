param(
    [string]$ContainerName = "n8n",
    [string]$WorkflowName = "YONGIN_01_공공데이터_수집갱신",
    [string]$WorkflowId = "YNGN01CollectWk1"
)

$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$workflow = Join-Path $PSScriptRoot "yongin-weekly-collector.json"
if (-not (Test-Path -LiteralPath $workflow)) {
    throw "Workflow JSON not found: $workflow"
}

$running = docker inspect -f '{{.State.Running}}' $ContainerName 2>$null
if ($running -ne "true") {
    throw "Existing n8n container is not running: $ContainerName"
}

$existing = docker exec $ContainerName n8n list:workflow
if ($existing -match [regex]::Escape("$WorkflowId|")) {
    throw "Workflow already exists; refusing to create a duplicate: $WorkflowName"
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupDir = "C:\n8n\backups\before-yongin-$stamp"
New-Item -ItemType Directory -Path $backupDir | Out-Null
docker exec $ContainerName n8n export:workflow --all --output=/tmp/all-workflows.json | Out-Null
docker cp "${ContainerName}:/tmp/all-workflows.json" "$backupDir\all-workflows.json" | Out-Null
docker exec -u root $ContainerName rm -f /tmp/all-workflows.json | Out-Null

docker cp $workflow "${ContainerName}:/tmp/yongin-weekly-collector.json" | Out-Null
docker exec $ContainerName n8n import:workflow `
    --input=/tmp/yongin-weekly-collector.json --activeState=false
docker exec -u root $ContainerName rm -f /tmp/yongin-weekly-collector.json | Out-Null

$created = docker exec $ContainerName n8n list:workflow |
    Where-Object { $_ -match [regex]::Escape("$WorkflowId|") }
if (-not $created) {
    throw "Import command completed but workflow was not found"
}
Write-Output "backup=$backupDir"
Write-Output "workflow=$created"
