# Continuous training status

Created by Claude (Anthropic). Updated every cycle by `continuous.py`.

Status: **running** · cycles: 9 · champion: `cycle-004`

Current weights: adapter `champions/cycle-004`; Q8_0 GGUF in `exports/cycle-004/gguf/` (fixed protocols as GGUF: bfv3_dev40 39, gate2_dev48 36, bfv4_dev90 88)

| Cycle | New train rows | Fresh core (cand / champ) | Weak A label (cand / champ) | Gate 2 (cand) | Regression | bfv4 | Result |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 797 | 72/76 vs 46 | 5/10 vs 7 | 37/48 | 17/18 | 89/90 | kept champion |
| 2 | 863 | 58/63 vs 43 | 6/14 vs 2 | 37/48 | 17/18 | 87/90 | promoted |
| 3 | 825 | 60/65 vs 61 | 2/6 vs 5 | 36/48 | 16/18 | 87/90 | kept champion |
| 4 | 758 | 70/76 vs 65 | 0/0 vs 0 | 36/48 | 17/18 | 88/90 | promoted |
| 5 | 868 | 75/76 vs 75 | 2/2 vs 0 | 37/48 | 17/18 | 88/90 | kept champion |
| 6 | 799 | 66/68 vs 65 | 3/9 vs 2 | 35/48 | 16/18 | 88/90 | kept champion |
| 7 | 801 | 74/76 vs 74 | 4/4 vs 4 | 36/48 | 17/18 | 86/90 | kept champion |
| 8 | 811 | 56/58 vs 55 | 1/2 vs 2 | 36/48 | 16/18 | 88/90 | kept champion |
| 9 | 855 | 65/67 vs 64 | 3/3 vs 0 | 36/48 | 17/18 | 86/90 | kept champion |

Fresh protocol = this cycle's new dev questions (companies never used before). "Core" excludes the weak
revision-reason labels (rule-derived, not human-reviewed), which are reported separately and not gated.
Gate and stop rules: continuous/PROTOCOL.md.
