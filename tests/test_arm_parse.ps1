<#
    arm.ps1 must REFUSE a chain that cannot parse, before registering anything.

        pwsh -NoProfile -File tests\test_arm_parse.ps1

    WHY THIS EXISTS

    On 2026-09-16 a pipeline with a bash heredoc in it died before its first
    step. PowerShell rejects an unparseable file whole, so nothing ran: no
    answers recorded, no merge, no rebuild. The log stayed empty and the only
    evidence was a ParserError in a stderr file nobody was watching, which reads
    as "still going" for several minutes (learning 53).

    arm.ps1 now parses a chain before registering it as a scheduled task, so a
    chain that cannot run is refused while somebody is watching rather than at
    2am. That guard had no test: it was written, reasoned about, and believed.
    A guard nobody has watched refusing is indistinguishable from one that
    cannot refuse (learning 44).

    The fixture is tests/fixtures/unparseable_chain.ps1 and it is not to be
    fixed - its whole value is that it does not parse.

    SAFETY: arm.ps1 throws on the parse BEFORE Register-ScheduledTask or
    Stop-ChainWorkers, so this leaves no task behind and kills nothing. The last
    check asserts exactly that rather than assuming it.
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Continue'

$here    = Split-Path -Parent $PSCommandPath
$repo    = Split-Path -Parent $here
$arm     = Join-Path $repo 'guards\arm.ps1'
$fixture = Join-Path $here  'fixtures\unparseable_chain.ps1'
$task    = 'contentarchives-test-arm-parse'

$script:FAILURES = @()
function Check($name, $got, $want) {
    $ok = $got -eq $want
    "  {0,-58} {1}" -f $name, $(if ($ok) { 'OK' } else { "FAIL got=$got want=$want" }) | Write-Host
    if (-not $ok) { $script:FAILURES += $name }
}

Write-Host ''
Write-Host '1. the fixture really is unparseable (or this test proves nothing)'
$perr = $null
[void][System.Management.Automation.Language.Parser]::ParseFile($fixture, [ref]$null, [ref]$perr)
Check 'the fixture does not parse' ($null -ne $perr -and $perr.Count -gt 0) $true

Write-Host ''
Write-Host '2. a real chain in the repo DOES parse (the detector is not just saying no)'
$ok = $null
[void][System.Management.Automation.Language.Parser]::ParseFile(
    (Join-Path $repo 'stages\07_people\chain_rounds.ps1'), [ref]$null, [ref]$ok)
Check 'chain_rounds.ps1 parses' ($null -eq $ok -or $ok.Count -eq 0) $true

Write-Host ''
Write-Host '3. arm.ps1 refuses to arm it, and says so'
# Copy the fixture in beside the chains, because arm.ps1 resolves -Chain by name.
$staged = Join-Path $repo 'stages\07_people\__test_unparseable.ps1'
Copy-Item $fixture $staged -Force
try {
    $out = & pwsh -NoProfile -File $arm -Chain '__test_unparseable.ps1' -TaskName $task 2>&1 | Out-String
    $code = $LASTEXITCODE
    Check 'it exits non-zero'                 ($code -ne 0) $true
    Check 'it says REFUSING TO ARM'           ($out -match 'REFUSING TO ARM') $true
    Check 'it counts the parse errors'        ($out -match 'parse error') $true
    Check 'it names the chain'                ($out -match '__test_unparseable') $true

    Write-Host ''
    Write-Host '4. and it registered NOTHING - the refusal came first'
    $t = Get-ScheduledTask -TaskName $task -ErrorAction SilentlyContinue
    Check 'no scheduled task was left behind' ($null -eq $t) $true
} finally {
    Remove-Item $staged -Force -ErrorAction SilentlyContinue
    Get-ScheduledTask -TaskName $task -ErrorAction SilentlyContinue | ForEach-Object {
        Unregister-ScheduledTask -TaskName $task -Confirm:$false -ErrorAction SilentlyContinue
    }
}

Write-Host ''
if ($script:FAILURES.Count) {
    Write-Host ("{0} FAILED: {1}" -f $script:FAILURES.Count, ($script:FAILURES -join ', '))
    exit 1
}
Write-Host 'all checks passed'
exit 0
