@echo off
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars32.bat" >nul || exit /b 1
cd /d "%~dp0"
cl /nologo /O2 /MT /W3 /D_CRT_SECURE_NO_WARNINGS launch_play.cpp /Fe:launch_play.exe || exit /b 1
del *.obj 2>nul
