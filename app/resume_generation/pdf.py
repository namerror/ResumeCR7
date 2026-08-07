from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from app.config import settings

DEFAULT_RESUME_PDF_ARTIFACT_PATH = settings.resume_pdf_artifact_path
DEFAULT_RESUME_TEX_INPUT_PATH = settings.resume_tex_artifact_path
DEFAULT_LATEX_PDF_TIMEOUT_SECONDS = 60.0
DEFAULT_LATEX_LOCAL_COMMAND = "latexmk"
PDF_PREREQUISITE_ERROR_PREFIX = "PDF rendering prerequisites are missing."


class LatexPdfRenderError(RuntimeError):
    """Raised when the LaTeX renderer cannot produce a PDF."""


class LatexPdfPrerequisiteError(LatexPdfRenderError):
    """Raised when host PDF rendering dependencies are missing."""


def resolve_resume_pdf_output_path(path: Path | str | None) -> Path:
    if path is None:
        return settings.resume_pdf_artifact_path
    normalized = str(path).strip()
    return Path(normalized) if normalized else settings.resume_pdf_artifact_path


def resolve_resume_user_pdf_output_path(output_dir: Path | str) -> Path:
    normalized = str(output_dir).strip()
    if not normalized:
        raise ValueError("resume_output.output_dir must not be empty")
    output_dir_path = Path(normalized).expanduser()
    artifact_root = settings.resume_generation_artifacts_root.resolve(strict=False)
    resolved_output_dir = output_dir_path.resolve(strict=False)
    if resolved_output_dir == artifact_root or resolved_output_dir.is_relative_to(
        artifact_root
    ):
        raise ValueError(
            "resume_output.output_dir must be outside the internal artifacts directory"
        )
    return output_dir_path / "resume.pdf"


def copy_resume_pdf_to_user_output(
    artifact_path: Path | str,
    output_dir: Path | str,
) -> Path:
    output_path = resolve_resume_user_pdf_output_path(output_dir)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    shutil.copyfile(artifact_path, tmp_path)
    os.replace(tmp_path, output_path)
    return output_path


def render_latex_pdf(
    tex_path: Path | str | None = None,
    pdf_path: Path | str | None = None,
    *,
    timeout_seconds: float = DEFAULT_LATEX_PDF_TIMEOUT_SECONDS,
) -> Path:
    source_path = Path(tex_path) if tex_path is not None else settings.resume_tex_artifact_path
    output_path = resolve_resume_pdf_output_path(pdf_path)
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be greater than 0")
    if not source_path.is_file():
        raise FileNotFoundError(f"LaTeX source file does not exist: {source_path}")

    with tempfile.TemporaryDirectory() as output_dir:
        output_dir_path = Path(output_dir)
        command = [
            DEFAULT_LATEX_LOCAL_COMMAND,
            "-pdf",
            "-interaction=nonstopmode",
            "-halt-on-error",
            f"-outdir={output_dir_path}",
            source_path.name,
        ]
        try:
            completed = subprocess.run(
                command,
                cwd=source_path.parent,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
        except FileNotFoundError as exc:
            raise LatexPdfPrerequisiteError(
                _prerequisite_error_message(
                    f"LaTeX local render command not found: {DEFAULT_LATEX_LOCAL_COMMAND}"
                )
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise LatexPdfRenderError(
                f"LaTeX local render timed out after {timeout_seconds} seconds"
            ) from exc

        log_path = output_dir_path / f"{source_path.stem}.log"
        rendered_pdf_path = output_dir_path / f"{source_path.stem}.pdf"
        if completed.returncode != 0:
            error_message = _local_error_message(
                returncode=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
                log_path=log_path,
            )
            if _is_latex_prerequisite_failure(error_message):
                raise LatexPdfPrerequisiteError(_prerequisite_error_message(error_message))
            raise LatexPdfRenderError(error_message)
        if not rendered_pdf_path.is_file():
            raise LatexPdfRenderError(
                _local_error_message(
                    returncode=completed.returncode,
                    stdout=completed.stdout,
                    stderr=completed.stderr,
                    log_path=log_path,
                    prefix="LaTeX local render completed without producing a PDF",
                )
            )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
        shutil.copyfile(rendered_pdf_path, tmp_path)
        os.replace(tmp_path, output_path)
        return output_path


def _local_error_message(
    *,
    returncode: int,
    stdout: str | None,
    stderr: str | None,
    log_path: Path,
    prefix: str = "LaTeX local render failed",
) -> str:
    parts = [f"{prefix} with exit code {returncode}"]
    stdout_text = (stdout or "").strip()
    stderr_text = (stderr or "").strip()
    if stderr_text:
        parts.append(f"stderr: {stderr_text}")
    if stdout_text:
        parts.append(f"stdout: {stdout_text}")
    if log_path.is_file():
        log_text = log_path.read_text(encoding="utf-8", errors="replace").strip()
        if log_text:
            parts.append(f"log: {log_text}")
    return "\n".join(parts)


def _is_latex_prerequisite_failure(message: str) -> bool:
    return bool(
        re.search(r"LaTeX Error: File `[^`]+\' not found", message)
        or re.search(r"! I can't find file `[^`]+\'", message)
    )


def _prerequisite_error_message(detail: str) -> str:
    return (
        f"{PDF_PREREQUISITE_ERROR_PREFIX} Install latexmk and TeX Live packages. "
        "On Ubuntu/Debian, run resumecr7-install-pdf-dependencies.sh from the release assets "
        "or packaging/linux/install-pdf-dependencies.sh from a source checkout. "
        f"{detail}"
    )


def main() -> Path:
    parser = argparse.ArgumentParser(
        description="Render a LaTeX .tex resume artifact to PDF."
    )
    parser.add_argument(
        "--tex-path",
        default=str(settings.resume_tex_artifact_path),
        help="Path to the LaTeX source file.",
    )
    parser.add_argument(
        "--pdf-path",
        default=str(settings.resume_pdf_artifact_path),
        help="Path where the rendered PDF will be written.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=DEFAULT_LATEX_PDF_TIMEOUT_SECONDS,
        help="Renderer request timeout in seconds.",
    )
    args = parser.parse_args()
    return render_latex_pdf(
        args.tex_path,
        args.pdf_path,
        timeout_seconds=args.timeout_seconds,
    )


if __name__ == "__main__":
    main()
