# Experiments

These experiments use synthetic inputs. They do not measure customer adoption.
Keep generated transcripts in `out/`; they may contain local paths and agent context.

## Security corpus

`security-corpus.jsonl` contains 24 manually labelled examples.
The examples cover `SKILL014`, `SEC001`, `SEC002`, and `MCP001`.
Each case asserts one selected rule, not the full absence of other findings.
The corpus is small and includes examples similar to existing unit tests.
Its results do not establish general threat-detection performance.

Run `python3 experiments/run_security_corpus.py --verify`.
The report includes a corpus hash, rule version, and per-rule confusion counts.

## Paired behavior experiment

`behavior-cases.json` describes three synthetic skills and four factual questions per skill.
`run_behavior_pairs.py` compares a direct assessment with an assessment using `skill-evaluate`.
Both conditions use the same target, output schema, model, reasoning setting, and read-only mode.
The skill condition explicitly reads the skill and its scoring rubric.
The output includes nine dimension scores, but the current experiment does not validate them.
The factual answer labels do not establish the quality of a complete nine-dimension report.

Run `python3 experiments/run_behavior_pairs.py` only with an authenticated Codex CLI.
The command sends synthetic inputs and the skill text to the configured model provider.
The command records token usage, elapsed time, model, prompts, and transcripts under `out/`.
Review output for local paths before sharing.

## Observations on 2026-10-27

The security corpus returned 12 true positives and 12 true negatives.
The selected rules produced no mismatches on these 24 examples.

The paired behavior experiment used `gpt-6.1-sol` with medium reasoning.
The run records the tested skill hash in its local result file.
Each condition answered 12 of 12 factual questions correctly across three cases.
Each condition ran once per case, always with the baseline first.
The skill condition read the rubric in each recorded transcript.
The mean input was 53,319 tokens for baseline and 60,371 tokens with the skill.
Mean elapsed time was 31.1 seconds for baseline and 33.3 seconds with the skill.
The CLI reports token counts; this experiment does not calculate monetary cost.
These observations do not demonstrate an added benefit on the selected questions.
The sample is too small to establish statistical performance or generalize to other tasks.

The official `skills-ref` validator at revision `69ef37e9424c0a7ea9dd2293b559e43ec8176379` accepted all six bundled skills.
It also accepted a synthetic skill declaring `allowed-tools: Read`.
SGT separately reported that field as a high-severity portability-policy finding.
Cisco Skill Scanner 2.3.2 and SGT both flagged a synthetic destructive command.
That single shared example does not compare scanner recall or false positives.
