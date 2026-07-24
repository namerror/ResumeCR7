# Baseline Filter Test
We are testing the baseline filter today to ensure a baseline selection is made before the LLM selection. This is important for token efficiency and better performance. 
This is the payload we used:
```json
{
  "job_role": "Backend Engineer",
  "technology": [
    "CSS", "Node.JS", "Django", "Figma", "Angular", "Docker", "Kubernetes", "AWS", "Google Cloud", "PyTorch", "Unity", "Unreal Engine", "Pandas", "Matplotlib", "SAP", "Springboot", "TailwindCSS"
  ],
  "programming": [
    "Matlab", "Assembly", "TypeScript", "Java", "C#", "Rust", "python"
  ],
  "concepts": [
    "Rest", "API", "Database Management", "Penetration Testing", "Data Visualization", "Networking", "Caching", "Distributed Computing", "Web Development", "Machine Learning", "Fullstack Development", "authentication", "session management", "rate limiting", "multi-threading", "UI design"
  ],
  "baseline_filter": true
}
```

## Results
The response body:
```json
{
  "technology": [
    "AWS",
    "Django",
    "Docker",
    "Google Cloud",
    "Kubernetes"
  ],
  "programming": [
    "C#",
    "Java",
    "python",
    "Rust",
    "TypeScript"
  ],
  "concepts": [
    "API",
    "authentication",
    "Caching",
    "Database Management",
    "Distributed Computing"
  ],
  "details": {
    "technology": {
      "AWS": {
        "source": "llm",
        "normalized_skill": "amazon web services",
        "method_score": 3,
        "normalized_final_score": 1
      },
      "Django": {
        "source": "baseline",
        "baseline_score": 3,
        "normalized_skill": "django",
        "normalized_final_score": 1
      },
      "Docker": {
        "source": "baseline",
        "baseline_score": 3,
        "normalized_skill": "docker",
        "normalized_final_score": 1
      },
      "Google Cloud": {
        "source": "llm",
        "normalized_skill": "google cloud platform",
        "method_score": 3,
        "normalized_final_score": 1
      },
      "Kubernetes": {
        "source": "baseline",
        "baseline_score": 3,
        "normalized_skill": "kubernetes",
        "normalized_final_score": 1
      },
      "Node.JS": {
        "source": "llm",
        "normalized_skill": "nodejs",
        "method_score": 3,
        "normalized_final_score": 1
      },
      "Springboot": {
        "source": "llm",
        "normalized_skill": "springboot",
        "method_score": 3,
        "normalized_final_score": 1
      },
      "Angular": {
        "source": "llm",
        "normalized_skill": "angular",
        "method_score": 0,
        "normalized_final_score": 0
      },
      "CSS": {
        "source": "llm",
        "normalized_skill": "css",
        "method_score": 0,
        "normalized_final_score": 0
      },
      "Figma": {
        "source": "llm",
        "normalized_skill": "figma",
        "method_score": 0,
        "normalized_final_score": 0
      },
      "Matplotlib": {
        "source": "llm",
        "normalized_skill": "matplotlib",
        "method_score": 0,
        "normalized_final_score": 0
      },
      "Pandas": {
        "source": "llm",
        "normalized_skill": "pandas",
        "method_score": 0,
        "normalized_final_score": 0
      },
      "PyTorch": {
        "source": "llm",
        "normalized_skill": "pytorch",
        "method_score": 0,
        "normalized_final_score": 0
      },
      "SAP": {
        "source": "llm",
        "normalized_skill": "sap",
        "method_score": 0,
        "normalized_final_score": 0
      },
      "TailwindCSS": {
        "source": "llm",
        "normalized_skill": "tailwind",
        "method_score": 0,
        "normalized_final_score": 0
      },
      "Unity": {
        "source": "llm",
        "normalized_skill": "unity",
        "method_score": 0,
        "normalized_final_score": 0
      },
      "Unreal Engine": {
        "source": "llm",
        "normalized_skill": "unreal engine",
        "method_score": 0,
        "normalized_final_score": 0
      }
    },
    "programming": {
      "C#": {
        "source": "baseline",
        "baseline_score": 3,
        "normalized_skill": "c#",
        "normalized_final_score": 1
      },
      "Java": {
        "source": "baseline",
        "baseline_score": 3,
        "normalized_skill": "java",
        "normalized_final_score": 1
      },
      "python": {
        "source": "baseline",
        "baseline_score": 3,
        "normalized_skill": "python",
        "normalized_final_score": 1
      },
      "Rust": {
        "source": "llm",
        "normalized_skill": "rust",
        "method_score": 2,
        "normalized_final_score": 0.6666666666666666
      },
      "TypeScript": {
        "source": "llm",
        "normalized_skill": "typescript",
        "method_score": 2,
        "normalized_final_score": 0.6666666666666666
      },
      "Assembly": {
        "source": "llm",
        "normalized_skill": "assembly",
        "method_score": 0,
        "normalized_final_score": 0
      },
      "Matlab": {
        "source": "llm",
        "normalized_skill": "matlab",
        "method_score": 0,
        "normalized_final_score": 0
      }
    },
    "concepts": {
      "API": {
        "source": "baseline",
        "baseline_score": 3,
        "normalized_skill": "api",
        "normalized_final_score": 1
      },
      "authentication": {
        "source": "baseline",
        "baseline_score": 3,
        "normalized_skill": "authentication",
        "normalized_final_score": 1
      },
      "Caching": {
        "source": "llm",
        "normalized_skill": "caching",
        "method_score": 3,
        "normalized_final_score": 1
      },
      "Database Management": {
        "source": "llm",
        "normalized_skill": "database management",
        "method_score": 3,
        "normalized_final_score": 1
      },
      "Distributed Computing": {
        "source": "llm",
        "normalized_skill": "distributed computing",
        "method_score": 3,
        "normalized_final_score": 1
      },
      "multi-threading": {
        "source": "llm",
        "normalized_skill": "multi-threading",
        "method_score": 3,
        "normalized_final_score": 1
      },
      "rate limiting": {
        "source": "llm",
        "normalized_skill": "rate limiting",
        "method_score": 3,
        "normalized_final_score": 1
      },
      "Rest": {
        "source": "llm",
        "normalized_skill": "restful api",
        "method_score": 3,
        "normalized_final_score": 1
      },
      "session management": {
        "source": "llm",
        "normalized_skill": "session management",
        "method_score": 3,
        "normalized_final_score": 1
      },
      "Web Development": {
        "source": "llm",
        "normalized_skill": "web development",
        "method_score": 3,
        "normalized_final_score": 1
      },
      "Fullstack Development": {
        "source": "llm",
        "normalized_skill": "fullstack development",
        "method_score": 2,
        "normalized_final_score": 0.6666666666666666
      },
      "Networking": {
        "source": "llm",
        "normalized_skill": "networking",
        "method_score": 2,
        "normalized_final_score": 0.6666666666666666
      },
      "Machine Learning": {
        "source": "llm",
        "normalized_skill": "machine learning",
        "method_score": 1,
        "normalized_final_score": 0.3333333333333333
      },
      "Penetration Testing": {
        "source": "llm",
        "normalized_skill": "penetration testing",
        "method_score": 1,
        "normalized_final_score": 0.3333333333333333
      },
      "Data Visualization": {
        "source": "llm",
        "normalized_skill": "data visualization",
        "method_score": 0,
        "normalized_final_score": 0
      },
      "UI design": {
        "source": "llm",
        "normalized_skill": "ui design",
        "method_score": 0,
        "normalized_final_score": 0
      }
    },
    "_baseline_filter": {
      "enabled": true,
      "requested_method": "llm",
      "fallback": false,
      "categories": {
        "technology": {
          "recognized": 3,
          "unrecognized": 14,
          "second_pass_scored": 14
        },
        "programming": {
          "recognized": 3,
          "unrecognized": 4,
          "second_pass_scored": 4
        },
        "concepts": {
          "recognized": 2,
          "unrecognized": 14,
          "second_pass_scored": 14
        }
      }
    },
    "_llm": {
      "model": "gpt-5-mini",
      "api_calls": 1,
      "latency_ms": 14350.779,
      "prompt_tokens": 1200,
      "completion_tokens": 1133,
      "total_tokens": 2333
    }
  }
}
```
The returned skills seem reasonable. It seems that with baseline filtering enabled, we also manage to lower the token usage. 

However, I'm trying to figure out why a lot of the skills that should be recognized by baseline filter are still passed on to LLM method. For example, "AWS", "Node.JS" these are all already defined in the baseline filter, so they should not be passed to LLM method at all. We need to investigate this further.

For reference, the baseline filter should look through the role profiles for certain roles, in this case, "Backend Engineer", and pick out the relevant skills that are defined in the baseline filter for that role. 

## Agent Investigation
I investigated the note and reproduced the baseline pre-pass locally with the same payload. The `source: llm` labels are coming from the baseline filter split, not from the role profile loader itself.

The key flow is:

- Baseline filter runs baseline with `include_zero=True` in [baseline_filter.py](/home/leon/Documents/proj/ResumeCR7/app/services/baseline_filter.py):147.
- If a skill’s baseline `score > 0`, it is marked `source: baseline` in [baseline_filter.py](/home/leon/Documents/proj/ResumeCR7/app/services/baseline_filter.py):177.
- If baseline score is `0`, it is added to `unrecognized_inputs` in [baseline_filter.py](/home/leon/Documents/proj/ResumeCR7/app/services/baseline_filter.py):188.
- The unrecognized skills are sent to the requested second pass, and because the request used `method: llm`, those details are marked `source: llm` in [baseline_filter.py](/home/leon/Documents/proj/ResumeCR7/app/services/baseline_filter.py):250.

So the real question is why baseline scores some profile-defined skills as zero.

There are three causes:

1. **Profile keywords are not normalized before matching.**  
   Incoming skills are normalized in [baseline.py](/home/leon/Documents/proj/ResumeCR7/app/scoring/baseline.py):15, but profile keywords are used raw in [baseline.py](/home/leon/Documents/proj/ResumeCR7/app/scoring/baseline.py):20.  
   Example: `AWS` normalizes to `amazon web services` via [synonym_to_normalized.json](/home/leon/Documents/proj/ResumeCR7/app/data/synonym_to_normalized.json):14, but backend profile contains raw `aws` in [backend.yaml](/home/leon/Documents/proj/ResumeCR7/app/data/role_profiles/backend.yaml):23. Those do not match, so `AWS` is sent to LLM.  
   Same issue for `Node.JS`: it normalizes to `nodejs`, while backend has `node.js` in [backend.yaml](/home/leon/Documents/proj/ResumeCR7/app/data/role_profiles/backend.yaml):12.

2. **Partial matching only works in one direction.**  
   Current code checks `normalized_skill in keyword` in [baseline.py](/home/leon/Documents/proj/ResumeCR7/app/scoring/baseline.py):34. That misses cases where the profile keyword is shorter than the input.  
   Example: `Database Management` normalizes to `database management`, while backend has `database` in [backend.yaml](/home/leon/Documents/proj/ResumeCR7/app/data/role_profiles/backend.yaml):3. Since `database management in database` is false, it scores zero. The likely intended partial check would also allow `keyword in normalized_skill`.

3. **Some expected skills are not actually in the Backend profile/category.**  
   `Kubernetes` is correctly marked `source: baseline` in the note. But `Google Cloud` is not in backend `technology`; backend only has concept keyword `cloud`, not technology `gcp` or `google cloud`. `Rust` is in `general`, `devops`, and `security`, but not backend programming. `TypeScript` is frontend programming. Several concepts like `Caching`, `Distributed Computing`, `rate limiting`, and `session management` are not currently backend profile keywords.

I did not make code changes yet. The likely fix is to normalize role profile keywords before comparison, then add a focused test for `AWS`/`Node.JS` under backend baseline filtering. A second, slightly broader fix would make partial matching bidirectional so `Database Management` can match backend keyword `database`, but that changes scoring behavior more broadly and should get a test around category boundaries.

## Fix Progress
- Added role profile keyword normalization to fix problem 1. [details](/docs/devlog/04-16-2026-Codex-normalize-profile-keywords.md)
- Added bidirectional partial matching, and updated token scoring logic to fix problem 2. [details](/docs/devlog/04-17-2026-Codex-token-boundary-containment-scoring.md)

## Post-Fix Test Results
After the fixes, I reran the same payload and got the following response:
```json
{
  "technology": [
    "AWS",
    "Django",
    "Docker",
    "Google Cloud",
    "Kubernetes"
  ],
  "programming": [
    "C#",
    "Java",
    "python",
    "Rust",
    "TypeScript"
  ],
  "concepts": [
    "API",
    "authentication",
    "Caching",
    "Database Management",
    "Distributed Computing"
  ],
  "details": {
    "technology": {
      "AWS": {
        "source": "baseline",
        "baseline_score": 3,
        "normalized_skill": "amazon web services",
        "normalized_final_score": 1
      },
      "Django": {
        "source": "baseline",
        "baseline_score": 3,
        "normalized_skill": "django",
        "normalized_final_score": 1
      },
      "Docker": {
        "source": "baseline",
        "baseline_score": 3,
        "normalized_skill": "docker",
        "normalized_final_score": 1
      },
      "Google Cloud": {
        "source": "baseline",
        "baseline_score": 3,
        "normalized_skill": "google cloud platform",
        "normalized_final_score": 1
      },
      "Kubernetes": {
        "source": "baseline",
        "baseline_score": 3,
        "normalized_skill": "kubernetes",
        "normalized_final_score": 1
      },
      "Node.JS": {
        "source": "baseline",
        "baseline_score": 3,
        "normalized_skill": "nodejs",
        "normalized_final_score": 1
      },
      "Springboot": {
        "source": "llm",
        "normalized_skill": "springboot",
        "method_score": 3,
        "normalized_final_score": 1
      },
      "Angular": {
        "source": "llm",
        "normalized_skill": "angular",
        "method_score": 1,
        "normalized_final_score": 0.3333333333333333
      },
      "Pandas": {
        "source": "llm",
        "normalized_skill": "pandas",
        "method_score": 1,
        "normalized_final_score": 0.3333333333333333
      },
      "PyTorch": {
        "source": "llm",
        "normalized_skill": "pytorch",
        "method_score": 1,
        "normalized_final_score": 0.3333333333333333
      },
      "SAP": {
        "source": "llm",
        "normalized_skill": "sap",
        "method_score": 1,
        "normalized_final_score": 0.3333333333333333
      },
      "CSS": {
        "source": "llm",
        "normalized_skill": "css",
        "method_score": 0,
        "normalized_final_score": 0
      },
      "Figma": {
        "source": "llm",
        "normalized_skill": "figma",
        "method_score": 0,
        "normalized_final_score": 0
      },
      "Matplotlib": {
        "source": "llm",
        "normalized_skill": "matplotlib",
        "method_score": 0,
        "normalized_final_score": 0
      },
      "TailwindCSS": {
        "source": "llm",
        "normalized_skill": "tailwind",
        "method_score": 0,
        "normalized_final_score": 0
      },
      "Unity": {
        "source": "llm",
        "normalized_skill": "unity",
        "method_score": 0,
        "normalized_final_score": 0
      },
      "Unreal Engine": {
        "source": "llm",
        "normalized_skill": "unreal engine",
        "method_score": 0,
        "normalized_final_score": 0
      }
    },
    "programming": {
      "C#": {
        "source": "baseline",
        "baseline_score": 3,
        "normalized_skill": "c#",
        "normalized_final_score": 1
      },
      "Java": {
        "source": "baseline",
        "baseline_score": 3,
        "normalized_skill": "java",
        "normalized_final_score": 1
      },
      "python": {
        "source": "baseline",
        "baseline_score": 3,
        "normalized_skill": "python",
        "normalized_final_score": 1
      },
      "Rust": {
        "source": "llm",
        "normalized_skill": "rust",
        "method_score": 2,
        "normalized_final_score": 0.6666666666666666
      },
      "TypeScript": {
        "source": "llm",
        "normalized_skill": "typescript",
        "method_score": 2,
        "normalized_final_score": 0.6666666666666666
      },
      "Assembly": {
        "source": "llm",
        "normalized_skill": "assembly",
        "method_score": 0,
        "normalized_final_score": 0
      },
      "Matlab": {
        "source": "llm",
        "normalized_skill": "matlab",
        "method_score": 0,
        "normalized_final_score": 0
      }
    },
    "concepts": {
      "API": {
        "source": "baseline",
        "baseline_score": 3,
        "normalized_skill": "api",
        "normalized_final_score": 1
      },
      "authentication": {
        "source": "baseline",
        "baseline_score": 3,
        "normalized_skill": "authentication",
        "normalized_final_score": 1
      },
      "Caching": {
        "source": "llm",
        "normalized_skill": "caching",
        "method_score": 3,
        "normalized_final_score": 1
      },
      "Database Management": {
        "source": "baseline",
        "baseline_score": 3,
        "normalized_skill": "database management",
        "normalized_final_score": 1
      },
      "Distributed Computing": {
        "source": "llm",
        "normalized_skill": "distributed computing",
        "method_score": 3,
        "normalized_final_score": 1
      },
      "multi-threading": {
        "source": "llm",
        "normalized_skill": "multi-threading",
        "method_score": 3,
        "normalized_final_score": 1
      },
      "Networking": {
        "source": "llm",
        "normalized_skill": "networking",
        "method_score": 3,
        "normalized_final_score": 1
      },
      "rate limiting": {
        "source": "llm",
        "normalized_skill": "rate limiting",
        "method_score": 3,
        "normalized_final_score": 1
      },
      "Rest": {
        "source": "baseline",
        "baseline_score": 3,
        "normalized_skill": "restful api",
        "normalized_final_score": 1
      },
      "session management": {
        "source": "llm",
        "normalized_skill": "session management",
        "method_score": 3,
        "normalized_final_score": 1
      },
      "Web Development": {
        "source": "llm",
        "normalized_skill": "web development",
        "method_score": 3,
        "normalized_final_score": 1
      },
      "Fullstack Development": {
        "source": "llm",
        "normalized_skill": "fullstack development",
        "method_score": 1,
        "normalized_final_score": 0.3333333333333333
      },
      "Machine Learning": {
        "source": "llm",
        "normalized_skill": "machine learning",
        "method_score": 1,
        "normalized_final_score": 0.3333333333333333
      },
      "Penetration Testing": {
        "source": "llm",
        "normalized_skill": "penetration testing",
        "method_score": 1,
        "normalized_final_score": 0.3333333333333333
      },
      "Data Visualization": {
        "source": "llm",
        "normalized_skill": "data visualization",
        "method_score": 0,
        "normalized_final_score": 0
      },
      "UI design": {
        "source": "llm",
        "normalized_skill": "ui design",
        "method_score": 0,
        "normalized_final_score": 0
      }
    },
    "_baseline_filter": {
      "enabled": true,
      "requested_method": "llm",
      "fallback": false,
      "categories": {
        "technology": {
          "recognized": 6,
          "unrecognized": 11,
          "second_pass_scored": 11
        },
        "programming": {
          "recognized": 3,
          "unrecognized": 4,
          "second_pass_scored": 4
        },
        "concepts": {
          "recognized": 4,
          "unrecognized": 12,
          "second_pass_scored": 12
        }
      }
    },
    "_llm": {
      "model": "gpt-5-mini",
      "api_calls": 1,
      "latency_ms": 21768.131,
      "prompt_tokens": 1037,
      "completion_tokens": 1080,
      "total_tokens": 2117
    }
  }
}
```

We can see that things are marked correctly by baseline filter now, and the token usage has also gone down from 2333 to 2117. The latency has increased, but that could be due to normal variance in LLM response times. Overall, the results look good and the baseline filter seems to be working as intended now.