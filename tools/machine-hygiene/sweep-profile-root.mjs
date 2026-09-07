#!/usr/bin/env node
/**
 * sweep-profile-root.mjs — janitor backstop for the file-routing card.
 *
 * The PreToolUse guard only sees Claude Code's own tool calls. Anything else
 * (Codex, Cursor, an installer, a stray script) can still drop files into
 * C:\Users\krish. This sweeps them into .scratch\root-strays\<date>\ and logs
 * what it moved.
 *
 *   node sweep-profile-root.mjs            # report only (default, safe)
 *   node sweep-profile-root.mjs --apply    # actually move the strays
 */

import fs from 'node:fs';
import path from 'node:path';

// Derived from the environment so this file is portable across machines.
const ROOT = (process.env.USERPROFILE || process.env.HOME || '')
  .replace(/\//g, '\\').replace(/\\+$/, '');
const APPLY = process.argv.includes('--apply');
const STAMP = new Date().toISOString().slice(0, 10);
const QUARANTINE = path.win32.join(ROOT, '.scratch', 'root-strays', STAMP);
const LOG = path.win32.join(ROOT, '.scratch', 'root-sweep.log');

// Everything that legitimately lives at the profile root.
const KEEP = new Set([
  'appdata', 'application data', 'local settings',
  'desktop', 'documents', 'downloads', 'pictures', 'music', 'videos',
  'my documents', 'onedrive', 'favorites', 'links', 'contacts', 'searches',
  'saved games', '3d objects', 'nethood', 'printhood', 'recent', 'sendto',
  'templates', 'start menu', 'cookies', 'crossdevice', 'muse hub', 'scoop',
  'dev', 'claude',
  'ntuser.ini', 'agents.md', 'skills-lock.json', 'desktop.ini',
]);

const isKept = (name) => {
  const n = name.toLowerCase();
  return n.startsWith('.') || n.startsWith('ntuser') || KEEP.has(n);
};

let entries;
try {
  entries = fs.readdirSync(ROOT, { withFileTypes: true });
} catch (e) {
  console.error('cannot read ' + ROOT + ': ' + e.message);
  process.exit(1);
}

const strays = entries.filter((e) => !isKept(e.name));

if (strays.length === 0) {
  console.log('Profile root is clean - no strays.');
  process.exit(0);
}

console.log(`${strays.length} stray item(s) in ${ROOT}:`);
for (const s of strays) console.log(`   ${s.isDirectory() ? '[dir] ' : '[file]'} ${s.name}`);

if (!APPLY) {
  console.log('\nReport only. Re-run with --apply to quarantine them into:');
  console.log('   ' + QUARANTINE);
  process.exit(strays.length ? 2 : 0);
}

fs.mkdirSync(QUARANTINE, { recursive: true });
const moved = [];
for (const s of strays) {
  const from = path.win32.join(ROOT, s.name);
  const to = path.win32.join(QUARANTINE, s.name);
  try {
    fs.renameSync(from, to);
    moved.push(s.name);
    console.log('   moved -> ' + s.name);
  } catch (e) {
    console.error('   FAILED ' + s.name + ': ' + e.message);
  }
}

if (moved.length) {
  const line = `${new Date().toISOString()}  moved ${moved.length} -> ${QUARANTINE}\n` +
    moved.map((m) => `    ${m}\n`).join('');
  try { fs.appendFileSync(LOG, line); } catch {}
  console.log(`\nQuarantined ${moved.length} item(s). Log: ${LOG}`);
  console.log('Nothing deleted - review and file them per the routing card.');
}
