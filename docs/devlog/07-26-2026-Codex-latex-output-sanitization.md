### 2026-07-26 - Harden LaTeX resume output sanitization

**Agent:** Codex (GPT-5)

**Changes:**
- `app/resume_generation/latex.py` - Added deterministic ASCII normalization before LaTeX escaping and set a safe `\footskip` value in the resume template.
- `app/bulletpoints_generation/llm_client.py` - Added prompt rules requiring plain ASCII bullet text for pdfLaTeX compatibility.
- `tests/test_resume_generation.py` - Added regression coverage for Unicode punctuation/symbol sanitization and rendered generated bullets.
- `tests/test_bulletpoints_llm_client.py` - Added coverage for the ASCII/pdfLaTeX prompt rule.

**Rationale:**
LLM-generated resume bullets can include Unicode symbols such as approximation signs, arrows, smart quotes, nonbreaking hyphens, and emoji. The existing renderer escaped TeX-reserved ASCII characters but passed unsupported Unicode through to pdfLaTeX, causing fatal compilation errors. A renderer-level sanitizer provides deterministic protection even when the LLM ignores formatting guidance, while prompt rules reduce how often sanitization is needed.

**Tests:**
- `test_latex_escape_normalizes_unicode_punctuation_for_pdflatex`: validates common problematic Unicode characters are converted or removed before TeX escaping.
- `test_render_resume_latex_sanitizes_generated_bullet_text`: validates generated project and experience bullets are sanitized in the final `.tex`.
- `test_build_bulletpoint_instructions_distinguishes_exact_and_flexible_counts`: validates bullet-generation instructions include the ASCII/pdfLaTeX safety rule.

**Impact:**
Generated resume `.tex` artifacts are more likely to compile reliably with the existing local `latexmk -pdf` flow, including when LLM output contains typographic Unicode or symbols.
