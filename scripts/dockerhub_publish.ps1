#!/usr/bin/env pwsh
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

param(
  [string]$Version = $null
)

$DockerhubUser = if ($env:DOCKERHUB_USER) { $env:DOCKERHUB_USER } else { "bluebluekitty" }
$ImageName = if ($env:IMAGE_NAME) { $env:IMAGE_NAME } else { "cloudmediapilot" }
$Version = if ($Version) { $Version } elseif ($env:VERSION) { $env:VERSION } else { "0.1.0" }
$Dockerfile = if ($env:DOCKERFILE) { $env:DOCKERFILE } else { "backend/Dockerfile" }
$Context = if ($env:CONTEXT) { $env:CONTEXT } else { "." }

if ([string]::IsNullOrWhiteSpace($Version)) {
  Write-Error "用法: .\scripts\dockerhub_publish.ps1 <version>`n示例: .\scripts\dockerhub_publish.ps1 0.1.1"
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
