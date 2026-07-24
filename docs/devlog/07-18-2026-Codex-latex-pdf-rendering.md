### 2026-07-18 - LaTeX PDF Rendering

**Agent:** Codex (GPT-5)

**Changes:**
- `resume_generation/pdf.py` - Added local `latexmk` PDF rendering, default `.tex`/`.pdf` paths, atomic PDF writing, render error wrapping, and a standalone CLI entrypoint.
- `resume_generation/models.py` - Extended `resume_output` with opt-in PDF rendering settings for output path and timeout.
- `resume_generation/main.py` - Added `write_resume_pdf_from_config(...)` and wired the direct module entrypoint to render PDFs after `.tex` generation only when enabled.
- `tests/test_resume_generation.py` - Added config, renderer request, error, helper, and CLI-default coverage.
- `README.md`, `docs/CHANGELOG.md`, `user/resume_generation/config.yaml`, and `resume_generation/__init__.py` - Documented and exported the PDF rendering capability.

**Rationale:**
The renderer stays outside the LaTeX template module so `.tex` generation remains deterministic and independently testable. The implementation is local-only because public LaTeX compile endpoints are operationally brittle and the current project does not need a remote rendering abstraction. The latexmk output directory flag uses `-outdir=<path>` for compatibility with the installed latexmk version that rejected `-output-directory`.

**Tests:**
- `test_load_generation_config_accepts_pdf_resume_output_settings`: validates typed PDF renderer config.
- `test_load_generation_config_defaults_blank_pdf_resume_output_path`: validates default PDF path resolution.
- `test_load_generation_config_rejects_invalid_pdf_resume_output_settings`: validates timeout rejection.
- `test_render_latex_pdf_local_*`: validates local `latexmk` invocation, `-outdir=<path>` usage, command-missing errors, and compile failures with log text.
- `test_write_resume_pdf_from_config_*`: validates opt-in pipeline helper behavior.
- `test_resume_pdf_main_uses_default_paths`: validates standalone script defaults.

**Impact:**
ResumeCR7 can now turn generated LaTeX resume artifacts into PDF files through a minimal, deployable renderer boundary without making PDF compilation mandatory for normal resume generation.
