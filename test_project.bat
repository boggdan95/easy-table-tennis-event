@echo off
REM ========================================================================
REM Easy Table Tennis Event Manager - Test Script (Windows)
REM ========================================================================
REM This script tests the complete V1 functionality

echo.
echo ============================================================
echo   Easy Table Tennis Event Manager - V1 Test Suite
echo ============================================================
echo.

REM Change to project directory
cd /d "%~dp0"

echo [1/7] Cleaning previous test data...
if exist .ettem rmdir /s /q .ettem
if exist out rmdir /s /q out
mkdir out
echo    ✓ Cleaned

echo.
echo [2/7] Importing players (Spanish - default)...
ettem import-players --csv data/samples/players.csv --category U13
if errorlevel 1 (
    echo    ✗ ERROR: Import failed
    pause
    exit /b 1
)
echo    ✓ Players imported

echo.
echo [3/7] Building groups...
ettem build-groups --config config/sample_config.yaml --category U13 --out out/
if errorlevel 1 (
    echo    ✗ ERROR: Build groups failed
    pause
    exit /b 1
)
echo    ✓ Groups created

echo.
echo [4/7] Computing standings (initial - before matches)...
ettem compute-standings --category U13
if errorlevel 1 (
    echo    ✗ ERROR: Compute standings failed
    pause
    exit /b 1
)
echo    ✓ Standings computed

echo.
echo [5/7] Building bracket...
ettem build-bracket --category U13 --config config/sample_config.yaml
if errorlevel 1 (
    echo    ✗ ERROR: Build bracket failed
    pause
    exit /b 1
)
echo    ✓ Bracket created

echo.
echo [6/7] Exporting data to CSV...
ettem export --what groups --format csv --out out/
ettem export --what standings --format csv --out out/
ettem export --what bracket --format csv --out out/
if errorlevel 1 (
    echo    ✗ ERROR: Export failed
    pause
    exit /b 1
)
echo    ✓ Data exported to out/ directory

echo.
echo [7/7] Testing i18n (English)...
ettem --lang en --help > nul 2>&1
if errorlevel 1 (
    echo    ✗ ERROR: i18n test failed
    pause
    exit /b 1
)
echo    ✓ i18n working

echo.
echo ============================================================
echo   ✓ All CLI tests passed!
echo ============================================================
echo.
echo Generated files:
dir /b out\*.csv 2>nul
echo.
echo Database created at: .ettem\ettem.sqlite
echo.
echo ============================================================
echo   Starting Web Panel...
echo ============================================================
echo.
echo The web panel will open at: http://127.0.0.1:8000
echo.
echo In the web panel you can:
echo   1. View groups and players
echo   2. Enter match results
echo   3. View standings
echo   4. View knockout bracket
echo.
echo Press Ctrl+C to stop the server when done
echo.
pause
echo.
echo Starting server...
ettem open-panel
