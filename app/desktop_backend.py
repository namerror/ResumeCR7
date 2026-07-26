from __future__ import annotations

import argparse
import os
from pathlib import Path


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the ResumeCR7 desktop backend sidecar.")
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host interface to bind. Defaults to 127.0.0.1.",
    )
    parser.add_argument(
        "--port",
        type=int,
        required=True,
        help="Port to bind. The desktop shell selects an available loopback port.",
    )
    parser.add_argument(
        "--packaged",
        action="store_true",
        help="Enable packaged runtime defaults for app-data storage.",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        help="Override the ResumeCR7 runtime data directory.",
    )
    return parser


def configure_desktop_environment(*, packaged: bool, data_dir: Path | None) -> None:
    if packaged:
        os.environ["RESUMECR7_PACKAGED"] = "true"
    if data_dir is not None:
        os.environ["RESUMECR7_DATA_DIR"] = str(data_dir)


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    configure_desktop_environment(packaged=args.packaged, data_dir=args.data_dir)

    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=False,
        access_log=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
