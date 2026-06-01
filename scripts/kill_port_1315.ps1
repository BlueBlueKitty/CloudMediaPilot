#!/usr/bin/env pwsh
[CmdletBinding(SupportsShouldProcess)]
param(
  [Parameter(Position = 0)]
  [int]$Port = 1315
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-PortOwningPids([int]$TargetPort) {
  return Get-NetTCPConnection -LocalPort $TargetPort -ErrorAction SilentlyContinue |
    Where-Object { $_.State -ne "TimeWait" } |
    Select-Object -ExpandProperty OwningProcess -Unique
}

function Get-KillCandidates([int[]]$Pids) {
  $all = New-Object System.Collections.Generic.HashSet[int]
  foreach ($pid in $Pids) {
    [void]$all.Add([int]$pid)
    $children = Get-CimInstance Win32_Process -Filter "ParentProcessId = $pid" -ErrorAction SilentlyContinue
    foreach ($child in $children) {
      [void]$all.Add([int]$child.ProcessId)
    }
    $pythonForks = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
      Where-Object { $_.CommandLine -and $_.CommandLine -match "parent_pid=$pid" }
    foreach ($child in $pythonForks) {
      [void]$all.Add([int]$child.ProcessId)
    }
  }
  return $all.ToArray()
}

$remaining = Get-PortOwningPids -TargetPort $Port
if (-not $remaining) {
  Write-Host "端口 $Port 当前没有监听进程。"
  exit 0
}

for ($round = 1; $round -le 3; $round++) {
  if (-not $remaining) { break }
  Write-Host "第 $round 轮清理，占用 PID: $($remaining -join ', ')"
  $candidates = Get-KillCandidates -Pids $remaining
  foreach ($procId in $candidates) {
    $name = "unknown"
    $cmd = "(无命令行信息)"
    try {
      $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $procId" -ErrorAction Stop
      if ($null -ne $proc) {
        if ($proc.PSObject.Properties["Name"] -and $proc.Name) { $name = [string]$proc.Name }
        if ($proc.PSObject.Properties["CommandLine"] -and $proc.CommandLine) { $cmd = [string]$proc.CommandLine }
      }
    } catch {}

    Write-Host "发现占用端口 $Port 的进程: PID=$procId Name=$name"
    Write-Host "CommandLine: $cmd"
    if ($PSCmdlet.ShouldProcess("PID $procId", "Stop-Process -Force / taskkill /T /F")) {
      try {
        Stop-Process -Id $procId -Force -ErrorAction Stop
      } catch {
        Write-Warning "Stop-Process 失败: $($_.Exception.Message)"
      }
      $taskkillOutput = & taskkill /PID $procId /T /F 2>&1
      if ($LASTEXITCODE -ne 0) {
        $text = ($taskkillOutput | Out-String).Trim()
        if ($text) {
          Write-Warning "taskkill 失败(PID=$procId): $text"
        }
      } else {
        Write-Host "已终止 PID=$procId 及其子进程"
      }
    }
  }
  Start-Sleep -Milliseconds 500
  $remaining = Get-PortOwningPids -TargetPort $Port
}

if ($remaining) {
  Write-Warning "端口 $Port 仍被占用，剩余 PID: $($remaining -join ', ')"
  Write-Warning "若进程权限较高，请使用管理员身份运行 PowerShell 后重试。"
  exit 1
}

Write-Host "端口 $Port 已释放。"
