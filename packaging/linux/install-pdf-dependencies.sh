#!/usr/bin/env bash
set -euo pipefail

packages=(
  latexmk
  texlive-latex-recommended
  texlive-latex-extra
  texlive-fonts-recommended
  texlive-fonts-extra
  texlive-extra-utils
)

required_commands=(
  latexmk
  pdflatex
  kpsewhich
)

required_tex_files=(
  fontawesome5.sty
  lato.sty
  mwe.sty
  wrapfig.sty
  titlesec.sty
  glyphtounicode.tex
)

if [[ ! -r /etc/os-release ]]; then
  echo "Unable to detect Linux distribution: /etc/os-release is not readable." >&2
  exit 1
fi

# shellcheck disable=SC1091
. /etc/os-release

distro_ids=" ${ID:-} ${ID_LIKE:-} "
if [[ "${distro_ids}" != *" debian "* && "${distro_ids}" != *" ubuntu "* ]]; then
  echo "Unsupported Linux distribution for this installer: ${PRETTY_NAME:-unknown}." >&2
  echo "Install latexmk and a TeX Live distribution that provides the ResumeCR7 template packages." >&2
  exit 1
fi

if ! command -v apt-get >/dev/null 2>&1; then
  echo "apt-get is required by this Ubuntu/Debian installer." >&2
  exit 1
fi

sudo_command=()
if [[ "$(id -u)" -ne 0 ]]; then
  if ! command -v sudo >/dev/null 2>&1; then
    echo "sudo is required when this installer is not run as root." >&2
    exit 1
  fi
  sudo_command=(sudo)
fi

echo "Installing ResumeCR7 PDF dependencies with apt..."
"${sudo_command[@]}" apt-get update
"${sudo_command[@]}" apt-get install -y "${packages[@]}"

echo "Verifying ResumeCR7 PDF dependencies..."
missing=0

for command_name in "${required_commands[@]}"; do
  if command -v "${command_name}" >/dev/null 2>&1; then
    echo "ok: ${command_name}"
  else
    echo "missing: ${command_name}"
    missing=1
  fi
done

if command -v kpsewhich >/dev/null 2>&1; then
  for tex_file in "${required_tex_files[@]}"; do
    if kpsewhich "${tex_file}" >/dev/null 2>&1; then
      echo "ok: ${tex_file}"
    else
      echo "missing: ${tex_file}"
      missing=1
    fi
  done
else
  echo "skipped: TeX package checks require kpsewhich"
fi

if [[ "${missing}" -ne 0 ]]; then
  echo "PDF dependency installation completed, but required tools or TeX files are still missing." >&2
  exit 1
fi

echo "ResumeCR7 PDF dependencies are installed."
