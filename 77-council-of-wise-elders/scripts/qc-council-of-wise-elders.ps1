# Council of Wise Elders (77): bundled QC gate, PowerShell counterpart.
# Core offline checks for Windows boxes: layout presence, frontmatter
# name, version agreement, roster and exact labels from
# config/advisors.json, JSON validity, and no state files in the folder.
# Exit 0 = pass, 1 = fail. This script never modifies anything.

$ErrorActionPreference = "Continue"
$SkillDir = Split-Path -Parent $PSScriptRoot
$script:Fail = 0

function Pass($m) { Write-Host "PASS $m" }
function Fail($m) { Write-Host "FAIL $m"; $script:Fail = 1 }

Write-Host "== Council of Wise Elders QC (PowerShell) =="
Write-Host "skill dir: $SkillDir"

$required = @(
  "SKILL.md", "INSTALL.md", "INSTRUCTIONS.md", "EXAMPLES.md",
  "CORE_UPDATES.md", "QC.md", "CHANGELOG.md", "PREREQS.json",
  "version", "skill-version.txt", "manifest.json",
  "config\defaults.json", "config\advisors.json",
  "assets\portrait-manifest.json"
)
$missing = @($required | Where-Object { -not (Test-Path (Join-Path $SkillDir $_)) })
if ($missing.Count -eq 0) { Pass "layout inventory (core files)" }
else { Fail "missing files: $($missing -join ', ')" }

$skillMd = Get-Content (Join-Path $SkillDir "SKILL.md") -Raw
if ($skillMd -match "(?m)^name:\s*council-of-wise-elders\s*$") {
  Pass "frontmatter name is council-of-wise-elders"
} else { Fail "frontmatter name is not council-of-wise-elders" }

$fmVersion = $null
if ($skillMd -match "(?m)^version:\s*(\S+)\s*$") { $fmVersion = $Matches[1] }
$vFile = (Get-Content (Join-Path $SkillDir "version") -Raw).Trim() -replace "^v", ""
$vSkill = (Get-Content (Join-Path $SkillDir "skill-version.txt") -Raw).Trim() -replace "^v", ""
if ($vFile -and $vFile -eq $vSkill -and $vFile -eq $fmVersion) {
  Pass "versions agree: $vFile"
} else { Fail "version disagreement: version=$vFile skill-version.txt=$vSkill frontmatter=$fmVersion" }

try {
  $cfg = Get-Content (Join-Path $SkillDir "config\advisors.json") -Raw | ConvertFrom-Json
  $expected = @("simon-sinek","td-jakes","oprah-winfrey","tiffany-aliche",
    "russell-brunson","michelle-obama","brene-brown","dennis-kimbro","les-brown")
  $ids = @($cfg.seats | ForEach-Object { $_.seat_id })
  if (($ids -join ",") -eq ($expected -join ",")) { Pass "roster is the fixed nine seats in order" }
  else { Fail "roster mismatch: $($ids -join ', ')" }
  $labelsOk = $true
  foreach ($seat in $cfg.seats) {
    $want = "AI perspective inspired by the published work of $($seat.name). Not the individual and not an endorsement."
    if ($seat.profile_label -ne $want) { $labelsOk = $false; Fail "label mismatch for $($seat.seat_id)" }
  }
  if ($labelsOk) { Pass "all nine profile labels exact" }
} catch { Fail "config\advisors.json does not parse: $($_.Exception.Message)" }

$jsonFiles = Get-ChildItem -Path $SkillDir -Recurse -Filter *.json -File
$jsonBad = 0
foreach ($f in $jsonFiles) {
  try { Get-Content $f.FullName -Raw | ConvertFrom-Json | Out-Null }
  catch { $jsonBad += 1; Fail "JSON parse: $($f.FullName): $($_.Exception.Message)" }
}
if ($jsonBad -eq 0) { Pass "JSON files parsed: $($jsonFiles.Count)" }

$state = Get-ChildItem -Path $SkillDir -Recurse -File |
  Where-Object { $_.Extension -in @(".sqlite", ".sqlite3", ".db") }
if ($state.Count -eq 0) { Pass "no state files inside the skill folder" }
else { Fail "state files inside skill folder: $($state.FullName -join ', ')" }

if ($script:Fail -eq 0) { Write-Host "QC: PASS" } else { Write-Host "QC: FAIL" }
exit $script:Fail
