# Copies the VM's daily database backups (deploy/oracle/backups/*.gz) to this PC.
# Run daily by the Windows scheduled task "FinanceBot DB backup pull" (see README).
param(
    [string]$HostName = "ubuntu@84.235.164.222",
    [string]$Key = "$env:USERPROFILE\.ssh\oracle_finance_bot",
    [string]$Dest = (Join-Path $PSScriptRoot "backups")
)

New-Item -ItemType Directory -Force $Dest | Out-Null
$log = Join-Path $Dest "pull.log"
$output = & scp -q -o BatchMode=yes -i $Key "${HostName}:finance-ai-bot/deploy/oracle/backups/*.gz" $Dest 2>&1
$code = $LASTEXITCODE
"$(Get-Date -Format s) exit=$code $output" | Out-File -Append -Encoding utf8 $log
exit $code
