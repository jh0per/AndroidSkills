#!/usr/bin/env python3
"""Validate every skills/*/SKILL.md and keep .claude-plugin/plugin.json in sync.

Usage:
  python3 scripts/validate_skills.py          # validate, exit 1 on problems
  python3 scripts/validate_skills.py --fix    # also rewrite the plugin manifest skill list

Checks (mirroring the agent-skills spec and the conventions in CONTRIBUTING.md):
  - frontmatter present, `name` equals the folder name, lowercase-hyphenated, <= 64 chars
  - `description` present, <= 1024 chars, says when to use the skill ("Use when" / "Use this skill")
  - `metadata.last-updated` is an ISO date and `metadata.keywords` is a non-empty list
  - relative markdown links and `references/...` mentions resolve to files
  - SKILL.md body stays under 300 lines (move depth into references/)
  - every skill folder is listed in .claude-plugin/plugin.json and .codex-plugin/plugin.json,
    and the two manifests carry the same version
  - README.md links every skill
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"
MANIFEST = ROOT / ".claude-plugin" / "plugin.json"
CODEX_MANIFEST = ROOT / ".codex-plugin" / "plugin.json"
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
    codex_expected = [{"source": {"path": p}} for p in expected]
    if codex is None:
        problems.append(f"{CODEX_MANIFEST.relative_to(ROOT)}: missing")
    else:
        version = (manifest or {}).get("version")
        if codex.get("skills") != codex_expected or codex.get("version") != version:
            if fix:
                codex["skills"] = codex_expected
                codex["version"] = version
                CODEX_MANIFEST.write_text(json.dumps(codex, indent=2) + "\n", encoding="utf-8")
                print(f"updated {CODEX_MANIFEST.relative_to(ROOT)} ({len(expected)} skills)")
            else:
                problems.append(
                    f"{CODEX_MANIFEST.relative_to(ROOT)}: skills list or version out of date; "
                    "run scripts/validate_skills.py --fix"
                )

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
