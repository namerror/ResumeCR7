### 2026-07-19 - LaTeX Header Contact Line

**Agent:** Codex (GPT-5)

**Changes:**
- `resume_generation/latex.py:63-71` - Added a shrink-only `\resumeHeaderLine` helper for fitting the full contact/profile row within `\textwidth`.
- `resume_generation/latex.py:176-202` - Combined email, phone, LinkedIn, GitHub, and website into one compact header line with tighter spacing.
- `tests/test_resume_generation.py:1798-1856` - Added renderer assertions for the header helper and single-line contact/profile output.

**Rationale:**
The previous heading renderer forced profile links onto a second line after email and phone. A single combined row better matches the intended compact resume header, while shrink-only fitting avoids dropping fields or permanently reducing the default font size.

**Tests:**
- `test_render_resume_latex_keeps_contact_and_profiles_on_one_header_line`: validates that all contact and profile fields render into one `\resumeHeaderLine` with compact spacing.
- `PYTHONPATH=. pytest tests/test_resume_generation.py`
- `latexmk -pdf -interaction=nonstopmode -halt-on-error -outdir=/tmp/resumecr7-latex-header-check/out /tmp/resumecr7-latex-header-check/resume.tex`

**Impact:**
Generated LaTeX resumes now keep the main contact and profile metadata together under the candidate name, with automatic shrink-to-fit behavior for unusually long rows.
