#!/usr/bin/env node
/**
 * guard-profile-root.mjs
 *
 * Enforces the file-routing card: NEVER write loose files into C:\Users\krish root.
 * Blocks Write/Edit and common Bash creation verbs whose target lands directly in
 * the profile root, and tells the caller where the file actually belongs.
 *
 * Routing (first match wins):
 *   1. code / repo / build artifact  -> C:\Users\krish\dev\<venture>\
 *   2. AI-training corpus            -> C:\Users\krish\dev\<venture>\_corpus\
 *   3. personal                      -> G:\My Drive\Personal\...
 *   4. scratch / QA / temp / audits  -> C:\Users\krish\.scratch\
 *   5. cross-venture timeless IP     -> G:\My Drive\Ventures\_Knowledge\<sub>\
 *   6. single-venture deliverable    -> G:\My Drive\Ventures\Active\<Venture>\0X_*\
 */

import path from 'node:path';

// Derived from the environment so this file is portable across machines.
const ROOT = (process.env.USERPROFILE || process.env.HOME || '')
  .replace(/\//g, '\\').replace(/\\+$/, '').toLowerCase();

// Directories that legitimately live at the profile root.
const ALLOWED_BASENAMES = new Set([
  'appdata', 'application data', 'local settings',
  'desktop', 'documents', 'downloads', 'pictures', 'music', 'videos',
  'my documents', 'onedrive', 'favorites', 'links', 'contacts', 'searches',
  'saved games', '3d objects', 'nethood', 'printhood', 'recent', 'sendto',
  'templates', 'start menu', 'cookies', 'crossdevice', 'muse hub', 'scoop',
  'dev', 'ntuser.ini', 'agents.md', 'skills-lock.json', 'desktop.ini',
]);

const GUIDANCE = [
  'BLOCKED by the file-routing card: never write loose files into C:\\Users\\krish root.',
  '',
  'Route it instead (first match wins):',
  '  1. code / repo / build artifact -> C:\\Users\\krish\\dev\\<venture>\\',
  '  2. AI-training corpus           -> C:\\Users\\krish\\dev\\<venture>\\_corpus\\',
  '  3. personal (wealth/legal/family/media) -> G:\\My Drive\\Personal\\...',
  '  4. scratch / QA output / screenshots / temp / one-off audits -> C:\\Users\\krish\\.scratch\\',
  '  5. cross-venture timeless IP    -> G:\\My Drive\\Ventures\\_Knowledge\\<sub>\\',
  '  6. single-venture deliverable   -> G:\\My Drive\\Ventures\\Active\\<Venture>\\0X_*\\',
  '  7. unsure -> ask; never dump at root.',
  '',
  'Ventures: Mindmake | Mindmake-OS | Fractionl (dev\\ mirrors Ventures\\Active\\).',
].join('\n');

/** True when `p` names something created *directly* in the profile root. */
function isProfileRootTarget(p, cwd) {
  if (!p) return false;
  let abs = p.replace(/^~(?=[\\/]|$)/, ROOT).replace(/\//g, '\\');
  if (!path.win32.isAbsolute(abs)) {
    if (!cwd) return false;
    abs = path.win32.resolve(cwd.replace(/\//g, '\\'), abs);
  }
  abs = path.win32.normalize(abs);

  const parent = path.win32.dirname(abs).toLowerCase().replace(/\\+$/, '');
  if (parent !== ROOT) return false;

  const base = path.win32.basename(abs).toLowerCase();
  if (!base || base.startsWith('.')) return false;          // dotfiles/dot-dirs are fine
  if (base.startsWith('ntuser')) return false;              // registry hives
  if (ALLOWED_BASENAMES.has(base)) return false;
  return true;
}

/** True when the session's working directory IS the profile root. */
function isCwdProfileRoot(cwd) {
  if (!cwd) return false;
  return cwd.replace(/\//g, '\\').replace(/\\+$/, '').toLowerCase() === ROOT;
}

function deny(reason) {
  process.stdout.write(JSON.stringify({
    hookSpecificOutput: {
      hookEventName: 'PreToolUse',
      permissionDecision: 'deny',
      permissionDecisionReason: `${GUIDANCE}\n\nOffending target: ${reason}`,
    },
  }));
  process.exit(0);
}

function main(raw) {
  let input;
  try { input = JSON.parse(raw); } catch { process.exit(0); }

  const tool = input.tool_name || '';
  const ti = input.tool_input || {};
  const cwd = input.cwd || input.working_directory || '';

  if (tool === 'Write' || tool === 'Edit' || tool === 'NotebookEdit') {
    const fp = ti.file_path || ti.notebook_path;
    // Editing an existing root file is allowed; creating a new one is not.
    if (tool === 'Write' && isProfileRootTarget(fp, cwd)) deny(fp);
    process.exit(0);
  }

  if (tool === 'Bash') {
    const cmd = String(ti.command || '');

    // --- cwd guard -------------------------------------------------------
    // A script run FROM the profile root writes its output there relative to
    // cwd, which no command-text inspection can catch. This is how the 109
    // loose files (speakers_part*.json, sn_grp*.json, ...) actually landed.
    // So: refuse to run anything file-producing while sitting in the root.
    if (isCwdProfileRoot(cwd)) {
      const producer = /(?:^|[\s;&|(])(?:python3?|py|node|npm|npx|pnpm|yarn|bun|deno|tsx|ts-node|pytest|playwright|jupyter|pip3?|cargo|go|dotnet|java|make|sh|bash|pwsh|powershell)\b/i;
      const fetcher = /\b(?:curl|wget|Invoke-WebRequest|iwr)\b/i;
      if (producer.test(cmd) || fetcher.test(cmd)) {
        deny(
          `command runs from cwd = C:\\Users\\krish (the profile root), so anything ` +
          `it writes relative to cwd lands there.\n` +
          `Fix: cd into the right destination first (dev\\<venture>\\... or .scratch\\), ` +
          `then run the command.\nCommand: ${cmd.split('\n')[0].slice(0, 160)}`
        );
      }
    }

    // git clone whose destination lands in the profile root
    const clone = cmd.match(/\bgit\s+clone\b[^\n;&|]*/i);
    if (clone) {
      const toks = clone[0].split(/\s+/).slice(2).filter(t => !t.startsWith('-'));
      const dest = toks.length >= 2 ? toks[toks.length - 1] : null;
      if (dest && isProfileRootTarget(dest, cwd)) deny(`git clone -> ${dest}`);
      // bare `git clone <url>` while sitting in the profile root
      if (!dest && isCwdProfileRoot(cwd)) {
        deny('git clone into C:\\Users\\krish (cwd is the profile root)');
      }
    }

    // Strip heredoc bodies before scanning: their content is DATA (test
    // fixtures, docs, generated files) and routinely mentions root paths
    // that are never actually written there.
    const scan = cmd.replace(
      /<<-?\s*(['"]?)([A-Za-z_][A-Za-z0-9_]*)\1[\s\S]*?^\s*\2\s*$/gm,
      '<<HEREDOC_BODY_STRIPPED'
    );

    // creation verbs and shell redirections aimed at the profile root
    const patterns = [
      /\b(?:touch|mkdir)\s+(?:-\S+\s+)*("[^"]+"|'[^']+'|\S+)/gi,
      /\b(?:cp|mv)\s+(?:-\S+\s+)*\S+\s+("[^"]+"|'[^']+'|\S+)/gi,
      />>?\s*("[^"]+"|'[^']+'|[^\s;&|>]+)/g,
    ];
    for (const re of patterns) {
      for (const m of scan.matchAll(re)) {
        const target = m[1].replace(/^['"]|['"]$/g, '');
        if (isProfileRootTarget(target, cwd)) deny(target);
      }
    }
  }

  process.exit(0);
}

let buf = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', d => { buf += d; });
process.stdin.on('end', () => main(buf));
