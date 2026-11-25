@echo off
setlocal
cd /d "%~dp0"
echo SHUNCHi 4.7.0 Diagnostics
echo ==========================
echo Python launcher:
where py
echo.
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -c "import sys, PySide6, numpy, sounddevice, keyring, pyperclip, pynput; print('Python:',sys.version); print('Required modules: OK'); import sounddevice as sd; print('Input devices:'); [print(i, d['name'], 'channels=',d['max_input_channels'],'rate=',d['default_samplerate']) for i,d in enumerate(sd.query_devices()) if d['max_input_channels'] > 0]"
) else (
  echo Build virtual environment not found. Run Build_Installer.bat first.
)
echo.
echo Expected GUI executable: dist\SHUNCHi\SHUNCHi.exe
echo This executable should be WINDOWED (no terminal).
echo SHUNCHi log: %APPDATA%\SHUNCHi\shunchi.log
echo History DB: %APPDATA%\SHUNCHi\history.db
pause
