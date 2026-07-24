### 2026-07-19 - LaTeX Heading Wrap

**Agent:** Codex (GPT-5)

**Changes:**
- `resume_generation/latex.py:60-101` - Replaced non-wrapping `tabular*` heading rows with `tabularx` rows using reusable ragged wrapping left and right columns.
- `tests/test_resume_generation.py:1826-1888` - Added coverage for long experience and project skill suffixes, preserving complete skill output while asserting the wrapping template structure.

**Rationale:**
Long skill suffixes, dates, and locations were rendered in `l`/`r` table columns, which do not wrap and caused overfull hboxes in generated PDFs. Moving the constraint into the LaTeX macros preserves all resume content and lets LaTeX wrap long fields within the available page width.

**Tests:**
- `test_render_resume_latex_uses_wrapping_heading_columns_for_long_skill_suffixes`: validates long experience and project skill suffixes are retained and rendered through wrapping columns.
- `PYTHONPATH=. pytest tests/test_resume_generation.py`
- `latexmk -pdf -interaction=nonstopmode -halt-on-error -outdir=/tmp/resumecr7-latex-wrap-check/out /tmp/resumecr7-latex-wrap-check/resume.tex`

**Impact:**
Generated LaTeX resumes can now wrap long experience and project heading metadata instead of hiding content past the page boundary.
