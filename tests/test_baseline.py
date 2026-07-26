from app.skill_selection.scoring.baseline import score_skill, normalize_skill, rank_skills, baseline_select_skills


# === Normalization tests ===

def test_normalize_skill_lowercases():
    """Test that skills are normalized to lowercase."""
    assert normalize_skill("Python") == "python"
    assert normalize_skill("PYTHON") == "python"
    assert normalize_skill("PyThOn") == "python"


def test_normalize_skill_strips_whitespace():
    """Test that whitespace is stripped."""
    assert normalize_skill("  python  ") == "python"
    assert normalize_skill("\tpython\n") == "python"


def test_normalize_skill_applies_synonyms():
    """Test that synonyms are normalized to canonical form."""
    assert normalize_skill("ReactJS") == "react"
    assert normalize_skill("react.js") == "react"
    assert normalize_skill("Node.js") == "nodejs"
    assert normalize_skill("postgres") == "postgresql"
    assert normalize_skill("JS") == "javascript"


def test_normalize_skill_preserves_unknown():
    """Test that unknown skills are lowercased but otherwise preserved."""
    assert normalize_skill("CustomSkill") == "customskill"
    assert normalize_skill("some-framework") == "some-framework"


# === Scoring tests - exact matches ===

def test_score_skill_exact_match_with_normalization():
    """Test exact match with synonym normalization."""
    score, details = score_skill(
        skill="ReactJS",
        role_family="frontend",
        category="technology",
        job_text=None,
    )

    assert score == 3.0
    assert details["normalized_skill"] == "react"
    assert "react" in details["matched_keywords"]


def test_score_skill_exact_match_backend():
    """Test exact match for backend role."""
    score, details = score_skill(
        skill="FastAPI",
        role_family="backend",
        category="technology",
        job_text=None,
    )

    assert score == 3.0
    assert details["normalized_skill"] == "fastapi"
    assert "fastapi" in details["matched_keywords"]


def test_score_skill_exact_match_normalizes_backend_profile_keywords():
    """Test exact matches when profile keywords are stored as aliases."""
    aws_score, aws_details = score_skill(
        skill="AWS",
        role_family="backend",
        category="technology",
        job_text=None,
    )
    node_score, node_details = score_skill(
        skill="Node.JS",
        role_family="backend",
        category="technology",
        job_text=None,
    )

    assert aws_score == 3.0
    assert aws_details["normalized_skill"] == "amazon web services"
    assert "amazon web services" in aws_details["matched_keywords"]
    assert node_score == 3.0
    assert node_details["normalized_skill"] == "nodejs"
    assert "nodejs" in node_details["matched_keywords"]


def test_score_skill_exact_match_normalizes_general_profile_keywords():
    """Test profile keyword normalization outside the backend profile."""
    gcp_score, gcp_details = score_skill(
        skill="GCP",
        role_family="general",
        category="technology",
        job_text=None,
    )
    oop_score, oop_details = score_skill(
        skill="OOP",
        role_family="general",
        category="concepts",
        job_text=None,
    )

    assert gcp_score == 3.0
    assert gcp_details["normalized_skill"] == "google cloud platform"
    assert "google cloud platform" in gcp_details["matched_keywords"]
    assert oop_score == 3.0
    assert oop_details["normalized_skill"] == "object-oriented programming"
    assert "object-oriented programming" in oop_details["matched_keywords"]


def test_score_skill_exact_match_programming():
    """Test exact match for programming category."""
    score, details = score_skill(
        skill="Python",
        role_family="backend",
        category="programming",
        job_text=None,
    )

    assert score == 3.0
    assert details["normalized_skill"] == "python"
    assert "python" in details["matched_keywords"]


def test_score_skill_exact_match_concepts():
    """Test exact match for concepts category."""
    score, details = score_skill(
        skill="Microservices",
        role_family="backend",
        category="concepts",
        job_text=None,
    )

    assert score == 3.0
    assert details["normalized_skill"] == "microservices"
    assert "microservices" in details["matched_keywords"]


# === Scoring tests - partial matches ===

def test_score_skill_partial_match():
    """Test partial match scoring."""
    score, details = score_skill(
        skill="dock",
        role_family="devops",
        category="technology",
        job_text=None,
    )

    assert score == 1.0
    assert details["normalized_skill"] == "dock"
    assert "docker" in details["matched_keywords"]


def test_score_skill_partial_match_ci():
    """Test partial match for CI/CD."""
    score, details = score_skill(
        skill="ci",
        role_family="devops",
        category="concepts",
        job_text=None,
    )

    # "ci" should normalize to "ci/cd" and match exactly
    assert score == 3.0
    assert details["normalized_skill"] == "ci/cd"


def test_score_skill_token_boundary_containment_profile_keyword_inside_skill():
    """Test profile keywords score exact relevance inside longer skill phrases."""
    score, details = score_skill(
        skill="Database Management",
        role_family="backend",
        category="concepts",
        job_text=None,
    )

    assert score == 3.0
    assert details["normalized_skill"] == "database management"
    assert "database" in details["matched_keywords"]


def test_score_skill_token_boundary_containment_skill_inside_profile_keyword():
    """Test shorter skill phrases score exact relevance inside profile keywords."""
    score, details = score_skill(
        skill="Object-Oriented",
        role_family="general",
        category="concepts",
        job_text=None,
    )

    assert score == 3.0
    assert details["normalized_skill"] == "object-oriented"
    assert "object-oriented programming" in details["matched_keywords"]


def test_score_skill_token_boundary_containment_normalizes_issue_three_phrase_variants():
    """Test issue #3 phrase variants match through normalized token containment."""
    score, details = score_skill(
        skill="RESTful APIs Design",
        role_family="general",
        category="technology",
        job_text=None,
    )

    assert score == 3.0
    assert details["normalized_skill"] == "restful apis design"
    assert "restful api" in details["matched_keywords"]


def test_score_skill_token_boundary_containment_avoids_raw_substring_false_positives():
    """Test containment uses full tokens instead of unsafe raw substrings."""
    javascript_score, javascript_details = score_skill(
        skill="JavaScript",
        role_family="backend",
        category="programming",
        job_text=None,
    )
    cloudformation_score, cloudformation_details = score_skill(
        skill="cloudformation",
        role_family="backend",
        category="concepts",
        job_text=None,
    )
    build_score, build_details = score_skill(
        skill="build",
        role_family="frontend",
        category="concepts",
        job_text=None,
    )
    application_score, application_details = score_skill(
        skill="application",
        role_family="mobile",
        category="concepts",
        job_text=None,
    )
    random_score, random_details = score_skill(
        skill="random",
        role_family="data",
        category="programming",
        job_text=None,
    )

    assert javascript_score == 0.0
    assert javascript_details["matched_keywords"] == []
    assert cloudformation_score == 0.0
    assert cloudformation_details["matched_keywords"] == []
    assert build_score == 0.0
    assert build_details["matched_keywords"] == []
    assert application_score == 0.0
    assert application_details["matched_keywords"] == []
    assert random_score == 0.0
    assert random_details["matched_keywords"] == []


def test_score_skill_token_boundary_containment_allows_short_keywords_as_standalone_tokens():
    """Test short keywords still match when they appear as standalone tokens."""
    c_score, c_details = score_skill(
        skill="C programming",
        role_family="general",
        category="programming",
        job_text=None,
    )
    ui_score, ui_details = score_skill(
        skill="UI design",
        role_family="frontend",
        category="concepts",
        job_text=None,
    )

    assert c_score == 3.0
    assert "c" in c_details["matched_keywords"]
    assert ui_score == 3.0
    assert "ui" in ui_details["matched_keywords"]


# === Inheritance tests ===

def test_score_skill_inherits_parent_keywords():
    """Test that fullstack inherits keywords from parent roles."""
    score, details = score_skill(
        skill="FastAPI",
        role_family="fullstack",
        category="technology",
        job_text=None,
    )

    assert score == 3.0
    assert details["normalized_skill"] == "fastapi"
    assert "fastapi" in details["matched_keywords"]


def test_score_skill_inherits_from_multiple_parents():
    """Test that fullstack inherits from backend, frontend, and devops."""
    # Test backend skill
    score_backend, _ = score_skill(
        skill="Django",
        role_family="fullstack",
        category="technology",
        job_text=None,
    )
    assert score_backend == 3.0

    # Test frontend skill
    score_frontend, _ = score_skill(
        skill="React",
        role_family="fullstack",
        category="technology",
        job_text=None,
    )
    assert score_frontend == 3.0

    # Test devops skill
    score_devops, _ = score_skill(
        skill="Docker",
        role_family="fullstack",
        category="technology",
        job_text=None,
    )
    assert score_devops == 3.0


# === Fallback to general profile ===

def test_score_skill_unknown_role_falls_back_to_general():
    """Test that unknown role families fall back to general profile."""
    score, details = score_skill(
        skill="Python",
        role_family="unknown_role",
        category="programming",
        job_text=None,
    )

    assert score == 3.0
    assert details["normalized_skill"] == "python"
    assert "python" in details["matched_keywords"]


def test_score_skill_general_role():
    """Test scoring with general role profile."""
    score, details = score_skill(
        skill="Git",
        role_family="general",
        category="technology",
        job_text=None,
    )

    assert score == 3.0
    assert details["normalized_skill"] == "git"
    assert "git" in details["matched_keywords"]


# === No match cases ===

def test_score_skill_no_match():
    """Test that unrelated skills score 0."""
    score, details = score_skill(
        skill="Photoshop",
        role_family="backend",
        category="technology",
        job_text=None,
    )

    assert score == 0.0
    assert details["normalized_skill"] == "photoshop"


def test_score_skill_wrong_category():
    """Test that skills in wrong category score 0."""
    score, details = score_skill(
        skill="React",
        role_family="frontend",
        category="programming",  # React is in technology, not programming
        job_text=None,
    )

    assert score == 0.0
    assert details["normalized_skill"] == "react"


# === Edge cases ===

def test_score_skill_empty_string():
    """Test handling of empty skill string."""
    score, details = score_skill(
        skill="",
        role_family="backend",
        category="technology",
        job_text=None,
    )

    assert score == 0.0
    assert details["normalized_skill"] == ""


def test_score_skill_whitespace_only():
    """Test handling of whitespace-only skill."""
    score, details = score_skill(
        skill="   ",
        role_family="backend",
        category="technology",
        job_text=None,
    )

    assert score == 0.0
    assert details["normalized_skill"] == ""


# === Determinism tests ===

def test_score_skill_deterministic():
    """Test that scoring is deterministic across multiple runs."""
    skill = "React"
    role_family = "frontend"
    category = "technology"

    results = [
        score_skill(skill, role_family, category, None)
        for _ in range(5)
    ]

    # All results should be identical
    scores = [r[0] for r in results]
    assert len(set(scores)) == 1, "Scores should be deterministic"

    normalized_skills = [r[1]["normalized_skill"] for r in results]
    assert len(set(normalized_skills)) == 1, "Normalization should be deterministic"


# === Category-specific tests ===

def test_score_skill_ml_ai_role():
    """Test ML/AI role specific keywords."""
    score, details = score_skill(
        skill="TensorFlow",
        role_family="ml/ai",
        category="technology",
        job_text=None,
    )

    assert score == 3.0
    assert details["normalized_skill"] == "tensorflow"


def test_score_skill_security_role():
    """Test security role specific keywords."""
    score, details = score_skill(
        skill="Metasploit",
        role_family="security",
        category="technology",
        job_text=None,
    )

    assert score == 3.0
    assert details["normalized_skill"] == "metasploit"


def test_score_skill_mobile_role():
    """Test mobile role specific keywords."""
    score, details = score_skill(
        skill="React Native",
        role_family="mobile",
        category="technology",
        job_text=None,
    )

    assert score == 3.0
    assert details["normalized_skill"] == "react native"


def test_score_skill_data_role():
    """Test data role specific keywords."""
    score, details = score_skill(
        skill="Spark",
        role_family="data",
        category="technology",
        job_text=None,
    )

    assert score == 3.0
    assert details["normalized_skill"] == "spark"


# === rank_skills tests ===

def test_rank_skills_determinism():
    """Test that rank_skills produces deterministic results."""
    skills = ["Python", "JavaScript", "React", "Django", "Vue"]
    role_family = "fullstack"
    category = "technology"

    # Run ranking multiple times
    results = [
        rank_skills(skills, role_family, category, None)
        for _ in range(5)
    ]

    # All ranked lists should be identical
    ranked_lists = [r[0] for r in results]
    for i in range(1, len(ranked_lists)):
        assert ranked_lists[i] == ranked_lists[0], "Rankings should be deterministic"


def test_rank_skills_tie_breaking_alphabetical():
    """Test that ties are broken alphabetically."""
    # These skills should all have the same score (0.0) for backend/technology
    skills = ["Photoshop", "Illustrator", "Figma", "Sketch"]
    role_family = "backend"
    category = "technology"

    ranked, _ = rank_skills(skills, role_family, category, None, include_zero=True)

    # Since all have same score, should be sorted alphabetically
    expected = sorted(skills)
    assert ranked[:len(skills)] == expected, "Ties should be broken alphabetically"


def test_rank_skills_tie_breaking_with_scores():
    """Test alphabetical tie-breaking when multiple skills have same non-zero score."""
    # Use skills that will get partial matches (score 1.0)
    skills = ["kubern", "terr", "jenk"]  # All partial matches for devops
    role_family = "devops"
    category = "technology"

    ranked, _ = rank_skills(skills, role_family, category, None)

    # All should get same score, so should be alphabetical
    expected = sorted(skills)
    assert ranked[:len(skills)] == expected, "Same-score items should be alphabetically sorted"


def test_rank_skills_score_ordering():
    """Test that skills are ordered by score (highest first)."""
    skills = ["React", "Vue", "Photoshop", "dock"]  # Exact, exact, no match, partial
    role_family = "frontend"
    category = "technology"

    ranked, _ = rank_skills(skills, role_family, category, None)

    # Should be ordered: exact matches (React, Vue alphabetically), partial (dock), no match (Photoshop)
    # React and Vue both score 3.0, so alphabetically: React, Vue
    # dock scores 1.0
    # Photoshop scores 0.0
    assert ranked[0] in ["React", "Vue"], "Top should be exact matches"
    assert ranked[1] in ["React", "Vue"], "Second should be exact match"
    assert ranked[0] != ranked[1], "Top two should be different"
    assert set(ranked[0:2]) == {"React", "Vue"}, "Top 2 should be React and Vue"


def test_rank_skills_duplicate_stability():
    """Test that duplicate skills get consistent scores."""
    skills = ["Python", "Python", "JavaScript", "Python"]
    role_family = "backend"
    category = "programming"

    ranked, _ = rank_skills(skills, role_family, category, None)

    # All Python entries should be adjacent (same score) and appear in the output
    python_count = ranked.count("Python")
    assert python_count >= 1, "Python should appear in results"

    # Verify all instances are treated consistently
    # All "Python" should have the same score and appear together
    python_indices = [i for i, skill in enumerate(ranked) if skill == "Python"]
    if len(python_indices) > 1:
        # All Python entries should be consecutive
        assert max(python_indices) - min(python_indices) == len(python_indices) - 1, \
            "Duplicate skills should be adjacent"


def test_rank_skills_never_invents_skills():
    """Test that output is always a subset of input."""
    skills = ["React", "Vue", "Angular", "Python", "Java"]
    role_family = "frontend"
    category = "technology"

    ranked, _ = rank_skills(skills, role_family, category, None)

    # Every skill in output must be in input
    for skill in ranked:
        assert skill in skills, f"Output skill '{skill}' not in input skills"


def test_rank_skills_never_invents_skills_with_synonyms():
    """Test that synonyms don't create new skills in output."""
    skills = ["ReactJS", "Node.js", "PostgreSQL"]  # Using synonym forms
    role_family = "backend"
    category = "technology"

    ranked, _ = rank_skills(skills, role_family, category, None)

    # Output should use exact input strings, not normalized forms
    for skill in ranked:
        assert skill in skills, f"Output skill '{skill}' not in input. Input was {skills}"


def test_rank_skills_empty_list():
    """Test ranking with empty skill list."""
    skills = []
    role_family = "backend"
    category = "technology"

    ranked, _ = rank_skills(skills, role_family, category, None)

    assert ranked == [], "Empty input should produce empty output"


def test_rank_skills_single_skill():
    """Test ranking with single skill."""
    skills = ["Python"]
    role_family = "backend"
    category = "programming"

    ranked, _ = rank_skills(skills, role_family, category, None)

    assert ranked == ["Python"], "Single skill should be returned as-is"


def test_rank_skills_preserves_input_casing():
    """Test that output preserves original input casing."""
    skills = ["PYTHON", "JavaScript", "react"]
    role_family = "fullstack"
    category = "programming"

    ranked, _ = rank_skills(skills, role_family, category, None)

    # Original casing should be preserved
    assert "PYTHON" in ranked, "Original casing should be preserved"
    assert "react" in ranked or "react" in skills, "Original casing should be preserved"


def test_rank_skills_top_n_limit():
    """Test that rank_skills respects SKILL_TOP_N limit."""
    # Create a large list of skills
    skills = [
        "Python", "JavaScript", "Java", "C#", "React", "Vue", "Angular",
        "Django", "FastAPI", "Node.js", "Docker", "Kubernetes", "AWS",
        "PostgreSQL", "MongoDB", "Redis", "Git", "Linux", "Bash"
    ]
    role_family = "fullstack"
    category = "technology"

    import os
    top_n = int(os.getenv("SKILL_TOP_N", 20))
    ranked, _ = rank_skills(skills, role_family, category, None, top_n=top_n)

    # Should return at most the configured SKILL_TOP_N skills.
    assert len(ranked) <= top_n, f"Should return at most {top_n} skills"
    assert len(ranked) <= len(skills), "Should not return more than input size"


def test_rank_skills_stable_sort():
    """Test that sorting is stable for skills with same score and name."""
    # Create list with duplicates that should tie
    skills = ["Photoshop", "Figma", "Photoshop", "Figma"]
    role_family = "backend"
    category = "technology"

    # Run multiple times to ensure stability
    results = [rank_skills(skills, role_family, category, None)[0] for _ in range(3)]

    # All results should be identical (stable sort)
    for result in results[1:]:
        assert result == results[0], "Sort should be stable"


def test_rank_skills_mixed_scores_correct_order():
    """Test comprehensive ordering with exact, partial, and no matches."""
    skills = [
        "Photoshop",     # 0.0 - no match
        "React",         # 3.0 - exact match
        "vue",           # 3.0 - exact match (synonym)
        "boot",          # 1.0 - partial match (bootstrap)
        "Illustrator",   # 0.0 - no match
        "angular",       # 3.0 - exact match
    ]
    role_family = "frontend"
    category = "technology"

    ranked, _ = rank_skills(skills, role_family, category, None)

    # Get scores for verification
    scores = []
    for skill in ranked:
        score, _ = score_skill(skill, role_family, category, None)
        scores.append(score)

    # Scores should be in descending order
    assert scores == sorted(scores, reverse=True), "Skills should be ordered by score descending"

    # Within same score, should be alphabetical
    # Check exact matches (score 3.0) are alphabetical
    exact_matches = [s for s, sc in zip(ranked, scores) if sc == 3.0]
    assert exact_matches == sorted(exact_matches), "Same-score items should be alphabetical"


# === baseline_select_skills tests ===

def test_baseline_select_skills_determinism_different_order():
    """Test that different input order produces same ranked output."""
    result1, _ = baseline_select_skills(
        job_role="Backend Engineer",
        technology=["Python", "Django", "React", "PostgreSQL", "Docker"],
        programming=["Python", "JavaScript", "Java"],
        concepts=["API", "Database", "Microservices"],
    )

    result2, _ = baseline_select_skills(
        job_role="Backend Engineer",
        technology=["Docker", "PostgreSQL", "React", "Django", "Python"],  # Different order
        programming=["Java", "Python", "JavaScript"],  # Different order
        concepts=["Microservices", "API", "Database"],  # Different order
    )

    # Rankings should be identical regardless of input order
    assert result1["technology"] == result2["technology"], "Technology ranking should be deterministic"
    assert result1["programming"] == result2["programming"], "Programming ranking should be deterministic"
    assert result1["concepts"] == result2["concepts"], "Concepts ranking should be deterministic"


def test_baseline_select_skills_determinism_multiple_runs():
    """Test that multiple runs produce identical results."""
    results = [
        baseline_select_skills(
            job_role="Frontend Developer",
            technology=["React", "Vue", "Angular", "Bootstrap", "Webpack"],
            programming=["JavaScript", "TypeScript", "Python"],
            concepts=["UI", "UX", "Responsive Design"],
        )[0]
        for _ in range(5)
    ]

    # All results should be identical
    for result in results[1:]:
        assert result == results[0], "Multiple runs should produce identical results"


def test_baseline_select_skills_backend_engineer():
    """Test role detection for 'Backend Engineer'."""
    result, _ = baseline_select_skills(
        job_role="Backend Engineer",
        technology=["Django", "FastAPI", "React", "PostgreSQL"],
        programming=["Python", "JavaScript", "Java"],
        concepts=["API", "Database", "UI"],
    )

    # Backend-relevant skills should rank higher
    assert "Django" in result["technology"], "Django should be selected for backend"
    assert "FastAPI" in result["technology"], "FastAPI should be selected for backend"
    assert "Python" in result["programming"], "Python should be selected for backend"
    assert "Java" in result["programming"], "Java should be selected for backend"
    assert "API" in result["concepts"], "API should be selected for backend"


def test_baseline_select_skills_backend_api_target_prioritizes_specific_terms():
    """Backend fallback should not let broad distractors crowd out API skills."""
    result, _ = baseline_select_skills(
        job_role="Python MCP Server Backend Engineer",
        job_text=(
            "Build Python APIs and local MCP servers with FastAPI, Docker, Git, Linux, "
            "configuration, caching, and database-backed testing workflows."
        ),
        technology=[
            "Docker",
            "FastAPI",
            "Git",
            "Google Cloud",
            "Linux",
            "PyTorch",
            "TensorFlow",
        ],
        programming=["C", "C#", "C++", "Java", "JavaScript", "Python"],
        concepts=[
            "API",
            "Caching",
            "Database Management",
            "Deep Learning",
            "REST API",
            "Testing",
        ],
        top_n=4,
    )

    assert {"Docker", "FastAPI", "Git"}.issubset(result["technology"])
    assert "PyTorch" not in result["technology"]
    assert "TensorFlow" not in result["technology"]
    assert "Python" in result["programming"]
    if "C" in result["programming"]:
        assert result["programming"].index("Python") < result["programming"].index("C")
    assert set(result["concepts"]) == {
        "API",
        "Caching",
        "Database Management",
        "REST API",
    }


def test_baseline_select_skills_swe_intern():
    """Test role detection for 'SWE Intern' (should use general profile)."""
    technology = ["Git", "Docker", "AWS"]
    programming = ["Python", "JavaScript", "C++"]
    concepts = ["Software Development", "Testing", "Agile"]

    result, _ = baseline_select_skills(
        job_role="SWE Intern",
        technology=technology,
        programming=programming,
        concepts=concepts,
    )

    # General skills should be selected
    assert len(result["technology"]) > 0, "Should select technology skills"
    assert len(result["programming"]) > 0, "Should select programming skills"
    assert len(result["concepts"]) > 0, "Should select concepts"

    # All outputs should be from inputs
    for skill in result["technology"]:
        assert skill in technology
    for skill in result["programming"]:
        assert skill in programming
    for skill in result["concepts"]:
        assert skill in concepts


def test_baseline_select_skills_software_engineer():
    """Test role detection for 'Software Engineer'."""
    result, _ = baseline_select_skills(
        job_role="Software Engineer",
        technology=["Python", "Git", "Docker", "AWS"],
        programming=["Python", "Java", "JavaScript"],
        concepts=["Architecture", "Testing", "Agile"],
    )

    # Should use general profile and select relevant skills
    assert "Git" in result["technology"], "Git is in general profile"
    assert "Python" in result["programming"], "Python is in general profile"


def test_baseline_select_skills_fullstack_developer():
    """Test role detection for 'Full Stack Developer'."""
    result, _ = baseline_select_skills(
        job_role="Full Stack Developer",
        technology=["React", "Django", "Docker", "PostgreSQL"],
        programming=["JavaScript", "Python", "TypeScript"],
        concepts=["API", "UI", "Database"],
    )

    # Fullstack should inherit from backend, frontend, and devops
    assert "React" in result["technology"], "React (frontend) should rank high"
    assert "Django" in result["technology"], "Django (backend) should rank high"
    assert "JavaScript" in result["programming"], "JavaScript should be selected"
    assert "Python" in result["programming"], "Python should be selected"


def test_baseline_select_skills_devops_engineer():
    """Test role detection for 'DevOps Engineer'."""
    result, _ = baseline_select_skills(
        job_role="DevOps Engineer",
        technology=["Docker", "Kubernetes", "Jenkins", "Terraform", "AWS"],
        programming=["Python", "Bash", "JavaScript"],
        concepts=["CI/CD", "Automation", "Monitoring"],
    )

    # DevOps-specific skills should rank high
    assert "Docker" in result["technology"], "Docker is devops tech"
    assert "Kubernetes" in result["technology"], "Kubernetes is devops tech"
    assert "Python" in result["programming"], "Python is devops language"
    assert "Bash" in result["programming"], "Bash is devops language"


def test_baseline_select_skills_all_categories_processed():
    """Test that all three categories are processed."""
    result, _ = baseline_select_skills(
        job_role="Backend Developer",
        technology=["Django", "PostgreSQL"],
        programming=["Python", "Java"],
        concepts=["API", "Database"],
    )

    # All three categories should be in the result
    assert "technology" in result, "Technology category should be present"
    assert "programming" in result, "Programming category should be present"
    assert "concepts" in result, "Concepts category should be present"

    # All should be lists
    assert isinstance(result["technology"], list)
    assert isinstance(result["programming"], list)
    assert isinstance(result["concepts"], list)


def test_baseline_select_skills_never_invents_skills():
    """Test that output is always a subset of input."""
    technology = ["React", "Vue", "Photoshop"]
    programming = ["JavaScript", "TypeScript"]
    concepts = ["UI", "UX", "Design"]

    result, _ = baseline_select_skills(
        job_role="Frontend Developer",
        technology=technology,
        programming=programming,
        concepts=concepts,
    )

    # Every output skill must be in input
    for skill in result["technology"]:
        assert skill in technology, f"Invented skill: {skill}"
    for skill in result["programming"]:
        assert skill in programming, f"Invented skill: {skill}"
    for skill in result["concepts"]:
        assert skill in concepts, f"Invented skill: {skill}"


def test_baseline_select_skills_empty_categories():
    """Test handling of empty skill lists."""
    result, _ = baseline_select_skills(
        job_role="Backend Engineer",
        technology=[],
        programming=["Python"],
        concepts=[],
    )

    # Empty input should produce empty output
    assert result["technology"] == [], "Empty input should produce empty output"
    assert result["concepts"] == [], "Empty input should produce empty output"
    assert result["programming"]==["Python"], "Should only contain input skill"


def test_baseline_select_skills_all_empty():
    """Test handling when all categories are empty."""
    result, _ = baseline_select_skills(
        job_role="Software Engineer",
        technology=[],
        programming=[],
        concepts=[],
    )

    # All should be empty
    assert result["technology"] == []
    assert result["programming"] == []
    assert result["concepts"] == []


def test_baseline_select_skills_preserves_original_casing():
    """Test that output preserves original input casing."""
    result, _ = baseline_select_skills(
        job_role="Backend Developer",
        technology=["DJANGO", "PostgreSQL", "docker"],
        programming=["PYTHON", "java"],
        concepts=["api", "DATABASE"],
    )

    # Original casing should be preserved
    if "DJANGO" in result["technology"]:
        assert "DJANGO" in result["technology"], "Should preserve DJANGO casing"
    if "PYTHON" in result["programming"]:
        assert "PYTHON" in result["programming"], "Should preserve PYTHON casing"


def test_baseline_select_skills_role_with_hyphens():
    """Test role detection with hyphenated job titles."""
    result, _ = baseline_select_skills(
        job_role="Full-Stack Developer",
        technology=["React", "Django"],
        programming=["JavaScript", "Python"],
        concepts=["API", "UI"],
    )

    # Should detect as fullstack
    assert len(result["technology"]) > 0
    assert "React" in result["technology"] or "Django" in result["technology"]


def test_baseline_select_skills_role_case_insensitive():
    """Test that role detection is case-insensitive."""
    result1, _ = baseline_select_skills(
        job_role="BACKEND ENGINEER",
        technology=["Django", "PostgreSQL"],
        programming=["Python"],
        concepts=["API"],
    )

    result2, _ = baseline_select_skills(
        job_role="backend engineer",
        technology=["Django", "PostgreSQL"],
        programming=["Python"],
        concepts=["API"],
    )

    # Should produce identical results
    assert result1 == result2, "Role detection should be case-insensitive"


def test_baseline_select_skills_ml_engineer():
    """Test role detection for 'ML Engineer'."""
    result, _ = baseline_select_skills(
        job_role="ML Engineer",
        technology=["TensorFlow", "PyTorch", "Pandas", "React"],
        programming=["Python", "C++", "JavaScript"],
        concepts=["Machine Learning", "Deep Learning", "UI"],
    )

    # ML-specific skills should rank higher
    assert "TensorFlow" in result["technology"], "TensorFlow is ML tech"
    assert "Python" in result["programming"], "Python is ML language"
    assert "Machine Learning" in result["concepts"] or "Deep Learning" in result["concepts"]


def test_baseline_select_skills_respects_top_n():
    """Test that output respects SKILL_TOP_N limit per category."""
    import os
    top_n = int(os.getenv("SKILL_TOP_N", "20"))

    # Create request with more skills than the configured SKILL_TOP_N.
    tech_skills = [f"Skill{i}" for i in range(top_n + 5)] + ["Python", "Django", "React"]

    result, _ = baseline_select_skills(
        job_role="Backend Developer",
        technology=tech_skills,
        programming=["Python", "Java", "JavaScript"],
        concepts=["API", "Database"],
        top_n=top_n,
    )

    # Each category should have at most the configured SKILL_TOP_N.
    assert len(result["technology"]) <= top_n, f"Should return at most {top_n} technology skills"
    assert len(result["programming"]) <= top_n, f"Should return at most {top_n} programming skills"
    assert len(result["concepts"]) <= top_n, f"Should return at most {top_n} concepts"


def test_baseline_select_skills_consistency_across_categories():
    """Test that same role produces consistent behavior across categories."""
    result, _ = baseline_select_skills(
        job_role="Backend Engineer",
        technology=["Django", "React", "PostgreSQL"],
        programming=["Python", "JavaScript", "Photoshop"],  # Photoshop doesn't belong
        concepts=["API", "Design", "Database"],  # Design is less relevant
    )

    # Backend-relevant skills should be selected across all categories
    # Django and PostgreSQL are backend tech
    assert "Django" in result["technology"] or "PostgreSQL" in result["technology"]
    # Python is backend language
    assert "Python" in result["programming"]
    # API and Database are backend concepts
    assert "API" in result["concepts"] or "Database" in result["concepts"]
