---
name: verification-discipline
description: How to verify Android work so that "it passes" means something - make every gate fail once before trusting it, use controls for probes, print the bytes that cross a boundary, measure rendering instead of reading shaders, ask external systems for their state, and report checks as PASS/FAIL/NOT_RUN/BLOCKED. Use before claiming a change works, when a check passes suspiciously easily, when CI and local disagree, or when diagnosing a store, device or server refusal.
metadata:
  last-updated: '2026-10-15'
  keywords:
  - verification
  - testing discipline
  - controls
  - fail first
  - evidence
  - PASS/FAIL reporting
---

# Verification discipline

A check you have never seen fail is a claim, not a check. These rules come from real failures where
every gate was green and the product was broken.

## Gates

- **Make it fail first.** Break what the gate guards (missing function in a test source set, a lint
  violation, a perturbed constant) and watch it go red. Then restore.
- If a deliberate break does **not** turn a gate red, that is information about the gate's boundary.
  Write the boundary down next to the number ("the hash proves the colour maths, not the spatial
  passes") instead of picking a different thing to break.
- **One named command** for local and CI (`./gradlew verify`). A copied task or file list drifts,
  always toward passing. Prefer globs to hand-maintained lists.
- A build gate proves nothing about a file the build has no reason to read. Check the artefact
  exists (compiled class, packaged resource), not only the exit code.
- Name a gate after what it covers. A task called "typecheck" that skips generated sources is a claim
  about a subset nobody wrote down.
- **Read the output.** `grep -c error` over output turns "command not found" into zero errors.
  Use exit status, or print the tail and read it. Be suspicious of a sweep where every file passes
  first time. A new tool must be installed in the worktree that uses it.
- Run the gate on exactly what you commit. In a shared tree, stage the paths you changed (not
  `git add -A`) and read `git diff --cached`.

## Probes need controls

A negative result from a probe you have never seen succeed is not evidence. Ask the probe for
something you know is there first.

```bash
# Is my string in the APK? Control: a string you saw on screen ten minutes ago.
unzip -p app.apk classes3.dex > /tmp/probe.dex      # write to a file; piping binary into strings can read nothing
strings /tmp/probe.dex | grep -c KnownPresentClass   # control, must be non-zero
strings /tmp/probe.dex | grep -c NewClass
```

Gradle `UP-TO-DATE` with a newer mtime is not staleness: Gradle hashes contents.

## Assertions

- Assert the value you expect, not the absence of one you do not ("is dimmed", not "is not red"):
  a negative assertion passes on an empty screen.
- When a visual check passes on the first run, sample the neighbourhood: what the point *is* tells
  you where it landed (a white selection handle is "not red" too).
- Name the property a comparison measures, then name a defect that leaves that property untouched.
  Rendering always has at least geometry **and** colour; add the second measurement.
- Pick thresholds between two measured numbers: the passing case and the deliberately failing case.

## Boundaries

- **Print the bytes.** Not the model, not the DTO: the encoded string that leaves the process.
  Serializers omit defaults; servers may require keys to be present.
- An error message describes what the validator wants, not which way you violated it. Reproduce the
  message from a known input before believing its diagnosis.
- A repair must know its units: the same field name can be pixels in one place and a fraction in
  another.
- Write guards that cross the boundary (client test that derives the server's required keys from
  the server's own schema), so a new server rule fails the client's suite.

## Rendering and GPU code

A shader is not verified by reading it, by matching a CPU reference in prose, or by compiling.
Render it and compare pixels. When a value is in doubt, encode it into an output channel and read it
back. Watch for dialect fallbacks (a missing `#version 300 es` first line can silently select an
older GLSL) and uniforms that mean a padded texture size rather than the output frame.

## External systems

- Ask the system, not a comment: the store's track listing for used `versionCode`s, the device for
  what is installed, the server for what it accepted.
- When a store or payment provider refuses a well-formed request, read **every** returned field,
  including human-readable ones (`title` suffixes like `(unreviewed)`).
- A null that the shape can never hold proves nothing.
- Before concluding "the external system is broken", consider that your evidence is incomplete.

## Half-built mechanisms

When a guard looks expensive, check that anything ever trips it: a revocation check with no
revoker, a feature flag nobody sets, a config value that silently defaults to "off" (`0`, empty).
Grep for the writer, not the reader. A default that is "a working state by design" is exactly how a
missing configuration survives every release.

## Devices

- Mass identical failures on one device: try a second device before reading code (see
  `android-testing`).
- Render/input claims need device observation; "the screenshot was produced" is not "the
  screenshot was checked".

## Reporting

Report each check as **PASS / FAIL / NOT_RUN / BLOCKED**, name what CI does not cover, and say
which results are local-only evidence. Never present an inference as a measurement, and when an
explanation turns out to be invented, correct it where you published it.

## Housekeeping

Push a task branch as soon as it has a commit; a pushed branch survives a deleted worktree. Saying
"I'm done with this worktree" is an instruction someone may act on.
