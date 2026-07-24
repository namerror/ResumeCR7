### 2026-07-19 - LaTeX Project Heading Width

**Agent:** Codex (GPT-5)

**Changes:**
- `resume_generation/latex.py:106-110` - Changed project headings to use a single full-width wrapping column instead of reserving right-side date/location space.
- `tests/test_resume_generation.py:1919-1920` - Added assertions that project headings use the full-width column and no longer render as two-column rows.

**Rationale:**
Experience headings need a right-side column for date and location, but project headings currently pass an empty right-side value. Reusing the experience layout wasted horizontal space and caused project skill suffixes to wrap earlier than necessary.

**Tests:**
- `test_render_resume_latex_uses_wrapping_heading_columns_for_long_skill_suffixes`: validates distinct wrapping layouts for experience and project headings.
- `PYTHONPATH=. pytest tests/test_resume_generation.py`
- `latexmk -pdf -interaction=nonstopmode -halt-on-error -outdir=/tmp/resumecr7-latex-project-fullwidth-check/out /tmp/resumecr7-latex-project-fullwidth-check/resume.tex`

**Impact:**
Project skill suffixes now use the full available heading width and wrap only near the actual page edge.
