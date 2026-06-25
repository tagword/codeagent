<#
.SYNOPSIS
  CodeAgent — Windows 一键运行脚本
  首次运行自动安装依赖，之后直接启动
.DESCRIPTION
  用法:
    .\run.ps1                        # 首次自动安装，然后启动
    .\run.ps1 -NoInstall             # 仅启动（跳过安装检查）
    .\run.ps1 -Port 8766             # 指定端口
    .\run.ps1 -Host 0.0.0.0          # 指定监听地址
#>

param(
  [switch]$NoInstall,
  [int]$Port = 8765,
  [string]$Host = "0.0.0.0"
)

$ErrorActionPreference = "Stop"

# ── 颜色输出 ──────────────────────────────────────────────────────────
function info  { Write-Host "▶ " -NoNewline -ForegroundColor Cyan; Write-Host "$args" }
function ok    { Write-Host "✓ " -NoNewline -ForegroundColor Green; Write-Host "$args" }
function warn  { Write-Host "⚠ " -NoNewline -ForegroundColor Yellow; Write-Host "$args" }
function err   { Write-Host "✗ " -NoNewline -ForegroundColor Red; Write-Host "$args"; exit 1 }

# ── 项目根目录 ──────────────────────────────────────────────────────
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
info "项目目录: $projectRoot"

# ── 安装阶段 ──────────────────────────────────────────────────────────
if (-not $NoInstall) {
  Write-Host "─── 🔧 环境检查 ───" -ForegroundColor Blue

  # Python 检测
  $python = $null
  foreach ($cmd in @("python3", "python")) {
    try { $ver = & $cmd --version 2>&1; $python = $cmd; break } catch {}
  }
  if (-not $python) { err "未检测到 Python，请先安装 Python ≥3.9（https://www.python.org/downloads/）" }

  $verMajor = & $python -c "import sys; print(sys.version_info.major)"
  $verMinor = & $python -c "import sys; print(sys.version_info.minor)"
  if ($verMajor -lt 3 -or ($verMajor -eq 3 -and $verMinor -lt 9)) {
    err "Python 版本过低: $(& $python --version)（需要 ≥3.9）"
  }
  ok "Python $(& $python --version 2>&1 | ForEach-Object { $_.Trim() })"

  # Git 检测
  try { git --version | Out-Null; ok "Git $(git --version)" } catch { err "未检测到 Git" }

  # 虚拟环境
  $venvPath = "$projectRoot\.venv"
  if (-not (Test-Path $venvPath)) {
    Write-Host "─── 📦 创建虚拟环境 ───" -ForegroundColor Blue
    & $python -m venv $venvPath
    ok "虚拟环境创建完成"
  } else {
    ok "虚拟环境已存在"
  }

  $pip = "$venvPath\Scripts\pip.exe"
  $pythonVenv = "$venvPath\Scripts\python.exe"

  Write-Host "─── 📥 安装依赖 ───" -ForegroundColor Blue

  # 升级 pip
  & $pip install --upgrade pip -q

  # 安装 Seed 框架
  $seedDir = "$projectRoot\.seed-build"
  function Install-SeedPkg($pkg) {
    try { & $pythonVenv -c "import $pkg" 2>$null; ok "  $pkg 已安装，跳过"; return } catch {}
    info "  安装 $pkg ..."
    New-Item -ItemType Directory -Force -Path "$seedDir" | Out-Null
    $srcDir = "$seedDir\$pkg"
    $tgzPath = "$seedDir\$pkg.tar.gz"
    Remove-Item -Recurse -Force $srcDir -ErrorAction SilentlyContinue | Out-Null
    Remove-Item -Force $tgzPath -ErrorAction SilentlyContinue | Out-Null

    # 方案 A: git clone（带 45 秒超时）
    $attempts = 0
    while ($attempts -lt 2) {
      $attempts++
      info "  git clone $pkg（尝试 $attempts/2）..."
      try {
        $job = Start-Job -ScriptBlock { param($u,$d) git clone --depth 1 $u $d 2>$null } -ArgumentList "https://github.com/tagword/${pkg}.git", $srcDir
        $job | Wait-Job -Timeout 45 -ErrorAction SilentlyContinue | Out-Null
        if ($job.State -eq "Running") { $job.Stop(); Remove-Job $job -Force; throw "超时" }
        Receive-Job $job -ErrorAction SilentlyContinue | Out-Null
        Remove-Job $job -Force
        if ((Test-Path "$srcDir\pyproject.toml") -or (Test-Path "$srcDir\setup.py")) {
          & $pip install $srcDir --no-input -q
          ok "  $pkg 安装完成"
          return
        }
        warn "  $pkg 克隆不完整，重试..."
        Remove-Item -Recurse -Force $srcDir -ErrorAction SilentlyContinue | Out-Null
      } catch {
        warn "  git clone $pkg 失败，重试..."
        Remove-Item -Recurse -Force $srcDir -ErrorAction SilentlyContinue | Out-Null
      }
      if ($attempts -lt 2) { Start-Sleep -Seconds 2 }
    }

    # 方案 B: tarball（Invoke-WebRequest 带超时）
    $attempts = 0
    while ($attempts -lt 2) {
      $attempts++
      info "  tarball $pkg（尝试 $attempts/2）..."
      try {
        $url = "https://github.com/tagword/${pkg}/tarball/HEAD"
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $url -OutFile $tgzPath -TimeoutSec 60 -ErrorAction Stop
        if ((Get-Item $tgzPath).Length -gt 100) {
          New-Item -ItemType Directory -Force -Path $srcDir | Out-Null
          tar xzf $tgzPath -C $srcDir --strip-components=1
          & $pip install $srcDir --no-input -q
          ok "  $pkg 安装完成（tarball）"
          return
        }
        warn "  $pkg tarball 无效，重试..."
      } catch {
        warn "  tarball $pkg 下载失败，重试..."
      }
      Remove-Item -Force $tgzPath -ErrorAction SilentlyContinue | Out-Null
      if ($attempts -lt 2) { Start-Sleep -Seconds 2 }
    }
    err "$pkg 安装失败，请检查网络后重试"
  }
  }

  Install-SeedPkg "seed-model-providers"
  Install-SeedPkg "seed"
  Install-SeedPkg "seed-tools"
  Remove-Item -Recurse -Force $seedDir -ErrorAction SilentlyContinue | Out-Null

  # 安装 CodeAgent
  Push-Location $projectRoot
  & $pip install -e . -q
  Pop-Location
  ok "CodeAgent 安装完成"
}

# ── 启动 ──────────────────────────────────────────────────────────
Write-Host ""
Write-Host "─── 🚀 启动 CodeAgent Web UI ───" -ForegroundColor Blue
Write-Host "监听地址: http://$Host`:$Port" -ForegroundColor Cyan
Write-Host "浏览器打开: http://localhost:$Port" -ForegroundColor Green
Write-Host "按 Ctrl+C 停止服务" -ForegroundColor Yellow
Write-Host ""

# 激活虚拟环境
& "$projectRoot\.venv\Scripts\Activate.ps1"

# 启动
codeagent serve --host $Host --port $Port
