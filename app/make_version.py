"""Reads APP_VERSION from app.py (the ONE place the version is set) and writes version_info.txt for PyInstaller."""
import re, pathlib
src = pathlib.Path(__file__).with_name("app.py").read_text(encoding="utf-8")
ver = re.search(r'^APP_VERSION\s*=\s*"(\d+(?:\.\d+){1,3})"', src, re.M).group(1)
parts = (ver.split(".") + ["0", "0", "0"])[:4]
tup = ", ".join(parts)
pathlib.Path(__file__).with_name("version_info.txt").write_text(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers=({tup}), prodvers=({tup}), mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'Ruhul Amin'),
      StringStruct('FileDescription', 'SHUNCHi AI Voice Typing'),
      StringStruct('FileVersion', '{'.'.join(parts)}'),
      StringStruct('InternalName', 'SHUNCHi'),
      StringStruct('LegalCopyright', '(c) Ruhul Amin. shunchiai.com'),
      StringStruct('OriginalFilename', 'SHUNCHi.exe'),
      StringStruct('ProductName', 'SHUNCHi'),
      StringStruct('ProductVersion', '{'.'.join(parts)}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
""", encoding="utf-8")
print(ver)
