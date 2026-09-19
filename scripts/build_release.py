"""Build allowlisted source and runtime-bundled Windows preview archives."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from code_relay.installer import INSTALL_FILES

VERSION = "0.1.1"
TOP_FILES = [
    "AGENTS.md", "DEVELOPMENT_PRINCIPLES.md", "README.md", "LICENSE", ".gitignore",
    "pyproject.toml", "build-requirements.txt", ".mcp.json", ".codex-plugin/plugin.json",
    "CLOUD_STORAGE.md", "RUNTIME_LIFECYCLE.md", "governance/OWNERSHIP.md",
    "templates/LIFECYCLE_RECORD.md", "governance/incidents/CB-2026-001.md",
]
DIRECTORIES = ["code_relay", "scripts", "skills", "docs", "tests", "verification", ".github"]


def source_files():
    result = [ROOT / name for name in TOP_FILES]
    for directory in DIRECTORIES:
        result.extend(path for path in (ROOT / directory).rglob("*") if path.is_file()
                      and "__pycache__" not in path.parts and path.suffix in {".py", ".md", ".json", ".yml", ".sh", ".txt"})
    return sorted(set(result))


def main():
    subprocess.run([sys.executable, str(ROOT / "scripts/check_release.py")], check=True, cwd=ROOT)
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    archives = []
    source = dist / f"code-relay-{VERSION}-source.zip"
    with zipfile.ZipFile(source, "w", zipfile.ZIP_DEFLATED) as archive:
        for file in source_files():
            archive.write(file, "code-relay/" + file.relative_to(ROOT).as_posix())
    archives.append(source)
    if os.name == "nt" and "--source-only" not in sys.argv:
        arguments = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--onefile", "--noupx",
                     "--hide-console", "hide-early", "--name", "code-relay",
                     "--paths", str(ROOT), "--specpath", str(ROOT / "build"),
                     "--workpath", str(ROOT / "build" / "pyinstaller"),
                     "--distpath", str(dist / "windows"), "--log-level", "WARN"]
        for relative in [".codex-plugin", *INSTALL_FILES]:
            path = ROOT / relative
            destination = (Path("plugin_resources") /
                           (Path(relative) if path.is_dir() else Path(relative).parent)).as_posix()
            arguments += ["--add-data", str(path) + ":" + destination]
        arguments += [str(ROOT / "scripts/entry.py")]
        subprocess.run(arguments, cwd=ROOT, check=True)
        binary = dist / "windows" / "code-relay.exe"
        subprocess.run([str(binary), "self-test"], check=True, timeout=20, cwd=ROOT)
        subprocess.run([sys.executable, str(ROOT / "scripts/smoke_mcp.py"), "--exe", str(binary)], check=True, timeout=25, cwd=ROOT)
        package = dist / f"code-relay-{VERSION}-windows-x64.zip"
        python_license = Path(sys.base_prefix) / "LICENSE.txt"
        assert python_license.exists(), "Bundled CPython licence must be included."
        tcl_files = list((Path(sys.base_prefix) / "tcl").glob("*/license.terms"))
        assert tcl_files, "Bundled Tcl/Tk licences must be included."
        with zipfile.ZipFile(package, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.write(binary, "code-relay/code-relay.exe")
            for name in INSTALL_FILES:
                archive.write(ROOT / name, "code-relay/" + name)
            archive.write(python_license, "code-relay/licenses/CPython-LICENSE.txt")
            for file in tcl_files:
                archive.write(file, "code-relay/licenses/" + file.parent.name + "-license.terms")
        archives.append(package)
    checksums = "\n".join(hashlib.sha256(p.read_bytes()).hexdigest() + "  " + p.name for p in archives) + "\n"
    (dist / "SHA256SUMS.txt").write_text(checksums, encoding="utf-8")
    print(json.dumps({"version": VERSION, "artifacts": [{"path": str(p), "bytes": p.stat().st_size,
                     "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in archives]}, indent=2))


if __name__ == "__main__":
    main()
