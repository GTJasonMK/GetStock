@echo off
setlocal EnableExtensions

rem Ensure UTF-8 output (best-effort)
rem NOTE: Keep CRLF line endings (see .gitattributes) for best cmd.exe compatibility.
chcp 65001 >nul

cd /d "%~dp0\.."

echo ==================================================
echo Frontend deps repair (Windows)
echo ==================================================

echo [1/5] Checking Node.js...
node -v >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Node.js not found. Please install Node 18+ and ensure node/npm are in PATH.
  exit /b 1
)

echo [2/5] Cleaning old dependencies...
if exist node_modules rmdir /s /q node_modules
if exist .next rmdir /s /q .next

echo [3/5] Installing dependencies (prefer offline)...
npm ci --prefer-offline --no-audit --no-fund
if errorlevel 1 (
  echo [INFO] Offline install failed, retrying online...
  npm ci --no-audit --no-fund
  if errorlevel 1 (
    echo [ERROR] Install failed. Please check network / npm registry settings.
    exit /b 1
  )
)

echo [4/5] Validating platform SWC binary...
node scripts/check-next-swc.js
if errorlevel 1 (
  echo [ERROR] SWC validation failed. Next.js build may still fail.
  exit /b 1
)

echo [5/5] Verifying build...
npm run build
if errorlevel 1 (
  echo [ERROR] Build still failed. Please keep logs for further investigation.
  exit /b 1
)

echo.
echo [DONE] Frontend deps repair succeeded.
exit /b 0
