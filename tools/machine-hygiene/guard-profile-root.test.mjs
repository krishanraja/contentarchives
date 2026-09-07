import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
const B = String.fromCharCode(92), j = (...p) => p.join(B);
const ROOT = (process.env.USERPROFILE || process.env.HOME).replace(RegExp('/','g'), B);
const REPO = j(ROOT, 'dev', 'mindmaker', 'mm-ctrl');
const HOOK = process.env.GUARD_HOOK
  || fileURLToPath(new URL('./guard-profile-root.mjs', import.meta.url));
const rootFwd = ROOT.split(B).join('/');

const cases = [
  // --- cwd guard: the vector that actually caused the sprawl ---
  [true,  'python script, cwd=ROOT (real sprawl vector)', { tool_name: 'Bash', tool_input: { command: 'python score_wave2.py' }, cwd: ROOT }],
  [true,  'node script, cwd=ROOT',            { tool_name: 'Bash', tool_input: { command: 'node sn_build.mjs' }, cwd: ROOT }],
  [true,  'npm install, cwd=ROOT',            { tool_name: 'Bash', tool_input: { command: 'npm install' }, cwd: ROOT }],
  [true,  'curl download, cwd=ROOT',          { tool_name: 'Bash', tool_input: { command: 'curl -o out.json https://x' }, cwd: ROOT }],
  [false, 'ls at ROOT still fine',            { tool_name: 'Bash', tool_input: { command: 'ls -la' }, cwd: ROOT }],
  [false, 'git status at ROOT still fine',    { tool_name: 'Bash', tool_input: { command: 'git status' }, cwd: ROOT }],
  [false, 'cat at ROOT still fine',           { tool_name: 'Bash', tool_input: { command: 'cat .gitconfig' }, cwd: ROOT }],
  [false, 'python from a real repo cwd',      { tool_name: 'Bash', tool_input: { command: 'python score.py' }, cwd: REPO }],
  [false, 'npm install from a real repo cwd', { tool_name: 'Bash', tool_input: { command: 'npm install' }, cwd: REPO }],

  // --- heredoc bodies are DATA, not writes (regression guard) ---
  [false, 'root path inside heredoc body',    { tool_name: 'Bash', tool_input: { command: "cat > /tmp/t.txt <<'EOF'\necho hi > " + rootFwd + "/out.json\nEOF" } }],
  [true,  'real redirect alongside heredoc',  { tool_name: 'Bash', tool_input: { command: "cat <<'EOF'\nharmless text\nEOF\necho x > " + rootFwd + "/real.json" } }],

  // --- original suite, must not regress ---
  [true,  'Write <root>/stray.py',            { tool_name: 'Write', tool_input: { file_path: j(ROOT, 'stray.py') } }],
  [true,  'git clone -> root',                { tool_name: 'Bash', tool_input: { command: 'git clone https://x/y.git ' + j(ROOT, 'newrepo') } }],
  [true,  'touch at root',                    { tool_name: 'Bash', tool_input: { command: 'touch ' + j(ROOT, 'notes.txt') } }],
  [true,  'redirect > root',                  { tool_name: 'Bash', tool_input: { command: 'echo hi > ' + rootFwd + '/out.json' } }],
  [false, 'Write into dev/',                  { tool_name: 'Write', tool_input: { file_path: j(REPO, 'src', 'a.ts') } }],
  [false, 'Write into .scratch/',             { tool_name: 'Write', tool_input: { file_path: j(ROOT, '.scratch', 'shot.png') } }],
  [false, 'Write .claude/settings.json',      { tool_name: 'Write', tool_input: { file_path: j(ROOT, '.claude', 'settings.json') } }],
  [false, 'Write into Documents/',            { tool_name: 'Write', tool_input: { file_path: j(ROOT, 'Documents', 'n.md') } }],
  [false, 'Edit existing root AGENTS.md',     { tool_name: 'Edit', tool_input: { file_path: j(ROOT, 'AGENTS.md') } }],
  [false, 'git clone, cwd=dev/labs',          { tool_name: 'Bash', tool_input: { command: 'git clone https://x/y.git' }, cwd: j(ROOT, 'dev', 'labs') }],
  [false, 'ordinary command, no cwd',         { tool_name: 'Bash', tool_input: { command: 'npm test' } }],
  [false, 'mkdir inside dev/',                { tool_name: 'Bash', tool_input: { command: 'mkdir -p ' + j(ROOT, 'dev', 'fractionl', 'x') } }],
  [false, 'redirect elsewhere',               { tool_name: 'Bash', tool_input: { command: 'echo x > /tmp/f' } }],
];

let fail = 0;
for (const [want, label, payload] of cases) {
  const out = execFileSync('node', [HOOK], { input: JSON.stringify(payload), encoding: 'utf8' });
  const got = out.includes('"deny"'), ok = got === want;
  if (!ok) fail++;
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${want ? 'block' : 'allow'}  ${label}${ok ? '' : `   <-- got ${got ? 'BLOCKED' : 'allowed'}`}`);
}
console.log(fail ? `\n${fail} FAILURE(S)` : `\nall ${cases.length} cases pass`);
process.exit(fail ? 1 : 0);
