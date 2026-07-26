from __future__ import annotations

import argparse
import platform
import shutil
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BINARY_NAME = "resumecr7-backend"


def host_triple() -> str:
    result = subprocess.run(
        ["rustc", "-vV"],
        check=True,
        capture_output=True,
        text=True,
    )
    for line in result.stdout.splitlines():
        if line.startswith("host: "):
            return line.removeprefix("host: ").strip()
    raise RuntimeError("Unable to determine Rust host target triple from `rustc -vV`.")


def executable_name(binary_name: str, target_triple: str) -> str:
    suffix = ".exe" if "windows" in target_triple or platform.system() == "Windows" else ""
    return f"{binary_name}-{target_triple}{suffix}"


def build_sidecar(
    *,
    binary_name: str = DEFAULT_BINARY_NAME,
    target_triple: str | None = None,
    dist_dir: Path | None = None,
    work_dir: Path | None = None,
    output_dir: Path | None = None,
) -> Path:
    target = target_triple or host_triple()
    dist = dist_dir or REPO_ROOT / "build" / "desktop-sidecar" / "dist"
    work = work_dir or REPO_ROOT / "build" / "desktop-sidecar" / "work"
    output = output_dir or REPO_ROOT / "frontend" / "src-tauri" / "binaries"
    dist.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)

    import PyInstaller.__main__

    PyInstaller.__main__.run(
        [
            "--clean",
            "--onefile",
            "--name",
            binary_name,
            "--distpath",
            str(dist),
            "--workpath",
            str(work),
            "--specpath",
            str(work),
            "--collect-data",
            "app",
            "--hidden-import",
            "app.main",
            str(REPO_ROOT / "app" / "desktop_backend.py"),
        ]
    )

    built_name = f"{binary_name}.exe" if platform.system() == "Windows" else binary_name
    built_path = dist / built_name
    if not built_path.exists():
        raise FileNotFoundError(f"PyInstaller did not produce expected sidecar: {built_path}")

    target_path = output / executable_name(binary_name, target)
    shutil.copy2(built_path, target_path)
    target_path.chmod(target_path.stat().st_mode | 0o111)
    return target_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the ResumeCR7 desktop backend sidecar.")
    parser.add_argument("--target-triple", help="Tauri target triple suffix. Defaults to rustc host.")
    parser.add_argument("--binary-name", default=DEFAULT_BINARY_NAME)
    args = parser.parse_args(argv)

    target_path = build_sidecar(binary_name=args.binary_name, target_triple=args.target_triple)
    print(target_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
