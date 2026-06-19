@echo off
echo Building TeeInBlue Mockup Importer Pro...
pyinstaller --onefile --windowed --name "TeeBlueMockupImporterPro" main.py
echo Build complete. Check the 'dist' folder.
pause
