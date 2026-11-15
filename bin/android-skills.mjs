#!/usr/bin/env node
// Install, update and remove the skills from this repository for coding agents.
//
//   npx github:jh0per/AndroidSkills list
//   npx github:jh0per/AndroidSkills add compose-mvi-viewmodel runtime-permissions --agent=claude,codex
//   npx github:jh0per/AndroidSkills add --all --project=.
//   npx github:jh0per/AndroidSkills update --all
//   npx github:jh0per/AndroidSkills remove runtime-permissions
//
// No dependencies; Node 18+.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const SKILLS_DIR = path.join(ROOT, "skills");
const MARKER = ".android-kmp-skills";
const PKG = JSON.parse(fs.readFileSync(path.join(ROOT, "package.json"), "utf8"));

// Where each agent reads skills from: [user-level dir, project-level dir], and the home folder
// whose presence means the agent is installed (used when --agent is not given).
const AGENTS = {
  claude: { global: ".claude/skills", project: ".claude/skills", detect: ".claude", label: "Claude Code" },
  codex: { global: ".agents/skills", project: ".agents/skills", detect: ".codex", label: "Codex" },
  gemini: { global: ".gemini/skills", project: ".gemini/skills", detect: ".gemini", label: "Gemini CLI" },
  antigravity: {
    global: ".gemini/antigravity/skills",
    project: ".agent/skills",
    detect: ".gemini/antigravity",
    label: "Antigravity",
  },
};

const HELP = `android-skills ${PKG.version}: Android and Kotlin Multiplatform skills for coding agents

Usage:
  android-skills list [--installed] [--agent=..] [--project=PATH]
  android-skills add <skill...> | --all [--agent=..] [--project=PATH] [--force]
  android-skills update [<skill...>] | --all [--agent=..] [--project=PATH]
  android-skills remove <skill...> | --all [--agent=..] [--project=PATH]

Options:
  --agent=LIST     Comma-separated: ${Object.keys(AGENTS).join(", ")}.
                   Default: every agent found in your home directory.
  --project=PATH   Install into a project (e.g. .claude/skills, .agents/skills) instead of
                   your user-level skill folders.
  --all            Every skill (add, remove) or every installed skill (update).
  --force          Overwrite a same-named skill that was not installed by this tool.
  -h, --help       Show this help.  -V, --version  Print the version.

update without arguments refreshes every skill this tool installed. Skills you customise should
be renamed, otherwise update overwrites them.`;

function parseArgs(argv) {
  const opts = { names: [], all: false, force: false, installed: false, agent: null, project: null };
  for (const arg of argv) {
    if (arg === "--all") opts.all = true;
    else if (arg === "--force") opts.force = true;
    else if (arg === "--installed") opts.installed = true;
    else if (arg === "-h" || arg === "--help") opts.help = true;
    else if (arg === "-V" || arg === "--version") opts.version = true;
    else if (arg.startsWith("--agent=")) opts.agent = arg.slice(8);
    else if (arg.startsWith("--project=")) opts.project = arg.slice(10) || ".";
    else if (arg === "--project") opts.project = ".";
    else if (arg.startsWith("-")) fail(`unknown option ${arg}`);
    else if (!opts.command) opts.command = arg;
    else opts.names.push(arg);
  }
  return opts;
}

function fail(message) {
  console.error(`android-skills: ${message}`);
  process.exit(1);
}

function readSkills() {
  return fs
    .readdirSync(SKILLS_DIR, { withFileTypes: true })
    .filter((d) => d.isDirectory() && fs.existsSync(path.join(SKILLS_DIR, d.name, "SKILL.md")))
    .map((d) => {
      const text = fs.readFileSync(path.join(SKILLS_DIR, d.name, "SKILL.md"), "utf8");
      const match = text.match(/^description:\s*(.*)$/m);
      const description = (match ? match[1] : "").replace(/^['"]|['"]$/g, "");
      return { name: d.name, summary: description.split(/ - |\. /)[0] };
    })
    .sort((a, b) => a.name.localeCompare(b.name));
}

function resolveAgents(opts) {
  const home = os.homedir();
  let names;
  if (opts.agent) {
    names = opts.agent.split(",").map((s) => s.trim()).filter(Boolean);
    const unknown = names.filter((n) => !AGENTS[n]);
    if (unknown.length) fail(`unknown agent ${unknown.join(", ")}; use ${Object.keys(AGENTS).join(", ")}`);
  } else {
    names = Object.keys(AGENTS).filter((n) => fs.existsSync(path.join(home, AGENTS[n].detect)));
    if (!names.length) fail(`no agent found in ${home}; pass --agent=${Object.keys(AGENTS).join(",")}`);
  }
  const base = opts.project === null ? home : path.resolve(opts.project);
  const targets = new Map(); // several agents can share one folder
  for (const n of names) {
    const dir = path.join(base, opts.project === null ? AGENTS[n].global : AGENTS[n].project);
    if (!targets.has(dir)) targets.set(dir, []);
    targets.get(dir).push(AGENTS[n].label);
  }
  return [...targets].map(([dir, labels]) => ({ dir, labels: labels.join(", ") }));
}

const ownedBy = (dir) => fs.existsSync(path.join(dir, MARKER));

function installedIn(target, known) {
  if (!fs.existsSync(target.dir)) return [];
  return fs.readdirSync(target.dir).filter((n) => known.has(n) && ownedBy(path.join(target.dir, n)));
}

function copySkill(name, target) {
  const dest = path.join(target.dir, name);
  fs.rmSync(dest, { recursive: true, force: true });
  fs.mkdirSync(target.dir, { recursive: true });
  fs.cpSync(path.join(SKILLS_DIR, name), dest, { recursive: true });
  fs.writeFileSync(path.join(dest, MARKER), `${PKG.name}@${PKG.version}\n`);
}

function pickNames(opts, skills, verb) {
  const known = new Set(skills.map((s) => s.name));
  if (opts.all) return skills.map((s) => s.name);
  if (!opts.names.length) fail(`${verb} needs skill names or --all (see 'list')`);
  const unknown = opts.names.filter((n) => !known.has(n));
  if (unknown.length) fail(`unknown skill ${unknown.join(", ")} (see 'list')`);
  return opts.names;
}

function main() {
  const opts = parseArgs(process.argv.slice(2));
  if (opts.version) return console.log(PKG.version);
  if (opts.help || !opts.command) return console.log(HELP);
  const skills = readSkills();
  const known = new Set(skills.map((s) => s.name));

  switch (opts.command) {
    case "list": {
      if (!opts.installed) {
        const width = Math.max(...skills.map((s) => s.name.length));
        for (const s of skills) console.log(`${s.name.padEnd(width)}  ${s.summary}`);
        console.log(`\n${skills.length} skills. Install: android-skills add <skill...> or add --all`);
        return;
      }
      for (const t of resolveAgents(opts)) {
        const names = installedIn(t, known);
        console.log(`${t.labels} (${t.dir}): ${names.length ? names.join(", ") : "none"}`);
      }
      return;
    }
    case "add": {
      const names = pickNames(opts, skills, "add");
      for (const t of resolveAgents(opts)) {
        const done = [];
        for (const n of names) {
          const dest = path.join(t.dir, n);
          if (fs.existsSync(dest) && !ownedBy(dest) && !opts.force) {
            console.warn(`skip ${n}: ${dest} exists and was not installed by android-skills (--force to overwrite)`);
            continue;
          }
          copySkill(n, t);
          done.push(n);
        }
        console.log(`${t.labels}: added ${done.length} skill(s) to ${t.dir}`);
      }
      return;
    }
    case "update": {
      for (const t of resolveAgents(opts)) {
        const installed = installedIn(t, known);
        const names = opts.names.length ? pickNames(opts, skills, "update") : installed;
        const todo = names.filter((n) => installed.includes(n));
        todo.forEach((n) => copySkill(n, t));
        console.log(`${t.labels}: updated ${todo.length} skill(s) in ${t.dir}`);
      }
      return;
    }
    case "remove": {
      const names = pickNames(opts, skills, "remove");
      for (const t of resolveAgents(opts)) {
        const todo = names.filter((n) => installedIn(t, known).includes(n));
        todo.forEach((n) => fs.rmSync(path.join(t.dir, n), { recursive: true, force: true }));
        console.log(`${t.labels}: removed ${todo.length} skill(s) from ${t.dir}`);
      }
      return;
    }
    default:
      fail(`unknown command '${opts.command}'; run with --help`);
  }
}

main();
