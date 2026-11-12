"""Dependency policy check (CLAUDE.md hard constraint 1; KPI "Runtime LLM calls").

Fails if any manifest or lock file lists a language-model or generative-AI client library.
Standard library only, so it runs before anything is installed.
"""

import json
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Matched against normalised package names (lower case, "_" and "." read as "-").
FORBIDDEN = re.compile(
    r"^(@?anthropic(-ai)?(/.*)?|@?openai(/.*)?|langchain.*|@langchain/.*|llama-?index.*|"
    r"litellm|ollama|cohere|mistralai|transformers|huggingface-hub|google-generativeai|"
    r"@google/generative-ai|google-genai|@google/genai|ai|@ai-sdk/.*|replicate|together|groq|"
    r"vllm|llama-cpp-python|sentence-transformers)$"
)


def normalise(name: str) -> str:
    return re.sub(r"[_.]+", "-", name.strip().lower())


def python_name(spec: str) -> str:
    match = re.match(r"\s*([A-Za-z0-9_.-]+)", spec)
    return normalise(match.group(1)) if match else ""


def main() -> int:
    found: list[tuple[str, str]] = []

    for manifest in ROOT.glob("**/package.json"):
        if "node_modules" in manifest.parts or "spikes" in manifest.parts:
            continue
        data = json.loads(manifest.read_text(encoding="utf-8"))
        for section in (
            "dependencies",
            "devDependencies",
            "peerDependencies",
            "optionalDependencies",
        ):
            for name in data.get(section, {}):
                if FORBIDDEN.match(normalise(name)):
                    found.append((str(manifest.relative_to(ROOT)), name))

    lock = ROOT / "package-lock.json"
    if lock.exists():
        for key in json.loads(lock.read_text(encoding="utf-8")).get("packages", {}):
            name = key.rsplit("node_modules/", 1)[-1]
            if name and FORBIDDEN.match(normalise(name)):
                found.append(("package-lock.json", name))

    for pyproject in ROOT.glob("services/**/pyproject.toml"):
        project = tomllib.loads(pyproject.read_text(encoding="utf-8")).get("project", {})
        specs = list(project.get("dependencies", []))
        for extra in project.get("optional-dependencies", {}).values():
            specs.extend(extra)
        for spec in specs:
            if FORBIDDEN.match(python_name(spec)):
                found.append((str(pyproject.relative_to(ROOT)), spec))

    if found:
        print("Forbidden generative-AI dependencies found (CLAUDE.md, hard constraint 1):")
        for where, name in sorted(set(found)):
            print(f"  {where}: {name}")
        return 1
    print("Dependency policy: no LLM or generative-AI libraries.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
