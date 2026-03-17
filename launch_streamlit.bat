@echo off
setlocal

set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"

if exist "%PROJECT_DIR%\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%PROJECT_DIR%\.venv\Scripts\python.exe"
) else (
    where python >nul 2>nul
    if %errorlevel%==0 (
        set "PYTHON_EXE=python"
    ) else (
        echo Python was not found. Install Python or create a .venv for this project.
        pause
        exit /b 1
    )
)

start "" http://localhost:8501
call "%PYTHON_EXE%" -m streamlit run app\app.py
