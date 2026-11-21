@echo off
setlocal
where /q cl.exe
if errorlevel 1 (
    echo Open an x86 Native Tools Command Prompt for Visual Studio first.
    exit /b 1
)
pushd "%~dp0" || exit /b 1
cl /nologo /W4 /WX /O2 /MT /EHsc /LD windowed_d3d9.cpp user32.lib /link /MACHINE:X86 /DEF:d3d9.def /OUT:d3d9.dll
set "result=%ERRORLEVEL%"
popd
exit /b %result%
