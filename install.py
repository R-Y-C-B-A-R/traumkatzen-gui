"""
Erstellt Desktop- und Startmenü-Verknüpfung für Traumkatzen.
Ausführen mit: python install.py
"""
import sys
import subprocess
from pathlib import Path

APP_DIR = Path(__file__).parent.resolve()
APP_PY  = APP_DIR / "app.py"
ICON    = APP_DIR / "cat.ico"


def install_windows():
    pythonw = Path(sys.executable).parent / "pythonw.exe"
    if not pythonw.exists():
        pythonw = Path(sys.executable)  # fallback: python.exe

    icon_line = f'$lnk.IconLocation = "{ICON}"' if ICON.exists() else ""

    ps = f"""
$ws = New-Object -ComObject WScript.Shell

$desktop = "$env:USERPROFILE\\Desktop\\Traumkatzen.lnk"
$startmenu = "$env:APPDATA\\Microsoft\\Windows\\Start Menu\\Programs\\Traumkatzen.lnk"

foreach ($path in @($desktop, $startmenu)) {{
    $lnk = $ws.CreateShortcut($path)
    $lnk.TargetPath = "{pythonw}"
    $lnk.Arguments = "{APP_PY}"
    $lnk.WorkingDirectory = "{APP_DIR}"
    $lnk.Description = "Traumkatzen Datenbank"
    {icon_line}
    $lnk.Save()
    Write-Host "Erstellt: $path"
}}
"""
    subprocess.run(["powershell", "-Command", ps], check=True)
    print("\nFertig! App ist jetzt im Startmenü und auf dem Desktop.")


def install_linux():
    desktop_dir = Path.home() / ".local/share/applications"
    desktop_dir.mkdir(parents=True, exist_ok=True)
    python = sys.executable

    entry = f"""[Desktop Entry]
Name=Traumkatzen
Comment=Traumkatzen Datenbank
Exec={python} {APP_PY}
Path={APP_DIR}
Icon={ICON}
Terminal=false
Type=Application
Categories=Utility;
"""
    target = desktop_dir / "traumkatzen.desktop"
    target.write_text(entry, encoding="utf-8")
    target.chmod(0o755)
    print(f"Erstellt: {target}")
    print("\nFertig! App erscheint im Anwendungsmenü.")


if __name__ == "__main__":
    if sys.platform == "win32":
        install_windows()
    elif sys.platform.startswith("linux"):
        install_linux()
    else:
        print(f"Nicht unterstützte Plattform: {sys.platform}")
        sys.exit(1)
