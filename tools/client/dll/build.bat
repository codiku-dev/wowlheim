@echo off
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars32.bat" >nul || exit /b 1
cd /d "%~dp0"
cl /nologo /O2 /MT /LD /W3 /D_CRT_SECURE_NO_WARNINGS wowlheim_client.cpp /Fe:wowlheim_client.dll || exit /b 1
cl /nologo /O2 /MT /W3 /D_CRT_SECURE_NO_WARNINGS launch.cpp /Fe:launch.exe || exit /b 1
del *.obj *.exp *.lib 2>nul
