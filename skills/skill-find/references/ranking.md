# Ranking — signals, weights, scoring math

Detail reference for `skill-find` Phase 2 (Semantic matching). The body of `SKILL.md` keeps only the phase header + 1–2 sentence summary; this file holds the weights and math.

## Signal extraction

Parse `NEED` to extract matching signals:

**Signal A — Task verb (what the user wants to DO):** Identify the primary action: analyze / generate / review / create / compare / evaluate / find / fix / document / monitor / test / extract / validate / scan / write. Match against verbs in each skill's `description` and `name`. **Weight: 30%.**

**Signal B — Domain entities (WHAT the user works with):** Identify key objects: PR / ticket / test case / SKILL.md / code / design / prompt / API / database / report / requirement / component / skill. Match against `description`, `tags`, and `name`. **Weight: 35%.**

**Signal C — Expected output (WHAT the user wants to GET):** Identify output type: score / ranked list / YAML file / document / recommendation / comparison / diff / summary / alerts / dashboard. Match against output descriptions in `description`. **Weight: 20%.**

**Signal D — Trigger phrase match:** Does the skill's `description` contain «Use when…» / «Triggers:…» text that directly matches the phrasing in `NEED`? **Weight: 15%.**

## Compute match score (0–100) per entry

Combine the four weighted signals (30 + 35 + 20 + 15 = 100) into a single score. Scores clamp to 0–100.

## Match tier classification

- ≥ 75 → **Strong match** — covers the need as-is
- 50–74 → **Partial match** — covers part; may need adaptation
- 25–49 → **Weak match** — tangentially related; inspiration only
- < 25 → **No match** — exclude (unless all entries below 25)

Sort all entries by match score descending. Apply `LIMIT`.

## Tie-break on identical match score

When entries from different sources yield the same numeric match, order them by source priority — `project` > `personal` > `corporate`. Project-local skills take precedence because they reflect the user's most recent decisions; corporate is the lowest-priority fallback (it may be out-of-sync with the user's intent).

## Next-step recommendation per result

- Match ≥ 75% AND quality score ≥ 70: `✓ Use directly` → show invocation hint
- Match ≥ 75% AND quality score < 70: `⚠ Use, but run skill-evaluate first` — quality below threshold
- Match ≥ 75% AND quality = n/a (no cached score): `✓ Use — run skill-evaluate to confirm quality` — only gate on quality once a score exists
- Match 50–74%: `~ Partial — run skill-compare to adapt for your context`
- Match 25–49%: `○ Weak match — use as reference only when writing a new skill`
