; AKVERI - Windows-asennusohjelma (Inno Setup 6)
; Rakennetaan GitHubissa: iscc /DVersio=x.y.z installer\akveri.iss

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
DefaultDirName={localappdata}\Programs\AKVERI
UsePreviousAppDir=no
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=AKVERI-asennus-{#Versio}
SetupIconFile=..\akveri.ico
UninstallDisplayIcon={app}\AKVERI.exe
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

[Files]
Source: "..\dist\AKVERI\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\AKVERI"; Filename: "{app}\AKVERI.exe"; Comment: "Ajoakun kunnon ja kapasiteetin mittaus"
Name: "{autodesktop}\AKVERI"; Filename: "{app}\AKVERI.exe"; Tasks: desktopicon; Comment: "Ajoakun kunnon ja kapasiteetin mittaus"

[Run]
; Päivittää Windowsin kuvakevälimuistin, jotta pikakuvakkeissa näkyy heti uusi kuvake
Filename: "{sys}\ie4uinit.exe"; Parameters: "-show"; Flags: runhidden skipifdoesntexist
Filename: "{app}\AKVERI.exe"; Description: "Käynnistä AKVERI"; Flags: nowait postinstall skipifsilent

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
    Result := 'AKVERIssa on mittaus käynnissä. Odota, että mittaus valmistuu, ja käynnistä asennus sitten uudelleen.'
  else
  begin
    { Sovellusikkuna sulkeutuu ohjelman perässä. Varmistetaan, ettei mikään AKVERIn osa jää käyntiin. }
    Sleep(5000);
    Exec('taskkill.exe', '/IM AKVERI.exe /F', '', SW_HIDE, ewWaitUntilTerminated, Code);
    Sleep(500);
  end;
end;
