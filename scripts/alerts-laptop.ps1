# Sends the reader alert e-mails from this computer instead of GitHub Actions.
# One-time setup (PowerShell, in the filing-flows folder):
#   py -m pip install -r requirements.txt playwright
#   py -m playwright install chromium
#   copy scripts\alerts.env.example scripts\alerts.env      # then fill it in
# Run every 10 minutes (sends "Email me" requests quickly; alerts go out after each hourly site update):
#   schtasks /Create /TN "Filing Flows alerts" /SC MINUTE /MO 10 /TR "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File \"%CD%\scripts\alerts-laptop.ps1\""
# Remove it again:  schtasks /Delete /TN "Filing Flows alerts" /F

$root = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $PSScriptRoot "alerts.env"
$log = Join-Path $PSScriptRoot "alerts.log"
if (-not (Test-Path $envFile)) { Write-Error "Create $envFile from alerts.env.example first."; exit 1 }
Get-Content $envFile | ForEach-Object {
  if ($_ -match '^\s*([A-Z_]+)\s*=\s*(.*?)\s*$') { [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2].Trim('"'), "Process") }
}
$python = if (Get-Command py -ErrorAction SilentlyContinue) { "py" } else { "python" }
Set-Location $root
"--- $(Get-Date -Format s)" | Out-File -Append -Encoding utf8 $log
# reads the published site, renders the charts locally, sends through your SMTP account
& $python -m pipeline.notify --site $env:SITE_URL 2>&1 | ForEach-Object { "$_" } | Out-File -Append -Encoding utf8 $log
