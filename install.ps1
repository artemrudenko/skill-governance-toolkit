#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Interactive one-command installer for the Skill Governance Toolkit.

.DESCRIPTION
    Asks which AI host and scope, auto-detects existing installs and reinstalls
    in --upgrade mode (cleans renamed/removed files). Works on Windows, macOS,
    and Linux with PowerShell 7+ (pwsh).

    On Unix it delegates to install.sh; on Windows it performs the copy
    natively with Copy-Item.

    Skill-subset selection (since 1.8.0) is supported via -Category / -Tier /
    -Skill / -Interactive. These mirror the bash installer's --category /
    --tier / --skill / --interactive flags and use the same filter_skills.py
    helper, so the resolved subset is identical on Unix and Windows.

.PARAMETER Force
    Wipe target dirs before copying (most aggressive reinstall).

.PARAMETER DryRun
    Resolve filters and target paths, print the install plan, then exit
    without writing files.

.PARAMETER YesDefault
    Non-interactive: install Claude Code to project scope. Useful for CI.

.PARAMETER Category
    Comma-separated list of skill categories to install. See
    docs/skill-authoring-standard.md for the closed vocab.

.PARAMETER Tier
    Comma-separated list of skill tiers to install. Default: stable,preview.
    Add experimental or internal to include skills with those tiers.

.PARAMETER Skill
    Comma-separated explicit skill names. Overrides -Category and -Tier.

.PARAMETER Interactive
    Show a menu of available categories with skill counts. Requires a host
    console (interactive PowerShell session).

.EXAMPLE
    ./install.ps1
    ./install.ps1 -Force
    ./install.ps1 -DryRun
    ./install.ps1 -YesDefault
    ./install.ps1 -Category discovery
    ./install.ps1 -Tier stable -Skill skill-find,skill-evaluate
    ./install.ps1 -Interactive
#>

[CmdletBinding()]
param(
    [switch]$Force,
    [switch]$DryRun,
    [switch]$YesDefault,
    [string]$Category = '',
    [string]$Tier    = '',
    [string]$Skill   = '',
    [switch]$Interactive,
    # Where YOUR project lives (project scope only). Mirrors bash
    # --target-project=PATH. Default: current working directory — NOT the
    # toolkit repo. Lets a Windows user install into their own app the same
    # way `cd ~/app; .../install.ps1` works under bash (H1).
    [string]$TargetProject = ''
)

$ErrorActionPreference = 'Stop'
$RepoRoot = $PSScriptRoot

# ── Delegate to bash on Unix (single source of truth) ─────────────────────────
if (-not $IsWindows) {
    $bashInstaller = Join-Path $RepoRoot 'install.sh'
    if (-not (Test-Path $bashInstaller)) {
        throw "Expected $bashInstaller to exist on non-Windows."
    }
    $bashArgs = @()
    if ($Force)                                  { $bashArgs += '--force' }
    if ($DryRun)                                 { $bashArgs += '--dry-run' }
    if ($YesDefault)                             { $bashArgs += '--yes-default' }
    if (-not [string]::IsNullOrWhiteSpace($Category)) { $bashArgs += @('--category', $Category) }
    if (-not [string]::IsNullOrWhiteSpace($Tier))     { $bashArgs += @('--tier',     $Tier) }
    if (-not [string]::IsNullOrWhiteSpace($Skill))    { $bashArgs += @('--skill',    $Skill) }
    if ($Interactive)                            { $bashArgs += '--interactive' }
    if (-not [string]::IsNullOrWhiteSpace($TargetProject)) { $bashArgs += "--target-project=$TargetProject" }
    & bash $bashInstaller @bashArgs
    exit $LASTEXITCODE
}

# ── Windows-native install logic ───────────────────────────────────────────────

# Resolve Python — required for filter_skills.py / marker_block.py /
# generate_subset_agents_md.py. Without it, subset install can't work
# (we'd have to re-implement YAML parsing in PowerShell).
$pythonCmd = if (Get-Command python3 -ErrorAction SilentlyContinue) { 'python3' }
             elseif (Get-Command python -ErrorAction SilentlyContinue) { 'python' }
             else { $null }
if (-not $pythonCmd) {
    throw "Python 3.8+ required on Windows for selective install / marker-block management. Install python.org Python or rerun on WSL where install.sh is delegated to bash."
}

$HostOptions = @(
    @{ Key='1'; Name='Claude Code';      Dir='.claude';  Kind='claude'  },
    @{ Key='2'; Name='GitHub Copilot';   Dir='.github';  Kind='copilot' },
    @{ Key='3'; Name='OpenAI Codex CLI'; Dir='.codex';   Kind='codex'   },
    @{ Key='4'; Name='Google Gemini';    Dir='.gemini';  Kind='gemini'  },
    @{ Key='5'; Name='Cursor';           Dir='.cursor';  Kind='cursor'  },
    @{ Key='6'; Name='All five above';   Dir='';         Kind='all'     }
)

if ($YesDefault) {
    $hostChoice = '1'
    $scopeChoice = '2'
}
else {
    Write-Host "Skill Governance Toolkit — installer`n"
    Write-Host "Which AI host do you want to install for?"
    foreach ($o in $HostOptions) { Write-Host ("  {0}) {1}" -f $o.Key, $o.Name) }
    $hostChoice = Read-Host "Choice [1-6] (default 1)"
    if ([string]::IsNullOrWhiteSpace($hostChoice)) { $hostChoice = '1' }

    Write-Host "`nWhere should it be installed?"
    Write-Host "  1) Global  — `$HOME\<host>\    (affects all projects)"
    Write-Host "  2) Project — .\<host>\         (this project only)"
    $scopeChoice = Read-Host "Choice [1-2] (default 2)"
    if ([string]::IsNullOrWhiteSpace($scopeChoice)) { $scopeChoice = '2' }
}

$selected = $HostOptions | Where-Object { $_.Key -eq $hostChoice }
if (-not $selected) { throw "Invalid host choice: $hostChoice" }

$targets = if ($selected.Kind -eq 'all') {
    $HostOptions | Where-Object { $_.Kind -ne 'all' }
} else {
    @($selected)
}

# Project root = where YOUR project lives. Mirrors bash TARGET_PROJECT:
# -TargetProject if given, otherwise the current working directory (NOT the
# toolkit repo). This is what makes `cd ~/app; .../install.ps1` install into
# the app, exactly like bash (H1).
$projectRoot = if (-not [string]::IsNullOrWhiteSpace($TargetProject)) {
    (Resolve-Path $TargetProject).Path
} else {
    (Get-Location).Path
}

$scopePrefix = switch ($scopeChoice) {
    '1' { $HOME }
    '2' { $projectRoot }
    default { throw "Invalid scope choice: $scopeChoice" }
}

# Self-install guard: project scope whose target IS the toolkit repo itself.
# Mirrors bash `[[ "$SOURCE" -ef "$TARGET_PROJECT" ]]`. When true, the installer
# must NOT upsert marker blocks into the toolkit's own AGENTS.md/CLAUDE.md/… nor
# create .{host}/ dupes inside the source tree (H2). Compare resolved paths.
$selfInstall = ($scopeChoice -eq '2') -and `
    ((Resolve-Path $projectRoot).Path.TrimEnd('\','/') -eq (Resolve-Path $RepoRoot).Path.TrimEnd('\','/'))
if ($selfInstall) {
    Write-Host "── Project target IS the toolkit's own dir — marker-block upsert and per-host dupes will be skipped (self-pollution guard) ──"
    Write-Host "  · For a real install, pass -TargetProject C:\path\to\your\repo"
}

# ── Detect existing install ────────────────────────────────────────────────────
$existing = $false
foreach ($t in $targets) {
    $dest = Join-Path $scopePrefix $t.Dir
    if ((Test-Path (Join-Path $dest 'skills')) -or
        (Test-Path (Join-Path $dest 'copilot-instructions.md'))) {
        $existing = $true
        break
    }
}

$mode = if ($Force) { 'force' }
        elseif ($existing) { 'upgrade' }
        else { 'fresh' }

# ── Resolve skill subset via filter_skills.py ─────────────────────────────────
# Mirror of resolve_skill_subset() in scripts/install.sh — same input flags,
# same filter_skills.py helper, same output (list of skill names + filtered
# INDEX.jsonl). Default tier = stable,preview.

$tierFilter = if ([string]::IsNullOrWhiteSpace($Tier)) { 'stable,preview' } else { $Tier }
$indexPath  = Join-Path $RepoRoot 'skills\INDEX.jsonl'
if (-not (Test-Path $indexPath)) {
    throw "skills/INDEX.jsonl not found at $indexPath. Run: python3 scripts/build_index.py"
}

if ($Interactive) {
    if (-not [Environment]::UserInteractive) {
        throw "-Interactive requires an interactive PowerShell session."
    }
    Write-Host "── Interactive: pick categories ──"
    $catLines = & $pythonCmd -X utf8 (Join-Path $RepoRoot 'scripts\filter_skills.py') --index $indexPath --list-categories
    $categories = @()
    $i = 1
    foreach ($line in $catLines) {
        $parts = $line -split "`t"
        if ($parts.Length -ge 3 -and $parts[0] -eq 'category') {
            Write-Host ("  {0}) {1,-12} ({2} skills)" -f $i, $parts[1], $parts[2])
            $categories += $parts[1]
            $i++
        }
    }
    Write-Host ""
    Write-Host "Tier distribution:"
    foreach ($line in $catLines) {
        $parts = $line -split "`t"
        if ($parts.Length -ge 3 -and $parts[0] -eq 'tier') {
            Write-Host ("  · {0,-14} {1} skills" -f $parts[1], $parts[2])
        }
    }
    $sel = Read-Host "`nSelect categories (comma-separated numbers, blank = all stable+preview)"
    if (-not [string]::IsNullOrWhiteSpace($sel)) {
        $chosen = @()
        foreach ($n in ($sel -split ',')) {
            $n = $n.Trim()
            if ($n -match '^\d+$' -and [int]$n -ge 1 -and [int]$n -le $categories.Count) {
                $chosen += $categories[[int]$n - 1]
            }
        }
        if ($chosen.Count -gt 0) {
            $Category = $chosen -join ','
            Write-Host "  → -Category set to: $Category"
        }
    }
}

$filterArgs = @('--index', $indexPath, '--tier', $tierFilter)
if (-not [string]::IsNullOrWhiteSpace($Category)) { $filterArgs += @('--category', $Category) }
if (-not [string]::IsNullOrWhiteSpace($Skill))    { $filterArgs += @('--skill',    $Skill) }

$selectedSkills = @((& $pythonCmd -X utf8 (Join-Path $RepoRoot 'scripts\filter_skills.py') @filterArgs) `
    | Where-Object { $_ -and $_.Trim() })
if (-not $selectedSkills -or $selectedSkills.Count -eq 0) {
    throw "No skills match the filter (Category=$Category Tier=$tierFilter Skill=$Skill). Inspect: $pythonCmd scripts/filter_skills.py --index skills/INDEX.jsonl --list-categories"
}

Write-Host "`nPlan:"
Write-Host "  host:    $($selected.Name)"
Write-Host "  scope:   $scopePrefix"
Write-Host "  mode:    $mode"
Write-Host "  filter:  category=$Category tier=$tierFilter skill=$Skill"
Write-Host "  install ($($selectedSkills.Count) skills): $($selectedSkills -join ', ')`n"

if ($DryRun) {
    Write-Host "── Dry-run install plan (no files will be written) ──"
    Write-Host "  source: $RepoRoot"
    Write-Host "  scope:  $scopePrefix"
    Write-Host "  targets:"
    foreach ($t in $targets) {
        Write-Host ("    · {0} -> {1}" -f $t.Kind, (Join-Path $scopePrefix $t.Dir))
    }
    if ($scopeChoice -eq '2') {
        $dryKinds = @($targets | ForEach-Object { $_.Kind })
        $rootFiles = @('AGENTS.md (consumer variant)')
        if ($dryKinds -contains 'claude')  { $rootFiles += 'CLAUDE.md' }
        if ($dryKinds -contains 'gemini')  { $rootFiles += 'GEMINI.md' }
        if ($dryKinds -contains 'copilot') { $rootFiles += '.github/copilot-instructions.md' }
        $manifests = @()
        if ($dryKinds -contains 'codex')  { $manifests += '.codex-plugin/' }
        if ($dryKinds -contains 'claude') { $manifests += '.claude-plugin/' }
        if ($dryKinds -contains 'gemini') { $manifests += 'gemini-extension.json' }
        Write-Host "  project root:"
        Write-Host "    · upsert marker blocks in: $($rootFiles -join ', ')"
        Write-Host "    · copy filtered skills/ plus agents/, references/, scripts/, commands/"
        Write-Host "    · copy docs/ with conflict-renaming"
        Write-Host "    · ensure out/ and .skill-state/ entries in .gitignore"
        if ($manifests.Count -gt 0) {
            Write-Host "    · place manifests: $($manifests -join ', ')"
        }
    }
    else {
        Write-Host "  project root: skipped for global scope"
    }
    Write-Host "`nDry run complete."
    exit 0
}

# ── Marker-block helper (Python parity with Bash installer) ──────────────────

function Upsert-MarkerBlock {
    param([string]$Src, [string]$Dest)
    $markerScript = Join-Path $RepoRoot 'scripts\marker_block.py'
    if (-not (Test-Path $markerScript)) {
        Write-Warning "marker_block.py missing — falling back to Copy-Item for $Dest"
        Copy-Item $Src $Dest -Force
        return
    }
    & $pythonCmd -X utf8 $markerScript upsert --file $Dest --src $Src
}

# Consumer AGENTS.md: installs must NOT carry the toolkit-repo prose (the
# self-CI `bash scripts/audit.sh` never ships; «This repository is a
# skill-governance toolkit» misdescribes the user's repo). Mirror of bash
# generate_consumer_agents_md() — always generate; the script also trims the
# skill table to the installed subset and adds a scoped notice when filtered.
function Resolve-AgentsSource {
    param([string[]]$SelectedSkills)
    $genScript = Join-Path $RepoRoot 'scripts\generate_subset_agents_md.py'
    if (-not (Test-Path $genScript)) {
        Write-Warning "generate_subset_agents_md.py missing — using canonical AGENTS.md"
        return (Join-Path $RepoRoot 'AGENTS.md')
    }
    $tmpFile = [System.IO.Path]::GetTempFileName()
    $skillCsv = ($SelectedSkills -join ',')
    $output = & $pythonCmd -X utf8 $genScript (Join-Path $RepoRoot 'AGENTS.md') $skillCsv
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "consumer AGENTS.md generation failed — using canonical AGENTS.md"
        return (Join-Path $RepoRoot 'AGENTS.md')
    }
    Set-Content -Path $tmpFile -Value $output -Encoding UTF8
    Write-Host "  · AGENTS.md prepared for install (consumer variant, $($SelectedSkills.Count) skills)"
    return $tmpFile
}

# Resolved once — used by the root marker block AND per-host runtime copies.
$agentsForInstall = Resolve-AgentsSource -SelectedSkills $selectedSkills
# Host kinds actually selected — root alias files / manifests are written only
# for these (mirror of bash _host_selected()).
$kinds = @($targets | ForEach-Object { $_.Kind })

# Mirror of ensure_gitignore_entries() in scripts/install.sh — keep audit
# outputs (out/) and resumable-run state (.skill-state/) untracked in the
# target repo. Append-if-missing, idempotent; user content never modified.
function Ensure-GitignoreEntries {
    param([string]$ProjectRoot)
    $gi = Join-Path $ProjectRoot '.gitignore'
    $comment = '# skill-governance-toolkit — audit outputs and resumable-run state (keep untracked)'
    $existing = if (Test-Path $gi) { @(Get-Content $gi) } else { @() }
    $missing = @('out/', '.skill-state/') | Where-Object { $existing -notcontains $_ }
    if (-not $missing) { return }
    $lines = @()
    if ($existing -notcontains $comment) { $lines += $comment }
    $lines += $missing
    Add-Content -Path $gi -Value ($lines -join "`n")
    Write-Host "  · .gitignore: ensured $($missing -join ', ')"
}

# ── Ensure project root user-owned files (append-with-markers) ────────────────
# Project scope only, and never when the target is the toolkit's own dir (H2).
# AGENTS.md always (consumer variant); host alias files only for selected hosts.
if ($scopeChoice -eq '2' -and -not $selfInstall) {
    Write-Host "── Ensuring user-owned files at project root (append-with-markers) ──"
    Upsert-MarkerBlock $agentsForInstall (Join-Path $scopePrefix 'AGENTS.md')
    if ($kinds -contains 'claude') {
        Upsert-MarkerBlock (Join-Path $RepoRoot 'CLAUDE.md') (Join-Path $scopePrefix 'CLAUDE.md')
    }
    if ($kinds -contains 'gemini') {
        Upsert-MarkerBlock (Join-Path $RepoRoot 'GEMINI.md') (Join-Path $scopePrefix 'GEMINI.md')
    }
    if ($kinds -contains 'copilot') {
        $copilotDir = Join-Path $scopePrefix '.github'
        New-Item -ItemType Directory -Force -Path $copilotDir | Out-Null
        Upsert-MarkerBlock (Join-Path $RepoRoot '.github\copilot-instructions.md') (Join-Path $copilotDir 'copilot-instructions.md')
    }
    Ensure-GitignoreEntries -ProjectRoot $scopePrefix
    Write-Host ""
}

# ── Copy helpers ───────────────────────────────────────────────────────────────

function Copy-FilteredSkills {
    param([string]$Dest, [string]$Mode)

    # Preserve unowned or locally edited skills and indexes on every upgrade.
    & $pythonCmd -X utf8 (Join-Path $RepoRoot 'scripts/managed_skills.py') install $Dest --index @selectedSkills
    if ($LASTEXITCODE -ne 0) { throw "Managed skill installation failed" }
}

# Mirror of _copy_runtime_scripts() in scripts/install.sh — copy ONLY the
# whitelisted runtime scripts (scripts/runtime-manifest.txt) into $Dest.
# Dev/test/release tooling is never shipped.
function Copy-RuntimeScripts {
    param([string]$Dest, [string]$Mode)

    $manifest = Join-Path $RepoRoot 'scripts\runtime-manifest.txt'
    if (-not (Test-Path $manifest)) {
        throw "scripts/runtime-manifest.txt not found — cannot resolve runtime script set."
    }
    # Wipe only on explicit force. In global scope $Dest is ~/.<host>/scripts,
    # which may hold the user's own scripts; the auto-detected `upgrade` mode
    # must overwrite whitelisted files in place, not nuke the whole dir (H3).
    if ($Mode -eq 'force' -and (Test-Path $Dest)) {
        Remove-Item -Recurse -Force $Dest
    }
    New-Item -ItemType Directory -Force -Path $Dest | Out-Null
    foreach ($raw in Get-Content $manifest) {
        $name = ($raw -replace '#.*$', '').Trim()
        if ([string]::IsNullOrWhiteSpace($name)) { continue }
        $srcScript = Join-Path $RepoRoot ('scripts\' + $name)
        if (Test-Path $srcScript) {
            Copy-Item -Force -Path $srcScript -Destination (Join-Path $Dest $name)
        } else {
            Write-Warning "manifest lists $name but scripts\$name missing — skipped"
        }
    }
}

# Mirror of _copy_owned_tree() in scripts/install.sh — copy a toolkit-owned tree
# WITHOUT deleting or clobbering the user's own files. Ownership tracked in
# "$Dest/.sgt-owned". User files (never owned) are left untouched; a user file
# colliding with our name is preserved (ours saved as *.skill-governance-toolkit.*).
function Copy-OwnedTree {
    param([string]$Src, [string]$Dest)

    if (-not (Test-Path $Src)) { return }
    New-Item -ItemType Directory -Force -Path $Dest | Out-Null
    $ownedFile = Join-Path $Dest '.sgt-owned'
    $wasOwned = if (Test-Path $ownedFile) { @(Get-Content $ownedFile) } else { @() }
    $nowOwned = New-Object System.Collections.Generic.List[string]
    $srcFull  = (Resolve-Path $Src).Path.TrimEnd('\', '/')

    Get-ChildItem -Path $Src -Recurse -File -Force |
        Where-Object { $_.Name -ne '.DS_Store' -and $_.FullName -notmatch '__pycache__' -and $_.FullName -notmatch '\.skill-state' } |
        ForEach-Object {
            $rel = ($_.FullName.Substring($srcFull.Length).TrimStart('\', '/')) -replace '\\', '/'
            $nowOwned.Add($rel)
            $d = Join-Path $Dest $rel
            New-Item -ItemType Directory -Force -Path (Split-Path $d -Parent) | Out-Null
            $collision = (Test-Path $d) -and ($wasOwned -notcontains $rel) -and `
                         ((Get-FileHash $_.FullName).Hash -ne (Get-FileHash $d).Hash)
            if ($collision) {
                $base = Split-Path $rel -Leaf
                $dir  = Split-Path $rel -Parent
                $ext  = [System.IO.Path]::GetExtension($base)
                $stem = [System.IO.Path]::GetFileNameWithoutExtension($base)
                $renamed = "$stem.skill-governance-toolkit$ext"
                if ($dir) { $renamed = "$dir/$renamed" }
                Copy-Item -Force $_.FullName (Join-Path $Dest $renamed)
                Write-Warning "conflict: user has $rel — saved ours as $renamed"
            } else {
                Copy-Item -Force $_.FullName $d
            }
        }
    foreach ($prev in $wasOwned) {
        if ([string]::IsNullOrWhiteSpace($prev)) { continue }
        if ($nowOwned -notcontains $prev) {
            $p = Join-Path $Dest $prev
            if (Test-Path $p) { Remove-Item -Force $p }
        }
    }
    ($nowOwned | Sort-Object) -join "`n" | Set-Content -Path $ownedFile -Encoding UTF8
}

# Use the same hash-verified documentation installer as the shell path.
function Ensure-DocsCopied {
    param([string]$Dest)
    $srcDocs = Join-Path $RepoRoot 'docs'
    if (-not (Test-Path $srcDocs)) { return }
    & $pythonCmd -X utf8 (Join-Path $RepoRoot 'scripts/managed_docs.py') $srcDocs $Dest
    if ($LASTEXITCODE -ne 0) { throw 'Managed documentation installation failed' }
}

function Install-Host {
    param([hashtable]$Target, [string]$ScopePrefix, [string]$Mode)

    $dest = Join-Path $ScopePrefix $Target.Dir
    switch ($Target.Kind) {
        'claude' {
            Copy-FilteredSkills (Join-Path $dest 'skills')     $Mode
            Copy-OwnedTree (Join-Path $RepoRoot 'agents') (Join-Path $dest 'agents')
            Copy-RuntimeScripts (Join-Path $dest 'scripts') $Mode
            Copy-OwnedTree (Join-Path $RepoRoot 'references') (Join-Path $dest 'references')
            Copy-OwnedTree (Join-Path $RepoRoot 'commands') (Join-Path $dest 'commands')
            Copy-Item (Join-Path $RepoRoot 'CLAUDE.md')  (Join-Path $dest 'CLAUDE.md') -Force
            # Consumer variant — runtime copies must not carry toolkit-repo prose.
            Copy-Item $agentsForInstall (Join-Path $dest 'AGENTS.md') -Force
            if ($ScopePrefix -ne $HOME) {
                $rootAgents = Join-Path $ScopePrefix 'AGENTS.md'
                if (-not (Test-Path $rootAgents)) {
                    Copy-Item $agentsForInstall $rootAgents -Force
                }
            }
            Write-Host "[ok] Claude Code: $dest  ($($selectedSkills.Count) skills)"
        }
        'copilot' {
            if ($ScopePrefix -eq $HOME) {
                New-Item -ItemType Directory -Force -Path $dest | Out-Null
                Upsert-MarkerBlock (Join-Path $RepoRoot '.github/copilot-instructions.md') `
                                   (Join-Path $dest 'copilot-instructions.md')
                Write-Host "[ok] Copilot (global): $dest\copilot-instructions.md"
            } else {
                Write-Host "[ok] Copilot: managed via marker block in project root .github/"
            }
            $skillDest = Join-Path $dest 'skills'
            if ($ScopePrefix -eq $HOME) { $skillDest = Join-Path $ScopePrefix '.copilot/skills' }
            if ($selectedSkills.Count -gt 0) {
                & $pythonCmd -X utf8 (Join-Path $RepoRoot 'scripts/managed_skills.py') install $skillDest @selectedSkills
                if ($LASTEXITCODE -ne 0) { throw "Copilot skill installation failed" }
            }
        }
        'codex' {
            Copy-FilteredSkills (Join-Path $dest 'skills')     $Mode
            Copy-OwnedTree (Join-Path $RepoRoot 'agents') (Join-Path $dest 'agents')
            Copy-RuntimeScripts (Join-Path $dest 'scripts') $Mode
            Copy-OwnedTree (Join-Path $RepoRoot 'references') (Join-Path $dest 'references')
            Copy-OwnedTree (Join-Path $RepoRoot 'commands') (Join-Path $dest 'commands')
            Copy-Item (Join-Path $RepoRoot '.codex-plugin/plugin.json') `
                      (Join-Path $dest 'plugin.json') -Force
            Write-Host "[ok] Codex CLI:  $dest  ($($selectedSkills.Count) skills)"
        }
        'gemini' {
            Copy-FilteredSkills (Join-Path $dest 'skills')     $Mode
            Copy-RuntimeScripts (Join-Path $dest 'scripts') $Mode
            Copy-OwnedTree (Join-Path $RepoRoot 'references') (Join-Path $dest 'references')
            Copy-OwnedTree (Join-Path $RepoRoot 'commands') (Join-Path $dest 'commands')
            Copy-Item (Join-Path $RepoRoot 'GEMINI.md') (Join-Path $dest 'GEMINI.md') -Force
            # AGENTS.md inside $dest — GEMINI.md uses `@./AGENTS.md` (consumer
            # variant; mirrors bash install_gemini, which always shipped it).
            Copy-Item $agentsForInstall (Join-Path $dest 'AGENTS.md') -Force
            Copy-Item (Join-Path $RepoRoot 'gemini-extension.json') `
                      (Join-Path $dest 'extension.json') -Force
            Write-Host "[ok] Gemini CLI: $dest  ($($selectedSkills.Count) skills)"
        }
        'cursor' {
            Copy-FilteredSkills (Join-Path $dest 'skills')     $Mode
            Copy-RuntimeScripts (Join-Path $dest 'scripts') $Mode
            Copy-OwnedTree (Join-Path $RepoRoot 'references') (Join-Path $dest 'references')
            Copy-OwnedTree (Join-Path $RepoRoot 'commands') (Join-Path $dest 'commands')
            Write-Host "[ok] Cursor:     $dest\skills  ($($selectedSkills.Count) skills) (AGENTS.md read from repo root)"
        }
    }
}

# ── Ensure project root canonical dirs (since 1.6.2) ─────────────────────────
# Mirror of ensure_project_root_canonical_dirs() in scripts/install.sh —
# in project scope, place skills/, agents/, references/, scripts/, commands/
# at TARGET_PROJECT root so Copilot/Cursor/Codex can auto-discover them.
if ($scopeChoice -eq '2' -and -not $selfInstall) {
    Write-Host "── Placing canonical dirs at project root (root-first layout) ──"
    Copy-FilteredSkills (Join-Path $scopePrefix 'skills') $mode
    Copy-OwnedTree (Join-Path $RepoRoot 'agents') (Join-Path $scopePrefix 'agents')
    Copy-OwnedTree (Join-Path $RepoRoot 'references') (Join-Path $scopePrefix 'references')
    Copy-RuntimeScripts (Join-Path $scopePrefix 'scripts') $mode
    Copy-OwnedTree (Join-Path $RepoRoot 'commands') (Join-Path $scopePrefix 'commands')

    # Root manifests only for SELECTED hosts — mirror of scripts/install.sh
    # ensure_project_root_canonical_dirs (a claude-only install must not plant
    # Codex/Gemini manifests in the user's repo).
    if ($kinds -contains 'codex') {
        New-Item -ItemType Directory -Force -Path (Join-Path $scopePrefix '.codex-plugin') | Out-Null
        Copy-Item -Force (Join-Path $RepoRoot '.codex-plugin/plugin.json')       (Join-Path $scopePrefix '.codex-plugin/plugin.json')
    }
    if ($kinds -contains 'claude') {
        New-Item -ItemType Directory -Force -Path (Join-Path $scopePrefix '.claude-plugin') | Out-Null
        Copy-Item -Force (Join-Path $RepoRoot '.claude-plugin/plugin.json')      (Join-Path $scopePrefix '.claude-plugin/plugin.json')
        Copy-Item -Force (Join-Path $RepoRoot '.claude-plugin/marketplace.json') (Join-Path $scopePrefix '.claude-plugin/marketplace.json')
    }
    if ($kinds -contains 'gemini') {
        Copy-Item -Force (Join-Path $RepoRoot 'gemini-extension.json')           (Join-Path $scopePrefix 'gemini-extension.json')
    }

    # Project docs (mirror of bash ensure_docs_copied) — the dry-run plan above
    # promises these; without this the Windows-native path silently skipped them.
    Ensure-DocsCopied -Dest (Join-Path $scopePrefix 'docs')

    Write-Host "  · root layout ready: skills/, agents/, references/, scripts/, commands/, docs/, manifests/"
    Write-Host ""
}

# Per-host install. Skipped entirely for a self-install (project scope whose
# target is the toolkit dir) — otherwise it would scatter .{host}/ dupes inside
# the source, the exact bug the bash guard prevents (H2).
if ($selfInstall) {
    Write-Host "── Self-install — skipping per-host install (would create .{host}/ dupes inside the toolkit dir) ──"
} else {
    foreach ($t in $targets) { Install-Host -Target $t -ScopePrefix $scopePrefix -Mode $mode }
}

# Clean up the generated consumer AGENTS.md temp file.
if ($agentsForInstall -ne (Join-Path $RepoRoot 'AGENTS.md') -and (Test-Path $agentsForInstall)) {
    Remove-Item $agentsForInstall -Force
}

Write-Host "`nDone."
