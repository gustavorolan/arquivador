@echo off
cd /d "%~dp0"
python -m PyInstaller --noconfirm --onefile --name Arquivador --icon arquivador.ico --add-data "index.html;." arquivador.py
if errorlevel 1 exit /b 1
copy /y dist\Arquivador.exe Arquivador.exe
rmdir /s /q build
rmdir /s /q dist
del /q Arquivador.spec
echo Gerado: %~dp0Arquivador.exe
