@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title SHUNCHi by RUHUL - Release Builder 4.4.0
echo ==========================================================
echo SHUNCHi by RUHUL - Windows 11 Release Build 4.4.0
echo ONEDIR + WINDOWED GUI + Gemini 3.5 Transcribe
echo ==========================================================
echo.

where py >nul 2>nul
if errorlevel 1 (
  echo Python Launcher not found.
  echo Install Python 3.13 x64 from https://www.python.org/downloads/windows/
  echo Enable Python Launcher during setup.
  pause
  exit /b 1
)

set "PYVER="
py -3.13 -c "import sys" >nul 2>nul && set "PYVER=3.13"
if not defined PYVER py -3.12 -c "import sys" >nul 2>nul && set "PYVER=3.12"
if not defined PYVER py -3.11 -c "import sys" >nul 2>nul && set "PYVER=3.11"
if not defined PYVER (
  echo Python 3.11, 3.12 or 3.13 was not found.
  pause
  exit /b 1
)

echo Using Python %PYVER%
py -%PYVER% -c "import struct; assert struct.calcsize('P') == 8, 'Use 64-bit Python'"
if errorlevel 1 (
  echo Please install 64-bit Python.
  pause
  exit /b 1
)

if exist .venv rmdir /s /q .venv
py -%PYVER% -m venv .venv
if errorlevel 1 goto fail
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
if errorlevel 1 goto fail
python -m pip install -r requirements.txt
if errorlevel 1 goto fail

echo.
echo Checking the source code and dependencies...
python -m py_compile app.py
if errorlevel 1 goto fail
python -c "import app; print('Dependency check OK:', app.APP_VERSION)"
if errorlevel 1 goto fail

echo.
echo [1/2] Building SHUNCHi as a WINDOWED ONEDIR application...
if exist dist\SHUNCHi rmdir /s /q dist\SHUNCHi
python -m PyInstaller --noconfirm --clean --windowed --onedir --noupx --name SHUNCHi ^
 --icon assets\shunchi.ico --add-data "assets;assets" ^
 --collect-all sounddevice --collect-all keyring --collect-all pynput ^
 --hidden-import pynput.keyboard._win32 --hidden-import pynput.mouse._win32 ^
 --hidden-import keyring.backends.Windows ^
 --exclude-module tkinter --exclude-module matplotlib --exclude-module scipy ^
 --exclude-module PySide6.QtWebEngineCore --exclude-module PySide6.QtWebEngineWidgets ^
 --exclude-module PySide6.Qt3DCore --exclude-module PySide6.QtQuick --exclude-module PySide6.QtQml ^
 app.py
if errorlevel 1 goto fail

if not exist "dist\SHUNCHi\SHUNCHi.exe" (
  echo Expected executable was not created: dist\SHUNCHi\SHUNCHi.exe
  goto fail
)

set "ISCC_EXE="
where ISCC >nul 2>nul && set "ISCC_EXE=ISCC"
if not defined ISCC_EXE if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC_EXE=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC_EXE if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC_EXE=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC_EXE (
  echo Inno Setup Compiler was not found. Install Inno Setup 6.
  pause
  exit /b 1
)

echo.
echo [2/2] Building standard Windows installer...
"%ISCC_EXE%" SHUNCHi.iss
if errorlevel 1 goto fail

echo.
echo ==========================================================
echo BUILD SUCCESS
echo Installer: installer_output\SHUNCHi_by_RUHUL_Setup_4.4.0.exe
echo App files: dist\SHUNCHi\
echo ==========================================================
pause
exit /b 0

:fail
echo.
echo BUILD FAILED. Send a screenshot of the complete error.
pause
exit /b 1
