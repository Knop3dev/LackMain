$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$Root = $PSScriptRoot
$Miner = Join-Path $Root 'lackminer-qbtc.exe'
$ConfigPath = Join-Path $Root 'miner-config.json'
$NodeDir = Join-Path $Root 'node\official\v2.5.0'
$NodeExe = Join-Path $NodeDir 'quantum-btc.exe'
$NodeUrl = 'http://127.0.0.1:24002'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$Config = @{ user=''; device=0; max_power=120; intensity=100; mode='pool'; backend='gpu'; cpu_threads=2; pool='stratum+ssl://ashenward.ru:3336' }
if (Test-Path -LiteralPath $ConfigPath) {
  $saved = Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json
  foreach ($name in @('user','device','max_power','intensity','mode','backend','cpu_threads','pool')) {
    if ($null -ne $saved.$name) { $Config[$name] = $saved.$name }
  }
}
if ($Config.pool -eq 'stratum+tcp://ashenward.ru:3334') { $Config.pool = 'stratum+ssl://ashenward.ru:3336' }
$answer = Read-Host "Mode: pool or solo [$($Config.mode)]"
if ($answer) { $Config.mode = $answer.ToLowerInvariant() }
if ($Config.mode -notin @('pool','solo')) { throw 'Choose pool or solo' }
if ($Config.mode -eq 'pool') {
  $answer = Read-Host "Backend: cpu or gpu [$($Config.backend)]"
  if ($answer) { $Config.backend = $answer.ToLowerInvariant() }
  if ($Config.backend -notin @('cpu','gpu')) { throw 'Choose cpu or gpu' }
}
$answer = Read-Host "Public Q-BTC payout address [$($Config.user)]"
if ($answer) { $Config.user = $answer }
& $Miner --validate-address --user $Config.user
if ($LASTEXITCODE -ne 0) { throw 'Invalid Q-BTC address' }
if ($Config.mode -eq 'pool' -and $Config.backend -eq 'cpu') {
  $answer = Read-Host "CPU threads [$($Config.cpu_threads)]"
  if ($answer) { $Config.cpu_threads = [int]$answer }
} else {
  & $Miner --list-devices
  $answer = Read-Host "GPU index [$($Config.device)]"
  if ($answer) { $Config.device = [int]$answer }
  $answer = Read-Host "Measured GPU power budget in W [$($Config.max_power)]"
  if ($answer) { $Config.max_power = [double]$answer }
  $answer = Read-Host "Intensity 1..100 [$($Config.intensity)]"
  if ($answer) { $Config.intensity = [int]$answer }
}
if ($Config.mode -eq 'pool') {
  $answer = Read-Host "Pool URL [$($Config.pool)]"
  if ($answer) { $Config.pool = $answer }
  Write-Host 'LackPool: 1.5% fee, PPLNS rewards, minimum payout 10 QBTC. No additional SOLO fee.'
  if ((Read-Host 'Start pool mining? Type YES') -cne 'YES') { exit 0 }
  $Config | ConvertTo-Json | Set-Content -LiteralPath $ConfigPath -Encoding utf8
  $worker = $Config.user + '.' + $env:COMPUTERNAME
  $arguments = @('--pool',$Config.pool,'--user',$worker,'--log-file',(Join-Path $Root 'miner.jsonl'),'--stats-file',(Join-Path $Root 'stats.json'))
  if ($Config.backend -eq 'cpu') { $arguments += @('--cpu','--cpu-threads',[string]$Config.cpu_threads) }
  else { $arguments += @('--device',[string]$Config.device,'--max-power',[string]$Config.max_power,'--intensity',[string]$Config.intensity) }
  & $Miner @arguments
  exit $LASTEXITCODE
}
Write-Host 'Fee: 10% of the entire coinbase (subsidy + transaction fees); 90% to your address.'
if ((Read-Host 'Start SOLO mining? Type YES') -cne 'YES') { exit 0 }
$Config | ConvertTo-Json | Set-Content -LiteralPath $ConfigPath -Encoding utf8
if (-not (Test-Path -LiteralPath $NodeExe)) {
  New-Item -ItemType Directory -Force -Path $NodeDir | Out-Null
  $archive = Join-Path $Root 'node\qbtc-core-windows.zip'
  Invoke-WebRequest -UseBasicParsing -Uri 'https://github.com/Q-Jack-core/quantum-btc/releases/download/v2.5.0/qbtc-core-windows.zip' -OutFile $archive
  if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne '3a9e7a9ac49ff7ca7a2973175b978bfdc784a4ee58d6d441fa99fa87c1c89375') { throw 'Official node SHA-256 mismatch' }
  $temp = Join-Path $Root ('node\extract-' + [guid]::NewGuid().ToString('N'))
  Expand-Archive -LiteralPath $archive -DestinationPath $temp
  $matches = @(Get-ChildItem -LiteralPath $temp -Filter quantum-btc.exe -File -Recurse)
  if ($matches.Count -ne 1) { throw 'Invalid official node archive' }
  Copy-Item -LiteralPath $matches[0].FullName -Destination $NodeExe
  $resolved = [IO.Path]::GetFullPath($temp)
  $allowed = [IO.Path]::GetFullPath((Join-Path $Root 'node')) + [IO.Path]::DirectorySeparatorChar
  if (-not $resolved.StartsWith($allowed, [StringComparison]::OrdinalIgnoreCase)) { throw 'Invalid cleanup path' }
  Remove-Item -LiteralPath $resolved -Recurse -Force
  Remove-Item -LiteralPath $archive -Force
}
$ready = $false
try { $null = Invoke-RestMethod "$NodeUrl/api/get_info" -TimeoutSec 2; $ready = $true } catch {}
if (-not $ready) {
  $data = Join-Path $Root 'node\data'
  New-Item -ItemType Directory -Force -Path $data | Out-Null
  Start-Process -FilePath $NodeExe -ArgumentList "--port 20001 --datadir `"$data`"" -WorkingDirectory $Root -WindowStyle Hidden -RedirectStandardOutput (Join-Path $Root 'node\node-console.log') -RedirectStandardError (Join-Path $Root 'node\node-error.log') | Out-Null
  for ($i=0; $i -lt 90; $i++) {
    Start-Sleep 1
    try { $null = Invoke-RestMethod "$NodeUrl/api/get_info" -TimeoutSec 2; $ready = $true; break } catch {}
  }
}
if (-not $ready) { throw 'Local node unavailable; inspect node logs' }
while ($true) {
  & $Miner --solo --node $NodeUrl --user $Config.user --device $Config.device --max-power $Config.max_power --intensity $Config.intensity --log-file (Join-Path $Root 'miner.jsonl') --stats-file (Join-Path $Root 'stats.json')
  if ($LASTEXITCODE -eq 0) { break }
  Write-Host 'Miner failed; retrying in 10 seconds. Ctrl+C to stop.'
  Start-Sleep 10
}
