# Contributing

## One skill, one folder

```
skills/<name>/
  SKILL.md              # required; frontmatter + instructions, under 300 lines
  references/*.md       # optional depth the agent reads on demand (progressive disclosure)
  *.kt, *.pro, *.yml    # optional files the skill tells the agent to copy or adapt
```

- `<name>` is lowercase-hyphenated, at most 64 characters, and equals `name` in the frontmatter.
- Run `python3 scripts/validate_skills.py --fix` before committing. It checks the rules below and
  rewrites the skill list in `.claude-plugin/plugin.json` and keeps `.codex-plugin/plugin.json`
  (which points at `./skills/`) on the same version. With PyYAML installed it also parses the
  frontmatter as strict YAML, the way Codex does; CI installs it and runs the same script.

`bin/android-skills.mjs` (the `npx` installer) copies whatever is in `skills/`, so a new skill
needs no installer change. The validator keeps `package.json` on the plugin version.

## Frontmatter

```yaml
---
name: edge-to-edge-insets
description: <what it does> - <the concrete topics it covers>. Use when <triggers>. Do not use for <neighbouring topic> (see <other-skill>).
metadata:
  last-updated: '2026-10-15'
  keywords:
  - edge-to-edge
  - window insets
---
```

- The description is the only thing the agent sees before deciding to load the skill. It must
  name the topics (so a task mentioning them matches), say **when** to use it, and, where a
  neighbouring skill exists, say when **not** to. Keep it under 1024 characters.
- `keywords` are the search terms a person or tool would use; `last-updated` changes whenever
  the body changes materially.

## Body

Our skills are opinionated rule sets with short code, not tutorials. The structure that has
worked best:

1. One paragraph: the rule of the skill and which neighbouring skills own the adjacent topics.
2. **Prerequisites**: library versions, platform facts, flags the agent must check first.
3. **Steps** in the order the work happens (inventory → change → verify), or a decision table
   when the skill is about choosing.
4. **RIGHT / WRONG** code pairs for the mistakes LLMs actually make, with one line saying why.
5. **Scope guards**: when a rule does *not* apply (for example "lazy layouts only").
6. **Verification**: how the change is proven, ideally "fail first" (`verification-discipline`).
7. **Report format** for audit-style skills, so output is comparable across runs.
8. **Checklist** at the end: the agent runs it before claiming done.

Keep `com.example.app` / `App*` names; never embed project-specific facts (package names,
component registries, API origins). Those belong in the project's `CLAUDE.md`.

## Adding or changing a skill

1. Check the existing skills for overlap. Prefer extending an existing skill or cross-linking
   over a near-duplicate.
2. Write the skill, run the validator, add a row to the README table in the right section.
3. Test it: give an agent a task the description should trigger and one it should not; read the
   result for wrong API names and version-specific claims.

## Releasing

Run the **Release** workflow (Actions → Release → Run workflow) with a tag such as `v0.3.0`. It
validates the skills, writes the version into both plugin manifests and `package.json`, commits and tags
`main`, and publishes a GitHub release with a zip of the skills and a list of skills changed since
the previous tag. Plugin installs pin to the manifest version, so every change people should
receive needs a release.
