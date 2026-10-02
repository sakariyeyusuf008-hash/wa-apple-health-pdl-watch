@echo off
REM One-click check. Double-click it.
setlocal
set "PY="
if exist "%LocalAppData%\Programs\Python\Python312\python.exe" set "PY=%LocalAppData%\Programs\Python\Python312\python.exe"
if not defined PY (
  for %%P in (312 313 311 310) do (
    if not defined PY if exist "%LocalAppData%\Programs\Python\Python%%P\python.exe" set "PY=%LocalAppData%\Programs\Python\Python%%P\python.exe"
  )
)
if not defined PY (
  where py >nul 2>&1 && set "PY=py"
)
if not defined PY (
  echo Python not found. Install Python 3.9+ or edit this file to point at it.
  pause
  exit /b 1
)

"%PY%" "%~dp0pdl_watch.py" --popup %*
set "RC=%errorlevel%"
echo.
if "%RC%"=="1" (
  echo ^>^> A change was found. Read ALERT.txt in this folder.
) else if "%RC%"=="0" (
  echo ^>^> No change since the last run.
) else (
  echo ^>^> Could not check. See watch.log.
)
pause
exit /b %RC%
