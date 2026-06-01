#!/usr/bin/env pwsh
param(
  [string]$Version = $null
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$DockerhubUser = if ($env:DOCKERHUB_USER) { $env:DOCKERHUB_USER } else { "bluebluekitty" }
$ImageName = if ($env:IMAGE_NAME) { $env:IMAGE_NAME } else { "cloudmediapilot" }
$Dockerfile = if ($env:DOCKERFILE) { $env:DOCKERFILE } else { "backend/Dockerfile" }
$Context = if ($env:CONTEXT) { $env:CONTEXT } else { "." }

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptRoot
$VersionFile = Join-Path $RepoRoot "backend/app/meta/version.json"
$DefaultVersion = $null

if (Test-Path $VersionFile) {
  try {
    $VersionMeta = Get-Content $VersionFile -Raw -Encoding UTF8 | ConvertFrom-Json
    $DefaultVersion = [string]$VersionMeta.current_version
  } catch {
    Write-Warning "读取版本文件失败: $VersionFile"
  }
}

$Version = if ($Version) { $Version } elseif ($env:VERSION) { $env:VERSION } else { $null }

if ([string]::IsNullOrWhiteSpace($Version)) {
  $Prompt = if ([string]::IsNullOrWhiteSpace($DefaultVersion)) {
    "请输入版本号 (例如 0.1.1)"
  } else {
    "请输入版本号 (直接回车使用默认: $DefaultVersion)"
  }
  $InputVersion = Read-Host $Prompt
  if ([string]::IsNullOrWhiteSpace($InputVersion)) {
    $Version = $DefaultVersion
  } else {
    $Version = $InputVersion
  }
}

if ([string]::IsNullOrWhiteSpace($Version)) {
  Write-Error "版本号不能为空，且未能从 backend/app/meta/version.json 读取默认版本。"
  exit 1
}

# if (-not $env:DOCKERHUB_TOKEN) {
#   Write-Error "请先设置 DOCKERHUB_TOKEN 环境变量，不建议在脚本中写死密码。`n示例: `$env:DOCKERHUB_TOKEN='xxxx'"
#   exit 1
# }

$Image = "$DockerhubUser/$ImageName"

# Write-Host "[1/4] 登录 Docker Hub: $DockerhubUser"
# $env:DOCKERHUB_TOKEN | docker login -u $DockerhubUser --password-stdin

Write-Host "[2/4] 构建镜像: ${Image}:$Version"
docker build `
  --build-arg "APP_VERSION=$Version" `
  -f $Dockerfile `
  -t "${Image}:$Version" `
  -t "${Image}:latest" `
  $Context

Write-Host "[3/4] 推送版本标签: ${Image}:$Version"
docker push "${Image}:$Version"

Write-Host "[4/4] 推送 latest 标签: ${Image}:latest"
docker push "${Image}:latest"

Write-Host "完成: ${Image}:$Version 和 ${Image}:latest"
