@echo off
rem ======================================================================
rem  AKVERI - asennus Windowsiin
rem  Tekee tasta kansiosta AKVERI.exe-sovelluksen tietokoneellesi,
rem  lisaa pikakuvakkeet tyopoydalle ja Kaynnista-valikkoon ja avaa ohjelman.
rem  Ajetaan kerran, ja uudelleen vain kun asennat uuden version.
rem ======================================================================
chcp 65001 >nul
title AKVERI - asennus
setlocal
cd /d "%~dp0"

set "APPDIR=%~dp0"
set "BUILD=%LOCALAPPDATA%\AKVERI\rakennus"
set "PYROOT=%BUILD%\python"
set "PY=%PYROOT%\tools\python.exe"
set "PYW=%PYROOT%\tools\pythonw.exe"
set "PYVER=3.12.10"
set "TARGET=%LOCALAPPDATA%\Programs\AKVERI"

echo.
echo  AKVERI - asennus
echo  -----------------------
echo  Asennus kestaa ensimmaisella kerralla noin 5-10 minuuttia ja vaatii verkkoyhteyden.
echo.

rem Poistetaan internetista ladattujen tiedostojen esto, jotta Windows ei kysy erikseen
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-ChildItem -LiteralPath '%APPDIR%' -Recurse -File | Unblock-File" >nul 2>nul

rem Suljetaan mahdollisesti kaynnissa oleva vanha versio
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Invoke-WebRequest -UseBasicParsing -Method Post -Uri 'http://127.0.0.1:8765/api/sulje' -Body '{\"vahvistettu\": false}' -ContentType 'application/json' -TimeoutSec 2 | Out-Null } catch {}" >nul 2>nul

rem Odotetaan, etta vanha versio ehtii sulkeutua
timeout /t 3 /nobreak >nul

if not exist "%PY%" call :lataa_python
if not exist "%PY%" goto :virhe

echo [2/4] Asennetaan kirjastot...
"%PY%" -m pip install --disable-pip-version-check --no-warn-script-location -q --upgrade -r "%APPDIR%requirements.txt" pyinstaller
if errorlevel 1 goto :virhe

echo [3/4] Rakennetaan AKVERI.exe...
if exist "%BUILD%\dist" rmdir /s /q "%BUILD%\dist"
"%PY%" -m PyInstaller --noconfirm --clean --log-level WARN --windowed --name AKVERI ^
  --icon "%APPDIR%akux.ico" ^
  --add-data "%APPDIR%akux\web;akux\web" ^
  --add-data "%APPDIR%akux\data;akux\data" ^
  --hidden-import serial.tools.list_ports ^
  --collect-submodules akux ^
  --collect-all webview ^
  --hidden-import clr ^
  --hidden-import clr_loader ^
  --collect-submodules reportlab.graphics ^
  --paths "%APPDIR%." ^
  --exclude-module tkinter ^
  --distpath "%BUILD%\dist" --workpath "%BUILD%\work" --specpath "%BUILD%" ^
  "%APPDIR%Akux.pyw"
if not exist "%BUILD%\dist\AKVERI\AKVERI.exe" goto :varatapa

echo [4/4] Asennetaan ohjelma...
robocopy "%BUILD%\dist\AKVERI" "%TARGET%" /MIR /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 goto :virhe
set "LAUNCH=%TARGET%\AKVERI.exe"
set "LARGS="
set "ICON=%TARGET%\AKVERI.exe"
goto :pikakuvakkeet

:varatapa
rem Jos exe-tiedoston rakentaminen ei onnistu, ohjelma asennetaan ajettavaksi
rem omalla Pythonillaan. Kaytto on taysin sama: oma ikkuna, ei mustaa ikkunaa.
echo Exe-tiedoston rakentaminen ei onnistunut. Asennetaan ohjelma toisella tavalla.
robocopy "%PYROOT%" "%TARGET%\python" /MIR /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 goto :virhe
robocopy "%APPDIR%akux" "%TARGET%\akux" /MIR /NFL /NDL /NJH /NJS /NP /XD __pycache__ >nul
if errorlevel 8 goto :virhe
copy /y "%APPDIR%akux.ico" "%TARGET%\akux.ico" >nul
set "LAUNCH=%TARGET%\python\tools\pythonw.exe"
set "LARGS=-m akux.launcher"
set "ICON=%TARGET%\akux.ico"

:pikakuvakkeet
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$w=New-Object -ComObject WScript.Shell;" ^
  "foreach($d in @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))){" ^
  "  $s=$w.CreateShortcut((Join-Path $d 'AKVERI.lnk'));" ^
  "  $s.TargetPath='%LAUNCH%'; $s.Arguments='%LARGS%'; $s.WorkingDirectory='%TARGET%';" ^
  "  $s.IconLocation='%ICON%'; $s.Description='Ajoakun kunnon ja kapasiteetin mittaus'; $s.Save() }"

echo.
echo  Valmis. AKVERI on asennettu kansioon:
echo  %TARGET%
echo  Kaynnista ohjelma jatkossa tyopoydan pikakuvakkeesta AKVERI.
echo  Mittaukset ja asetukset sailyvat, kun asennat uuden version.
echo.
start "" /D "%TARGET%" "%LAUNCH%" %LARGS%
timeout /t 8 >nul
exit /b 0

:lataa_python
echo [1/4] Ladataan Python %PYVER% ohjelman rakentamista varten...
if exist "%PYROOT%" rmdir /s /q "%PYROOT%"
mkdir "%PYROOT%" 2>nul
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop'; $ProgressPreference='SilentlyContinue';" ^
  "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12;" ^
  "$z=Join-Path $env:TEMP 'akux-python.zip';" ^
  "Invoke-WebRequest -UseBasicParsing 'https://www.nuget.org/api/v2/package/python/%PYVER%' -OutFile $z;" ^
  "Expand-Archive -Force $z '%PYROOT%'; Remove-Item $z"
if errorlevel 1 (
  echo Pythonin lataus epaonnistui. Tarkista verkkoyhteys.
  exit /b 1
)
"%PY%" -m ensurepip --upgrade >nul 2>nul
exit /b 0

:virhe
echo.
echo  Asennus ei onnistunut. Tarkista verkkoyhteys ja aja Asenna.bat uudelleen.
echo  Jos ongelma toistuu, poista kansio %BUILD% ja yrita uudelleen.
echo.
pause
exit /b 1
