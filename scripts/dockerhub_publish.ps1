#!/usr/bin/env pwsh
param(
  [string]$Version = $null
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-NextPatchVersion {
  param(
    [string]$BaseVersion
  )

  if ([string]::IsNullOrWhiteSpace($BaseVersion)) {
    return $null
  }

  $VersionMatch = [regex]::Match($BaseVersion.Trim(), '^(?<major>\d+)\.(?<minor>\d+)\.(?<patch>\d+)$')
  if (-not $VersionMatch.Success) {
    return $BaseVersion.Trim()
  }

  return "{0}.{1}.{2}" -f $VersionMatch.Groups['major'].Value, $VersionMatch.Groups['minor'].Value, ([int]$VersionMatch.Groups['patch'].Value + 1)
}

function Get-LatestDockerHubVersion {
  param(
    [string]$DockerhubUser,
    [string]$ImageName
  )

  $TagsApiUrl = "https://hub.docker.com/v2/repositories/$DockerhubUser/$ImageName/tags/?page_size=100"
  $SemanticVersions = New-Object System.Collections.Generic.List[version]

  try {
    while (-not [string]::IsNullOrWhiteSpace($TagsApiUrl)) {
      $Response = Invoke-RestMethod -Uri $TagsApiUrl -Method Get
      foreach ($Tag in @($Response.results)) {
        $TagName = [string]$Tag.name
        if ($TagName -match '^\d+\.\d+\.\d+$') {
          [void]$SemanticVersions.Add([version]$TagName)
        }
      }
      $TagsApiUrl = [string]$Response.next
    }
  } catch {
    Write-Warning "查询 Docker Hub 最新版本失败，将回退到本地 version.json。$($_.Exception.Message)"
    return $null
  }

  if ($SemanticVersions.Count -eq 0) {
    return $null
  }

  return ($SemanticVersions | Sort-Object -Descending | Select-Object -First 1).ToString()
}

function Update-VersionFile {
  param(
    [string]$VersionFile,
    [string]$Version
  )

  $VersionFilePath = Resolve-Path $VersionFile
  $PythonScript = @'
import json
import os
import pathlib
import sys

version_file = pathlib.Path(os.environ["VERSION_FILE"])
version = os.environ["TARGET_VERSION"].strip()

data = json.loads(version_file.read_text(encoding="utf-8"))
if not isinstance(data, dict):
    raise SystemExit("version.json 格式不正确")

data["current_version"] = version
version_file.write_text(
    json.dumps(data, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
'@

  $env:VERSION_FILE = [string]$VersionFilePath
  $env:TARGET_VERSION = $Version
  try {
    $PythonScript | python -
  } finally {
    Remove-Item Env:VERSION_FILE -ErrorAction SilentlyContinue
    Remove-Item Env:TARGET_VERSION -ErrorAction SilentlyContinue
  }
}

$DockerhubUser = if ($env:DOCKERHUB_USER) { $env:DOCKERHUB_USER } else { "bluebluekitty" }
$ImageName = if ($env:IMAGE_NAME) { $env:IMAGE_NAME } else { "cloudmediapilot" }
$Dockerfile = if ($env:DOCKERFILE) { $env:DOCKERFILE } else { "backend/Dockerfile" }
$Context = if ($env:CONTEXT) { $env:CONTEXT } else { "." }

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptRoot
$VersionFile = Join-Path $RepoRoot "backend/app/meta/version.json"
$DockerHubLatestVersion = Get-LatestDockerHubVersion -DockerhubUser $DockerhubUser -ImageName $ImageName
$LocalLatestVersion = $null
$LatestVersionSource = $null
$LatestVersion = $null
$DefaultVersion = $null

if (Test-Path $VersionFile) {
  try {
    $VersionMeta = Get-Content $VersionFile -Raw -Encoding UTF8 | ConvertFrom-Json
    $LocalLatestVersion = [string]$VersionMeta.current_version
  } catch {
    Write-Warning "读取版本文件失败: $VersionFile"
  }
}

$LatestVersion = if (-not [string]::IsNullOrWhiteSpace($DockerHubLatestVersion)) { $DockerHubLatestVersion } else { $LocalLatestVersion }
$LatestVersionSource = if (-not [string]::IsNullOrWhiteSpace($DockerHubLatestVersion)) { "Docker Hub" } elseif (-not [string]::IsNullOrWhiteSpace($LocalLatestVersion)) { "本地 version.json" } else { $null }
$DefaultVersion = Get-NextPatchVersion -BaseVersion $LatestVersion

if (-not [string]::IsNullOrWhiteSpace($LatestVersion)) {
  Write-Host "当前最新版本 ($LatestVersionSource): $LatestVersion"
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
  Write-Error "版本号不能为空，且未能从 backend/app/meta/version.json 读取当前最新版本。"
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

Update-VersionFile -VersionFile $VersionFile -Version $Version
Write-Host "已更新版本文件: $VersionFile -> $Version"

Write-Host "完成: ${Image}:$Version 和 ${Image}:latest"
