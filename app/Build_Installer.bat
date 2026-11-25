@echo off
rem Re-launch inside a window that stays open, so nothing disappears if an error happens.
if not "%~1"=="stay" (
  cmd /k ""%~f0" stay"
  exit /b
)
setlocal EnableExtensions
cd /d "%~dp0"
title SHUNCHi - Production Release Builder
echo ==========================================================
echo SHUNCHi - Windows Production Release Build
echo ONEDIR + WINDOWED GUI + full installer + web installer
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
for /f %%v in ('python make_version.py') do set "APPVER=%%v"
if not defined APPVER goto fail
echo Version: %APPVER%  (set in app.py, the only place to change)
echo.
echo [1/3] Building SHUNCHi as a WINDOWED ONEDIR application...
if exist dist\SHUNCHi rmdir /s /q dist\SHUNCHi
python -m PyInstaller --noconfirm --clean --windowed --onedir --noupx --name SHUNCHi ^
 --icon assets\shunchi.ico --version-file version_info.txt --add-data "assets;assets" ^
 --collect-all sounddevice --collect-all keyring --collect-all pynput ^
 --hidden-import pynput.keyboard._win32 --hidden-import pynput.mouse._win32 ^
 --hidden-import keyring.backends.Windows ^
 --exclude-module tkinter --exclude-module matplotlib --exclude-module scipy ^
 --exclude-module PySide6.QtWebEngineCore --exclude-module PySide6.QtWebEngineWidgets ^
 --exclude-module PySide6.Qt3DCore --exclude-module PySide6.QtQuick --exclude-module PySide6.QtQml ^
 app.py
if errorlevel 1 goto fail

echo.
echo PyInstaller finished OK. Looking for Inno Setup...
if not exist "dist\SHUNCHi\SHUNCHi.exe" (
  echo Expected executable was not created: dist\SHUNCHi\SHUNCHi.exe
  goto fail
)

set "ISCC_EXE="
where ISCC >nul 2>nul && set "ISCC_EXE=ISCC"
if not defined ISCC_EXE if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC_EXE=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC_EXE if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC_EXE=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC_EXE if exist "%LocalAppData%\Programs\Inno Setup 6\ISCC.exe" set "ISCC_EXE=%LocalAppData%\Programs\Inno Setup 6\ISCC.exe"
if not defined ISCC_EXE for %%K in ("HKCU" "HKLM") do for /f "tokens=2,*" %%A in ('reg query "%%~K\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1" /v InstallLocation 2^>nul ^| find "InstallLocation"') do if exist "%%B\ISCC.exe" set "ISCC_EXE=%%B\ISCC.exe"
if not defined ISCC_EXE (
  echo Inno Setup Compiler was not found. Install Inno Setup 6.4 or newer from jrsoftware.org.
  echo The app itself was built OK in dist\SHUNCHi. Install Inno Setup and run this file again.
  pause
  exit /b 1
)

echo.
echo [2/3] Building the FULL installer...
if exist installer_output rmdir /s /q installer_output
"%ISCC_EXE%" /DMyAppVersion=%APPVER% SHUNCHi.iss
if errorlevel 1 goto fail

echo.
echo [3/3] Building the small WEB installer (downloads the latest version)...
"%ISCC_EXE%" SHUNCHi_Web.iss
if errorlevel 1 (
  echo.
  echo WARNING: the small web installer could not be built. The FULL installer is fine, so the build continues.
  echo The web installer does not change between versions, so the one already on your website keeps working.
)

if exist release rmdir /s /q release
mkdir release
copy /y "installer_output\SHUNCHi_Setup_%APPVER%.exe" release\ >nul
if exist "installer_output\SHUNCHi_Setup.exe" copy /y "installer_output\SHUNCHi_Setup.exe" release\ >nul
certutil -hashfile "release\SHUNCHi_Setup_%APPVER%.exe" SHA256 > release\SHA256.txt

echo.
echo ==========================================================
echo BUILD SUCCESS  -  version %APPVER%
echo Upload BOTH files from the "release" folder to the GitHub Release:
echo   SHUNCHi_Setup_%APPVER%.exe   (full installer)
echo   SHUNCHi_Setup.exe            (small web installer, same name every release)
echo Release tag to use: v%APPVER%
echo ==========================================================
pause
exit /b 0

:fail
echo.
echo BUILD FAILED. Send a screenshot of the complete error.
pause
exit /b 1
