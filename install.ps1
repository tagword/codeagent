<#
.SYNOPSIS
  CodeAgent — Windows 一键安装脚本
.DESCRIPTION
  安装 CodeAgent 及其依赖（seed, seed-model-providers, seed-tools）
  用法:
    PowerShell (管理员) 运行:
      Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
      iex (iwr -Uri 'https://raw.githubusercontent.com/tagword/codeagent/main/install.ps1').Content
   或:
      .\install.ps1
#>

$ErrorActionPreference = "Stop"

# ── 颜色输出 ──────────────────────────────────────────────────────────
$Host.UI.RawUI.ForegroundColor = "Gray"
function info  { Write-Host "▶ " -NoNewline -ForegroundColor Cyan; Write-Host "$args" }
function ok    { Write-Host "✓ " -NoNewline -ForegroundColor Green; Write-Host "$args" }
function warn  { Write-Host "⚠ " -NoNewline -ForegroundColor Yellow; Write-Host "$args" }
function err   { Write-Host "✗ " -NoNewline -ForegroundColor Red; Write-Host "$args"; exit 1 }

# ── 检测 Python ────────────────────────────────────────────────────────
info "检测 Python..."
$python = $null
foreach ($cmd in @("python3", "python")) {
  try { $ver = & $cmd --version 2>&1; $python = $cmd; break } catch {}
}
if (-not $python) { err "未检测到 Python，请先安装 Python ≥3.9（https://www.python.org/downloads/）" }

$verStr = & $python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
$verMajor = & $python -c "import sys; print(sys.version_info.major)"
$verMinor = & $python -c "import sys; print(sys.version_info.minor)"
if ($verMajor -lt 3 -or ($verMajor -eq 3 -and $verMinor -lt 9)) {
  err "Python 版本过低: $verStr（需要 ≥3.9）"
}
ok "Python $verStr"

# ── 检测 Git ──────────────────────────────────────────────────────────
info "检测 Git..."
try { git --version | Out-Null; ok "Git $(git --version)" } catch { err "未检测到 Git，请先安装 Git（https://git-scm.com/downloads）" }

# ── 路径 ──────────────────────────────────────────────────────────────
$installDir = if ($env:CODEAGENT_DIR) { $env:CODEAGENT_DIR } else { "$env:USERPROFILE\codeagent" }

if (Test-Path $installDir) {
  warn "目录已存在: $installDir"
  Write-Host "  是否更新已有安装？[Y/n] " -NoNewline -ForegroundColor Yellow
  $reply = Read-Host
  if ($reply -eq "n" -or $reply -eq "N") {
    info "跳过安装。运行: cd $installDir; .\.venv\Scripts\Activate.ps1; codeagent serve"
    exit 0
  }
  info "更新已有仓库..."
  Push-Location $installDir
  git pull --ff-only 2>$null
  if (-not (Test-Path ".venv")) { & $python -m venv .venv }
  Pop-Location
} else {
  info "克隆仓库到 $installDir ..."
  git clone --depth 1 "https://github.com/tagword/codeagent.git" $installDir
}

# ── 虚拟环境 ──────────────────────────────────────────────────────────
$venvPath = "$installDir\.venv"
if (-not (Test-Path $venvPath)) {
  info "创建虚拟环境..."
  & $python -m venv $venvPath
  ok "虚拟环境创建完成"
} else {
  ok "虚拟环境已存在"
}

# ── 进入虚拟环境安装依赖 ──────────────────────────────────────────────
$pip = "$venvPath\Scripts\pip.exe"
$pythonVenv = "$venvPath\Scripts\python.exe"

info "升级 pip..."
& $pip install --upgrade pip -q

# ── 安装 Seed 框架（私有依赖） ──────────────────────────────────────
$seedDir = "$installDir\.seed-build"
New-Item -ItemType Directory -Force -Path $seedDir | Out-Null

function Install-SeedPkg($pkg) {
  $srcDir = "$seedDir\$pkg"
  $tgzPath = "$seedDir\$pkg.tar.gz"

  # 跳过已安装
  try { & $pythonVenv -c "import $pkg" 2>$null; ok "  $pkg 已安装，跳过"; return } catch {}

  info "  安装 $pkg ..."
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
      if ($job.State -eq "Running") {
        $job.Stop(); Remove-Job $job -Force
        throw "超时"
      }
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

  # 方案 B: curl tarball（带超时）
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

Install-SeedPkg("seed-model-providers")
Install-SeedPkg("seed")
Install-SeedPkg("seed-tools")

Remove-Item -Recurse -Force $seedDir -ErrorAction SilentlyContinue | Out-Null
ok "Seed 框架安装完成"

# ── 安装 CodeAgent ──────────────────────────────────────────────────
info "安装 CodeAgent..."
Push-Location $installDir
& $pip install -e . -q
Pop-Location
ok "CodeAgent 安装完成"

# ── 创建启动器 ──────────────────────────────────────────────────────
$launcherPath = "$installDir\codeagent.cmd"
@"
@echo off
chcp 65001 >nul
cd /d "%~dp0"
call "%~dp0.venv\Scripts\activate.bat"
echo.
echo   CodeAgent 启动中...
echo   浏览器打开: http://localhost:8765
echo   按 Ctrl+C 停止服务
echo.
codeagent serve
"@ | Out-File -FilePath $launcherPath -Encoding ascii

# ── 完成 ──────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Green
Write-Host "  CodeAgent 安装成功！" -ForegroundColor Green
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Green
Write-Host ""
Write-Host "  一键启动（双击 codeagent.cmd）:" -ForegroundColor Cyan
Write-Host "    $launcherPath" -ForegroundColor White
Write-Host ""
Write-Host "  或 PowerShell:" -ForegroundColor Cyan
Write-Host "    cd $installDir" -ForegroundColor White
Write-Host "    .\run.ps1" -ForegroundColor White
Write-Host ""
Write-Host "  浏览器打开: http://localhost:8765" -ForegroundColor Green
Write-Host ""
