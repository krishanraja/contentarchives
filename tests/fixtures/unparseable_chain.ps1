# A FIXTURE, not a chain. It is here to be REFUSED.
#
# This is the real shape that cost a cycle on 2026-09-16: a bash heredoc inside a
# PowerShell file. PowerShell rejects an unparseable file whole, so nothing ran -
# no answers recorded, no merge, no rebuild - while the log stayed empty and the
# only evidence was a ParserError in a stderr file nobody was watching, which
# reads as "still going" for several minutes (learning 53).
#
# guards/arm.ps1 now parses a chain before registering it as a scheduled task, so
# a chain that cannot run is refused while somebody is watching rather than at
# 2am. tests/test_arm_parse.ps1 arms THIS file and asserts the refusal.
#
# Do not "fix" it. Its whole value is that it does not parse.

python -u - << 'PY'
print('hi')
PY
