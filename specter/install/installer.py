import os
import sys
import json
import urllib.request
import zipfile
import shutil
import subprocess
import platform
from pathlib import Path

API_URL = "https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions-with-downloads.json"

def get_platform_key():
    system = platform.system().lower()
    machine = platform.machine().lower()
    
    if system == "windows":
        return "win64" if "64" in machine or "amd64" in machine else "win32"
    elif system == "darwin":
        return "mac-arm64" if "arm" in machine or "aarch64" in machine else "mac-x64"
    elif system == "linux":
        return "linux64"
    else:
        raise RuntimeError(f"Unsupported operating system: {system}")

def get_binary_name():
    return "chrome-headless-shell.exe" if platform.system().lower() == "windows" else "chrome-headless-shell"

def get_default_install_dir() -> Path:
    system = platform.system().lower()
    if system == "windows":
        base_dir = Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming")))
    elif system == "darwin":
        base_dir = Path.home() / "Library" / "Application Support"
    else:
        base_dir = Path.home() / ".local" / "share"
        
    install_dir = base_dir / "specter" / "bin"
    install_dir.mkdir(parents=True, exist_ok=True)
    return install_dir

def find_binary(directory: Path, binary_name: str) -> Path | None:
    for path in directory.rglob(binary_name):
        if path.is_file():
            return path
    return None

def download_and_install(target_dir: Path | None = None) -> Path:
    if target_dir is None:
        target_dir = get_default_install_dir()
    
    binary_name = get_binary_name()
    existing_binary = find_binary(target_dir, binary_name)
    if existing_binary:
        print(f"chrome-headless-shell already installed at: {existing_binary}")
        return existing_binary

    print(f"Fetching download URL from Chrome for Testing API...")
    try:
        with urllib.request.urlopen(API_URL) as response:
            data = json.loads(response.read().decode())
    except Exception as e:
        raise RuntimeError(f"Failed to fetch version metadata from {API_URL}: {e}")

    platform_key = get_platform_key()
    downloads = data.get("channels", {}).get("Stable", {}).get("downloads", {}).get("chrome-headless-shell", [])
    
    download_url = None
    for dl in downloads:
        if dl.get("platform") == platform_key:
            download_url = dl.get("url")
            break
            
    if not download_url:
        raise RuntimeError(f"Could not find download URL for platform: {platform_key}")

    print(f"Downloading chrome-headless-shell from: {download_url}")
    zip_path = target_dir / "chrome-headless-shell.zip"
    
    try:
        with urllib.request.urlopen(download_url) as response, open(zip_path, "wb") as out_file:
            shutil.copyfileobj(response, out_file)
    except Exception as e:
        if zip_path.exists():
            zip_path.unlink()
        raise RuntimeError(f"Failed to download zip: {e}")

    print("Extracting archive...")
    try:
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(target_dir)
    finally:
        if zip_path.exists():
            zip_path.unlink()

    binary_path = find_binary(target_dir, binary_name)
    if not binary_path:
        raise RuntimeError("Extraction completed but chrome-headless-shell binary was not found.")

    if platform.system().lower() != "windows":
        binary_path.chmod(0o755)

    print("Verifying installation...")
    try:
        result = subprocess.run([str(binary_path), "--version"], capture_output=True, text=True, check=True)
        version_str = result.stdout.strip() or result.stderr.strip()
        print(f"Successfully verified binary: {version_str}")
    except Exception as e:
        raise RuntimeError(f"Verification failed: {e}")

    return binary_path

if __name__ == "__main__":
    try:
        download_and_install()
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
