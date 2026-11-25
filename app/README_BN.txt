SHUNCHi by RUHUL — Version 4.7.0
=================================

Free AI voice typing for Windows. Press a shortcut, speak Bangla or English, pause, and the finished,
punctuated text is typed wherever your cursor is (browser, WhatsApp, Word, Notepad...).

SHORTCUTS
- Win + Left Ctrl   -> Bangla (English words may be mixed in)
- Win + Left Shift  -> English
- Press the same shortcut again to finish early. Otherwise recording stops by itself after a pause.

HOW IT WORKS
1. The microphone is recorded locally as 16 kHz mono audio.
2. When you stop (or pause), silence is trimmed and the audio is sent ONCE to Gemini 3.5 Transcribe
   (Smart mode: punctuation, filler-word removal, lists). Backup models are tried automatically.
3. The text is pasted at your cursor with Ctrl + V (SendInput) and saved to the local history.

WEBSITE, UPDATES AND MORE APPS (new in 4.5.0)
- Official website: https://shunchiai.com
- SHUNCHi reads https://shunchiai.com/update.json (a small file you upload, see website\README_UPDATE.txt).
  When its latest_version is higher than the installed version, every installed copy shows an update
  banner on the Dashboard and asks whether to download. The "More Apps" menu lists the apps in the same file.
- Until the website exists, the check fails silently and nothing is shown.

REQUIREMENTS FOR USERS
- Windows 10 or 11 (64-bit), a microphone, internet connection.
- A free Gemini API key from https://aistudio.google.com/apikey (Settings > Save & test).
  The key is stored in Windows Credential Manager.

BUILD (developer)
1. Install Python 3.13 x64 (3.12 / 3.11 also work) and Inno Setup 6.
2. Double-click Build_Installer.bat. It checks the code, builds the app with PyInstaller
   (this also writes SHUNCHi.spec automatically) and compiles SHUNCHi.iss with Inno Setup.
3. Installer: release\SHUNCHi_Setup_<version>.exe + release\SHUNCHi_Setup.exe  (per-user, no administrator needed).
   Run RUN_DIAGNOSTICS.bat if something fails.

FILES
- app.py                 application
- SHUNCHi.iss            installer script
- Build_Installer.bat    one-click build
- RUN_DIAGNOSTICS.bat    environment check
- website\               update.json sample + instructions for shunchiai.com
- assets\                logo, icons, installer artwork, developer photo, popup design reference
- requirements.txt       Python packages

PRIVACY
- Audio is sent to Google only for transcription, using the user's own API key. With Google's free
  tier, content may be used by Google to improve its products; paid-tier content is not.
- History is stored only on the user's computer: %APPDATA%\SHUNCHi\history.db
- Log file: %APPDATA%\SHUNCHi\shunchi.log (API keys are redacted).

TEST CHECKLIST (about 10 minutes on a real Windows PC)
1. Install, open SHUNCHi, paste your key, choose Save & test: the green "Connected" banner appears.
2. Dashboard > "Try it here": click the box, press Win + Left Ctrl, speak Bangla, then stay silent.
   The popup stops by itself, shows "Writing", and the text appears in the box.
3. Repeat in Notepad, a browser text field and WhatsApp Desktop.
4. Press Win + Left Shift and speak English; then speak Bangla with some English words.
5. Settings: switch "Start with Windows" on, restart Windows, SHUNCHi should be in the tray.
6. Unplug the internet and dictate: the popup shows a clear notice and nothing crashes.
7. If an app runs "as administrator", Windows may block auto-typing; SHUNCHi then copies the text
   so you can press Ctrl + V.

SUPPORT
Facebook: https://www.facebook.com/voice.shunchi
Instagram: https://www.instagram.com/voice.shunchi/
Email: voice.shunchi@gmail.com
Developer: Ruhul Amin · https://www.facebook.com/iamruhulaamin
