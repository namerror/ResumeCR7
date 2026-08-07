from __future__ import annotations

import os
import re
from pathlib import Path

from app.config import settings
from app.resume_generation.models import (
    IntermediateResumeResult,
    ResumeEducationItem,
    ResumeExperienceItem,
    ResumeOutputConfig,
    ResumeProjectItem,
    ResumeSkillsSection,
    ResumeTopSection,
)

DEFAULT_RESUME_TEX_ARTIFACT_PATH = settings.resume_tex_artifact_path

_LATEX_HEADER = r"""\documentclass[letterpaper,9pt]{article}

\usepackage{fontawesome5}
\usepackage{latexsym}
\usepackage[empty]{fullpage}
\usepackage{titlesec}
\usepackage{marvosym}
\usepackage[usenames,dvipsnames]{color}
\usepackage{verbatim}
\usepackage{enumitem}
\usepackage[hidelinks]{hyperref}
\usepackage{fancyhdr}
\usepackage[english]{babel}
\usepackage{tabularx}
\usepackage{graphicx}
\usepackage{mwe}
\usepackage{wrapfig}

\input{glyphtounicode}
\usepackage[default]{lato}

\pagestyle{fancy}
\fancyhf{}
\fancyfoot{}
\renewcommand{\headrulewidth}{0pt}
\renewcommand{\footrulewidth}{0pt}
\setlength{\footskip}{4pt}

% Narrower margins to fit content on one page
\addtolength{\oddsidemargin}{-0.75in}
\addtolength{\evensidemargin}{-0.75in}
\addtolength{\textwidth}{1.5in}
\addtolength{\topmargin}{-0.65in}
\addtolength{\textheight}{1.3in}

\urlstyle{same}

\raggedbottom
\raggedright
\setlength{\tabcolsep}{0in}
\newcolumntype{L}{>{\raggedright\arraybackslash}X}
\newcolumntype{R}[1]{>{\raggedleft\arraybackslash}p{#1}}
\newcommand{\resumeHeadingRightWidth}{1.75in}
\newsavebox{\resumeHeaderBox}
\newcommand{\resumeHeaderLine}[1]{%
\sbox{\resumeHeaderBox}{\small #1}%
\ifdim\wd\resumeHeaderBox>\textwidth
\resizebox{\textwidth}{!}{\usebox{\resumeHeaderBox}}%
\else
\usebox{\resumeHeaderBox}%
\fi
}

% Sections formatting
\titleformat{\section}{
\vspace{-5pt}\scshape\raggedright\large
}{}{0em}{}[\color{black}\titlerule\vspace{-6pt}]

\pdfgentounicode=1

%-------------------------%
\begin{document}

%-------------------------%
% Custom commands
\newcommand{\resumeItem}[1]{
\item\small{
{#1 \vspace{-2pt}}
}
}

\newcommand{\resumeSubheading}[4]{
\vspace{-2pt}\item
\begin{tabularx}{0.97\textwidth}[t]{@{}L R{\resumeHeadingRightWidth}@{}}
\textbf{#1} & #2 \\
\textit{\small#3} & \textit{\small #4} \\
\end{tabularx}\vspace{-7pt}
}

\newcommand{\resumeExperienceSubheading}[5]{
\vspace{-2pt}\item
\begin{tabularx}{0.97\textwidth}[t]{@{}L R{\resumeHeadingRightWidth}@{}}
\textbf{#1} $|$ \textit{\small #2} & #3 \\
\textit{\small#4} & \textit{\small #5} \\
\end{tabularx}\vspace{-7pt}
}

\newcommand{\resumeSubSubheading}[2]{
\item
\begin{tabularx}{0.97\textwidth}{@{}L R{\resumeHeadingRightWidth}@{}}
\textit{\small#1} & \textit{\small #2} \\
\end{tabularx}\vspace{-7pt}
}

\newcommand{\resumeProjectHeading}[2]{
\item
\begin{tabularx}{0.97\textwidth}{@{}L@{}}
\small#1 \\
\end{tabularx}\vspace{-7pt}
}

\newcommand{\resumeSubItem}[1]{\resumeItem{#1}\vspace{-4pt}}

\renewcommand\labelitemii{$\vcenter{\hbox{\tiny$\bullet$}}$}

\newcommand{\resumeSubHeadingListStart}{\begin{itemize}[leftmargin=0.15in, label={}]}
\newcommand{\resumeSubHeadingListEnd}{\end{itemize}}
\newcommand{\resumeItemListStart}{\begin{itemize}}
\newcommand{\resumeItemListEnd}{\end{itemize}\vspace{-5pt}}

\definecolor{Black}{RGB}{0, 0, 0}
\newcommand{\seticon}[1]{\textcolor{Black}{\csname #1\endcsname}}


%-------------------------------------------%
%%%%%%  RESUME STARTS HERE  %%%%%
"""

_LATEX_FOOTER = r"""

%-------------------------------------------%
\end{document}
"""

_LATEX_ESCAPES = {
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
    "\\": r"\textbackslash{}",
}

_LATEX_TEXT_REPLACEMENTS = {
    "\u00a0": " ",
    "\u2010": "-",
    "\u2011": "-",
    "\u2012": "-",
    "\u2013": "-",
    "\u2014": "-",
    "\u2015": "-",
    "\u2212": "-",
    "\u2018": "'",
    "\u2019": "'",
    "\u201a": "'",
    "\u201b": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u201e": '"',
    "\u00ab": '"',
    "\u00bb": '"',
    "\u2022": "-",
    "\u2023": "-",
    "\u2043": "-",
    "\u2219": "-",
    "\u25e6": "-",
    "\u2190": " from ",
    "\u2192": " to ",
    "\u2194": " to ",
    "\u21d2": " to ",
    "\u27f6": " to ",
    "\u2248": " about ",
    "\u223c": " about ",
    "\u2264": " <= ",
    "\u2265": " >= ",
    "\u00b1": " +/- ",
    "\u00d7": " x ",
    "\u00f7": " / ",
    "\u2026": "...",
}


def sanitize_latex_text(text: str) -> str:
    """Normalize generated text to conservative pdfLaTeX-compatible ASCII."""
    normalized = "".join(_LATEX_TEXT_REPLACEMENTS.get(char, char) for char in text)
    ascii_text = "".join(
        char
        if (char == "\n" or char == "\t" or 32 <= ord(char) <= 126)
        else ""
        for char in normalized
    )
    collapsed = re.sub(r"[ \t]{2,}", " ", ascii_text)
    return re.sub(r" +([,.;:!?])", r"\1", collapsed).strip()


def latex_escape(text: str) -> str:
    sanitized = sanitize_latex_text(text)
    return "".join(_LATEX_ESCAPES.get(char, char) for char in sanitized)


def display_url(url: str) -> str:
    normalized = url.strip()
    for prefix in ("https://", "http://"):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix) :]
            break
    if normalized.startswith("www."):
        normalized = normalized[len("www.") :]
    return normalized.rstrip("/")


def resolve_resume_latex_output_path(path: Path | str | None) -> Path:
    if path is None:
        return settings.resume_tex_artifact_path
    normalized = str(path).strip()
    return Path(normalized) if normalized else settings.resume_tex_artifact_path


def resolve_resume_latex_output_path_from_config(config: ResumeOutputConfig) -> Path:
    return resolve_resume_latex_output_path(config.path)


def render_heading(top: ResumeTopSection) -> str:
    contact_items = [
        rf"{{\seticon{{faEnvelope}} {latex_escape(top.email)}}}",
        rf"{{\seticon{{faPhone}} {latex_escape(top.phone)}}}",
    ]
    profile_items: list[str] = []
    if top.linkedin:
        profile_items.append(
            rf"{{\seticon{{faLinkedin}} \underline{{{latex_escape(display_url(top.linkedin))}}}}}"
        )
    if top.github:
        profile_items.append(
            rf"{{\seticon{{faGithub}} \underline{{{latex_escape(display_url(top.github))}}}}}"
        )
    if top.website:
        profile_items.append(
            rf"{{\seticon{{faGlobe}} \underline{{{latex_escape(display_url(top.website))}}}}}"
        )

    header_items = contact_items + profile_items
    header_separator = r"\hspace{0.75em}"
    lines = [
        r"%----------HEADING----------%",
        r"\begin{tabularx}{\textwidth}{@{} X r @{}}",
        r"    \begin{minipage}[t]{\textwidth}",
        rf"        \textbf{{\Large \scshape {latex_escape(top.name)}}} \\[0.5em]",
        f"        \\resumeHeaderLine{{{header_separator.join(header_items)}}}",
    ]
    lines.extend(
        [
            r"    \end{minipage} &",
            r"\end{tabularx}",
        ]
    )
    return "\n".join(lines)


def render_education(items: list[ResumeEducationItem]) -> str:
    lines = [
        r"%-----------EDUCATION-----------%",
        r"\section{Education}",
        r"    \resumeSubHeadingListStart",
        "",
    ]
    for item in items:
        degree = latex_escape(item.degree)
        grade = item.grade.strip()
        degree_and_grade = (
            f"{degree} ({latex_escape(grade)})"
            if grade
            else degree
        )
        lines.extend(
            [
                r"    \resumeSubheading",
                rf"    {{{latex_escape(item.name)}}}{{{latex_escape(_date_range(item.start, item.end))}}}",
                rf"    {{{degree_and_grade}}}{{{latex_escape(item.location)}}}",
            ]
        )
        if item.relevant_coursework:
            coursework = ", ".join(latex_escape(course) for course in item.relevant_coursework)
            lines.extend(
                [
                    r"    \resumeItemListStart",
                    rf"        \resumeItem{{\textbf{{Relevant Coursework:}} {coursework}}}",
                    r"    \resumeItemListEnd",
                ]
            )
        lines.append("")
    lines.append(r"    \resumeSubHeadingListEnd")
    return "\n".join(lines)


def render_experience(items: list[ResumeExperienceItem]) -> str:
    lines = [
        r"%-----------EXPERIENCE-----------%",
        r"\section{Experience}",
        r"\resumeSubHeadingListStart",
        "",
    ]
    for item in items:
        role = latex_escape(item.role)
        skills = _join_escaped(item.skills)
        lines.extend(
            [
                r"    \resumeExperienceSubheading",
                rf"    {{{latex_escape(item.name)}}}{{{role}}}{{{latex_escape(_date_range(item.start, item.end))}}}",
                rf"    {{{skills}}}{{{latex_escape(item.location)}}}",
            ]
        )
        lines.extend(_render_bullet_list(item.bullet_points, indent="    "))
        lines.append("")
    lines.append(r"\resumeSubHeadingListEnd")
    return "\n".join(lines)


def render_projects(items: list[ResumeProjectItem]) -> str:
    lines = [
        r"%-----------PROJECTS-----------%",
        r"\section{Projects}",
        r"\resumeSubHeadingListStart",
        "",
    ]
    for item in items:
        title = rf"\textbf{{{latex_escape(item.name)}}}{_render_skill_suffix(item.skills)}"
        lines.extend(
            [
                r"    \resumeProjectHeading",
                rf"    {{{title}}}{{}}",
            ]
        )
        lines.extend(_render_bullet_list(item.bullet_points, indent="    "))
        lines.append("")
    lines.append(r"\resumeSubHeadingListEnd")
    return "\n".join(lines)


def render_skills(skills: ResumeSkillsSection) -> str:
    return "\n".join(
        [
            r"%-----------PROGRAMMING SKILLS-----------%",
            r"\section{Technical Skills}",
            r"    \begin{itemize}[leftmargin=0.15in, label={}]",
            r"    \small{\item{",
            rf"        \textbf{{Programming Languages}}{{: {_join_escaped(skills.programming)}}} \\",
            rf"        \textbf{{Technologies}}{{: {_join_escaped(skills.technology)}}} \\",
            rf"        \textbf{{Concepts}}{{: {_join_escaped(skills.concepts)}}} \\",
            r"    }}",
            r"    \end{itemize}",
        ]
    )


def render_resume_latex(resume_result: IntermediateResumeResult) -> str:
    sections = [
        _LATEX_HEADER.rstrip(),
        render_heading(resume_result.top),
        render_education(resume_result.education),
        render_experience(resume_result.experience),
        render_projects(resume_result.projects),
        render_skills(resume_result.skills),
        _LATEX_FOOTER.strip(),
    ]
    return "\n\n".join(sections) + "\n"


def write_resume_latex_artifact(
    resume_result: IntermediateResumeResult,
    path: Path | str | None = None,
) -> Path:
    artifact_path = resolve_resume_latex_output_path(path)
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = artifact_path.with_suffix(artifact_path.suffix + ".tmp")
    tmp_path.write_text(render_resume_latex(resume_result), encoding="utf-8")
    os.replace(tmp_path, artifact_path)
    return artifact_path


def _date_range(start: str, end: str | None) -> str:
    if end is None:
        end = "Present"
    return f"{start} -- {end}"


def _join_escaped(values: list[str]) -> str:
    return ", ".join(latex_escape(value) for value in values)


def _render_skill_suffix(skills: list[str]) -> str:
    if not skills:
        return ""
    return rf" $|$ \emph{{{_join_escaped(skills)}}}"


def _render_bullet_list(bullet_points: list[str], *, indent: str) -> list[str]:
    if not bullet_points:
        return []
    lines = [f"{indent}\\resumeItemListStart"]
    lines.extend(
        f"{indent}    \\resumeItem{{{latex_escape(bullet)}}}"
        for bullet in bullet_points
    )
    lines.append(f"{indent}\\resumeItemListEnd")
    return lines
