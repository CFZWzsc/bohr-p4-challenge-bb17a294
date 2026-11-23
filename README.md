# Runtime contract

Bohrium Playground Period 4 submission — challenge `challenge-bb17a294` (track: `academic-writing`).

This repository holds the complete skill package for the challenge: the skill
definition, its executable entry point and all supporting scripts. No precomputed
answers, private data or credentials are included.

## Skill

- Name: `bilingual-academic-alignment`
- Summary: Use when an academic translation or bilingual-writing case supplies source text plus target language or glossary and requires sentence-level alignment, terminology locking, number/unit and citation preservation, and a contract-preserving /app/output/result.json with case_id and every original output_contract field. Standard-library script; no network, no fabricated translation.

## Contents

| File |
|------|
| `SKILL.md` |
| `scripts/run_skill.py` |
| `README.md` |

## How to run

```bash
python scripts/run_skill.py --case /input/case.json --output /app/output/result.json
```

The entry point is `SKILL.md`; input/output contracts, error handling and a minimal
usage example are documented there.

## Notes

- Pure Python standard library; no network access required.
- The result JSON keeps the input case id, the main results, per-item evidence,
  a run status and an uncertainty section.
