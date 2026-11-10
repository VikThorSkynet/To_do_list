@echo off
cd /d "%~dp0"
pip install -r requirements.txt
pyinstaller --noconfirm ListaDeTarefas.spec
echo.
echo Build concluido. Executavel em: dist\ListaDeTarefas\ListaDeTarefas.exe
pause
