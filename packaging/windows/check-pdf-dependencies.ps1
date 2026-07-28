$ErrorActionPreference = "Stop"

$requiredCommands = @(
    "latexmk",
    "pdflatex",
    "kpsewhich"
)

$requiredTexFiles = @(
    "fontawesome5.sty",
    "lato.sty",
    "mwe.sty",
    "wrapfig.sty",
    "titlesec.sty",
    "glyphtounicode.tex"
)

$missing = $false

Write-Host "Checking ResumeCR7 PDF dependencies..."

foreach ($commandName in $requiredCommands) {
    if (Get-Command $commandName -ErrorAction SilentlyContinue) {
        Write-Host "ok: $commandName"
    } else {
        Write-Host "missing: $commandName"
        $missing = $true
    }
}

if (Get-Command "kpsewhich" -ErrorAction SilentlyContinue) {
    foreach ($texFile in $requiredTexFiles) {
        & kpsewhich $texFile *> $null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "ok: $texFile"
        } else {
            Write-Host "missing: $texFile"
            $missing = $true
        }
    }
} else {
    Write-Host "skipped: TeX package checks require kpsewhich"
}

if ($missing) {
    Write-Host "ResumeCR7 PDF dependencies are missing. Install MiKTeX or TeX Live with latexmk, pdflatex, and the required template packages."
    exit 1
}

Write-Host "ResumeCR7 PDF dependencies are installed."
exit 0
