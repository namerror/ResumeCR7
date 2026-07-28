#!/usr/bin/env bash
set -u

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

missing=0

echo "Checking ResumeCR7 PDF dependencies..."

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

if [[ "${missing}" -eq 0 ]]; then
  echo "ResumeCR7 PDF dependencies are installed."
else
  echo "ResumeCR7 PDF dependencies are missing. On Ubuntu/Debian, run resumecr7-install-pdf-dependencies.sh from the release assets or packaging/linux/install-pdf-dependencies.sh from a source checkout."
fi

exit "${missing}"
