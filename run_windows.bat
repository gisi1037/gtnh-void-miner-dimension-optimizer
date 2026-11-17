@echo off
setlocal
cd /d "%~dp0"
set "ORE_PROMPT="
if "%~1"=="" set "ORE_PROMPT=--choose-tier"
where py >nul 2>nul
if errorlevel 1 goto try_python
py -3 ore_dimension_optimizer.py %ORE_PROMPT% --report-prefix my_result %*
set "ORE_EXIT_CODE=%errorlevel%"
goto done
:try_python
where python >nul 2>nul
if errorlevel 1 goto missing_python
python ore_dimension_optimizer.py %ORE_PROMPT% --report-prefix my_result %*
set "ORE_EXIT_CODE=%errorlevel%"
goto done
:missing_python
echo Python 3.10 or newer is required. Install Python, then run this file again.
set "ORE_EXIT_CODE=1"
:done
echo.
pause
exit /b %ORE_EXIT_CODE%
