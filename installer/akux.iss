; AKVERI - Windows-asennusohjelma (Inno Setup 6)
; Rakennetaan GitHubissa: iscc /DVersio=x.y.z installer\akux.iss

#ifndef Versio
  #define Versio "0.0.0"
#endif

[Setup]
AppId={{15805C5D-4DBF-40BB-974F-7DA957C44CD5}
AppName=AKVERI
AppVersion={#Versio}
AppVerName=AKVERI {#Versio}
AppPublisher=AKVERI
AppComments=Ajoakun kunnon ja kapasiteetin mittaus
DefaultDirName={localappdata}\Programs\Akux
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=AKVERI-asennus-{#Versio}
SetupIconFile=..\akux.ico
UninstallDisplayIcon={app}\Akux.exe
UninstallDisplayName=AKVERI
VersionInfoVersion={#Versio}
VersionInfoProductName=AKVERI
VersionInfoDescription=AKVERI - asennus
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
ShowLanguageDialog=no

[Languages]
Name: "fi"; MessagesFile: "compiler:Languages\Finnish.isl"

[Tasks]
Name: "desktopicon"; Description: "Luo pikakuvake työpöydälle"; GroupDescription: "Pikakuvakkeet:"

[InstallDelete]
; Vanhan version ohjelmatiedostot poistetaan ennen asennusta. Mittaukset ja asetukset ovat eri kansiossa.
Type: filesandordirs; Name: "{app}\_internal"
; Aiempien nimien pikakuvakkeet korvautuvat AKVERI-pikakuvakkeilla
Type: files; Name: "{autoprograms}\AKUX.lnk"
Type: files; Name: "{autodesktop}\AKUX.lnk"
Type: files; Name: "{autoprograms}\Akux.lnk"
Type: files; Name: "{autodesktop}\Akux.lnk"

[Files]
Source: "..\dist\Akux\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\AKVERI"; Filename: "{app}\Akux.exe"; Comment: "Ajoakun kunnon ja kapasiteetin mittaus"
Name: "{autodesktop}\AKVERI"; Filename: "{app}\Akux.exe"; Tasks: desktopicon; Comment: "Ajoakun kunnon ja kapasiteetin mittaus"

[Run]
Filename: "{app}\Akux.exe"; Description: "Käynnistä AKVERI"; Flags: nowait postinstall skipifsilent

[Code]
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Code: Integer;
begin
  Result := '';
  { Suljetaan käynnissä oleva AKVERI hallitusti. Jos mittaus on kesken, asennusta ei tehdä. }
  Exec('powershell.exe',
    '-NoProfile -ExecutionPolicy Bypass -Command "try { Invoke-WebRequest -UseBasicParsing -Method Post -Uri http://127.0.0.1:8765/api/sulje -Body ''{}'' -ContentType application/json -TimeoutSec 3 | Out-Null; exit 0 } catch { if ($_.Exception.Response -and [int]$_.Exception.Response.StatusCode -eq 409) { exit 2 } else { exit 0 } }"',
    '', SW_HIDE, ewWaitUntilTerminated, Code);
  if Code = 2 then
    Result := 'AKVERIissa on mittaus käynnissä. Odota, että mittaus valmistuu, ja käynnistä asennus sitten uudelleen.'
  else
  begin
    { Sovellusikkuna sulkeutuu ohjelman perässä. Varmistetaan, ettei mikään AKVERIin osa jää käyntiin. }
    Sleep(5000);
    Exec('taskkill.exe', '/IM Akux.exe /F', '', SW_HIDE, ewWaitUntilTerminated, Code);
    Sleep(500);
  end;
end;
