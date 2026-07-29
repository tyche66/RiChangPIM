param(
  [string]$WslIp = '198.18.0.1',
  [int]$FrontendListenPort = 3001,
  [int]$FrontendTargetPort = 5173,
  [int]$BackendListenPort = 8000,
  [int]$BackendTargetPort = 8000,
  [int]$AiListenPort = 888,
  [int]$AiTargetPort = 888
)

$ErrorActionPreference = 'Stop'

function Ensure-PortProxy {
  param(
    [int]$ListenPort,
    [int]$TargetPort
  )

  & netsh interface portproxy delete v4tov4 listenport=$ListenPort 2>$null | Out-Null
  & netsh interface portproxy add v4tov4 listenport=$ListenPort connectaddress=$WslIp connectport=$TargetPort
}

function Ensure-FirewallRule {
  param(
    [int]$Port,
    [string]$Name
  )

  $exists = Get-NetFirewallRule -DisplayName $Name -ErrorAction SilentlyContinue
  if (-not $exists) {
    New-NetFirewallRule -DisplayName $Name -Direction Inbound -LocalPort $Port -Protocol TCP -Action Allow | Out-Null
  }
}

Ensure-PortProxy -ListenPort $FrontendListenPort -TargetPort $FrontendTargetPort
Ensure-PortProxy -ListenPort $BackendListenPort -TargetPort $BackendTargetPort
Ensure-PortProxy -ListenPort $AiListenPort -TargetPort $AiTargetPort
Ensure-FirewallRule -Port $FrontendListenPort -Name 'AI-PIM Demo Frontend 3001'
Ensure-FirewallRule -Port $BackendListenPort -Name 'AI-PIM Demo Backend 8000'
Ensure-FirewallRule -Port $AiListenPort -Name 'AI-PIM Demo AI 888'

Write-Host '==> portproxy configured:'
& netsh interface portproxy show all

Write-Host ''
Write-Host '==> Funnel commands:'
Write-Host "tailscale funnel $FrontendListenPort   # recommended public AI Portal / demo entry"
Write-Host "tailscale funnel $BackendListenPort"
Write-Host "tailscale funnel $AiListenPort         # optional direct Docker nginx entry"
