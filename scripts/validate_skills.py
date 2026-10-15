#!/usr/bin/env python3
"""Validate every skills/*/SKILL.md and keep the Claude and Codex plugin manifests in sync.

Usage:
  python3 scripts/validate_skills.py          # validate, exit 1 on problems
  python3 scripts/validate_skills.py --fix    # also rewrite the plugin manifests (skill list, Codex version)

Checks (mirroring the agent-skills spec and the conventions in CONTRIBUTING.md):
  - frontmatter present and valid YAML (when PyYAML is installed; CI installs it), since Codex
    parses it strictly and skips skills whose frontmatter fails to load
  - `name` equals the folder name, lowercase-hyphenated, <= 64 chars
  - `description` present, <= 1024 chars, says when to use the skill ("Use when" / "Use this skill")
  - `metadata.last-updated` is an ISO date and `metadata.keywords` is a non-empty list
  - relative markdown links and `references/...` mentions resolve to files
  - SKILL.md body stays under 300 lines (move depth into references/)
  - every skill folder is listed in .claude-plugin/plugin.json; .codex-plugin/plugin.json points
    `skills` at ./skills/ and carries the same name and version
  - .agents/plugins/marketplace.json lists the plugin with a source, policy and category
  - README.md links every skill
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

try:
    import yaml
except ImportError:  # optional locally; CI installs it
    yaml = None

ROOT = pathlib.Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"
MANIFEST = ROOT / ".claude-plugin" / "plugin.json"
CODEX_MANIFEST = ROOT / ".codex-plugin" / "plugin.json"
CODEX_MARKETPLACE = ROOT / ".agents" / "plugins" / "marketplace.json"
CODEX_SKILLS_PATH = "./skills/"
README = ROOT / "README.md"
MAX_BODY_LINES = 300

NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s#]+)(?:#[^)]*)?\)")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse_frontmatter(text: str) -> tuple[dict, str] | tuple[None, str]:
    if not text.startswith("---\n"):
        return None, text
    end = text.find("\n---\n", 4)
    if end < 0:
        return None, text
    raw = text[4:end]
    body = text[end + 5:]
    data: dict = {}
    current_key = None
    current_list: list | None = None
    nested: dict | None = None
    for line in raw.splitlines():
        if not line.strip():
            continue
        if line.startswith("  - ") and current_list is not None:
            current_list.append(line[4:].strip())
            continue
        if line.startswith("  ") and nested is not None:
            key, _, value = line.strip().partition(":")
            value = value.strip()
            if value == "":
                current_list = []
                nested[key] = current_list
            else:
                nested[key] = value.strip("'\"")
                current_list = None
            continue
        if line.startswith(" "):
            # continuation of a folded scalar
            if current_key:
                data[current_key] = (data[current_key] + " " + line.strip()).strip()
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        current_list = None
        nested = None
        if value == "":
            nested = {}
            data[key] = nested
            current_key = None
        else:
            data[key] = value.strip("'\"")
            current_key = key
    return data, body


def check_skill(folder: pathlib.Path, problems: list[str]) -> None:
    skill_md = folder / "SKILL.md"
    rel = skill_md.relative_to(ROOT)
    if not skill_md.exists():
        problems.append(f"{folder.relative_to(ROOT)}: missing SKILL.md")
        return
    text = skill_md.read_text(encoding="utf-8")
    fm, body = parse_frontmatter(text)
    if fm is None:
        problems.append(f"{rel}: missing YAML frontmatter")
        return
    if yaml is not None:
        raw = text[4:text.find("\n---\n", 4)]
        try:
            strict = yaml.safe_load(raw)
        except yaml.YAMLError as e:
            problems.append(f"{rel}: frontmatter is not valid YAML ({str(e).splitlines()[0]})")
        else:
            if not isinstance(strict, dict) or not all(
                isinstance(strict.get(k), str) for k in ("name", "description")
            ):
                problems.append(f"{rel}: frontmatter `name` and `description` must be plain strings")
    name = fm.get("name")
    if name != folder.name:
        problems.append(f"{rel}: name '{name}' != folder '{folder.name}'")
    if not name or not NAME_RE.match(name) or len(name) > 64:
        problems.append(f"{rel}: name must be lowercase-hyphenated and <= 64 chars")
    desc = fm.get("description", "")
    if not desc:
        problems.append(f"{rel}: missing description")
    elif len(desc) > 1024:
        problems.append(f"{rel}: description is {len(desc)} chars (max 1024)")
    elif not re.search(r"\buse (when|this skill|it|only|for|before|after)\b", desc, re.I):
        problems.append(f"{rel}: description should say when to use the skill ('Use when ...')")
    meta = fm.get("metadata")
    if not isinstance(meta, dict):
        problems.append(f"{rel}: missing metadata block (last-updated, keywords)")
    else:
        lu = meta.get("last-updated", "")
        if not DATE_RE.match(str(lu)):
            problems.append(f"{rel}: metadata.last-updated must be YYYY-MM-DD")
        kw = meta.get("keywords")
        if not isinstance(kw, list) or not kw:
            problems.append(f"{rel}: metadata.keywords must be a non-empty list")
    lines = body.count("\n")
    if lines > MAX_BODY_LINES:
        problems.append(f"{rel}: body is {lines} lines (> {MAX_BODY_LINES}); move detail into references/")
    for target in LINK_RE.findall(body):
        if re.match(r"^[a-z]+://", target) or target.startswith("mailto:"):
            continue
        if not (folder / target).exists():
            problems.append(f"{rel}: broken link '{target}'")
    for ref in set(re.findall(r"`(references/[^`]+)`", body)):
        if not (folder / ref).exists():
            problems.append(f"{rel}: mentions missing file '{ref}'")


def main(argv: list[str]) -> int:
    fix = "--fix" in argv
    problems: list[str] = []
    folders = sorted(p for p in SKILLS.iterdir() if p.is_dir())
    for folder in folders:
        check_skill(folder, problems)

    expected = [f"./skills/{f.name}" for f in folders]
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else None
    if manifest is None:
        problems.append(f"{MANIFEST.relative_to(ROOT)}: missing")
    elif manifest.get("skills") != expected:
        if fix:
            manifest["skills"] = expected
            MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            print(f"updated {MANIFEST.relative_to(ROOT)} ({len(expected)} skills)")
        else:
            problems.append(
                f"{MANIFEST.relative_to(ROOT)}: skills list out of date; run scripts/validate_skills.py --fix"
            )

    codex = json.loads(CODEX_MANIFEST.read_text(encoding="utf-8")) if CODEX_MANIFEST.exists() else None
    if codex is None:
        problems.append(f"{CODEX_MANIFEST.relative_to(ROOT)}: missing")
    else:
        name = (manifest or {}).get("name")
        version = (manifest or {}).get("version")
        if codex.get("skills") != CODEX_SKILLS_PATH or codex.get("version") != version:
            if fix:
                codex["skills"] = CODEX_SKILLS_PATH
                codex["version"] = version
                CODEX_MANIFEST.write_text(json.dumps(codex, indent=2) + "\n", encoding="utf-8")
                print(f"updated {CODEX_MANIFEST.relative_to(ROOT)}")
            else:
                problems.append(
                    f"{CODEX_MANIFEST.relative_to(ROOT)}: `skills` must be \"{CODEX_SKILLS_PATH}\" and "
                    "version must match .claude-plugin/plugin.json; run scripts/validate_skills.py --fix"
                )
        if codex.get("name") != name:
            problems.append(f"{CODEX_MANIFEST.relative_to(ROOT)}: name '{codex.get('name')}' != '{name}'")
        if not (codex.get("description") and (codex.get("author") or {}).get("name")):
            problems.append(f"{CODEX_MANIFEST.relative_to(ROOT)}: needs description and author.name")
        prompts = (codex.get("interface") or {}).get("defaultPrompt", [])
        if len(prompts) > 3 or any(len(p) > 128 for p in prompts):
            problems.append(f"{CODEX_MANIFEST.relative_to(ROOT)}: interface.defaultPrompt is at most 3 x 128 chars")

        market = (
            json.loads(CODEX_MARKETPLACE.read_text(encoding="utf-8")) if CODEX_MARKETPLACE.exists() else None
        )
        mrel = CODEX_MARKETPLACE.relative_to(ROOT)
        entry = next((p for p in (market or {}).get("plugins", []) if p.get("name") == codex.get("name")), None)
        if market is None:
            problems.append(f"{mrel}: missing")
        elif entry is None:
            problems.append(f"{mrel}: no plugin entry named '{codex.get('name')}'")
        else:
            source = entry.get("source") or {}
            if source.get("source") == "local" and not (ROOT / source.get("path", "")).joinpath(
                ".codex-plugin", "plugin.json"
            ).exists():
                problems.append(f"{mrel}: local source path does not contain .codex-plugin/plugin.json")
            policy = entry.get("policy") or {}
            if policy.get("installation") not in ("AVAILABLE", "INSTALLED_BY_DEFAULT", "NOT_AVAILABLE"):
                problems.append(f"{mrel}: policy.installation must be AVAILABLE, INSTALLED_BY_DEFAULT or NOT_AVAILABLE")
            if policy.get("authentication") not in ("ON_INSTALL", "ON_USE"):
                problems.append(f"{mrel}: policy.authentication must be ON_INSTALL or ON_USE")
            if not entry.get("category"):
                problems.append(f"{mrel}: plugin entry needs a category")

    readme = README.read_text(encoding="utf-8") if README.exists() else ""
    for folder in folders:
        if f"skills/{folder.name}/SKILL.md" not in readme:
            problems.append(f"README.md: skill '{folder.name}' is not listed")

    if problems:
        print("\n".join(problems))
        print(f"\n{len(problems)} problem(s) in {len(folders)} skills")
        return 1
    print(f"OK: {len(folders)} skills valid")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
