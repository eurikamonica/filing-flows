# Cycle 008

Created by Claude (Anthropic).

New training rows 811 (+ equal replay), 406 steps from `cycle-004`.

Fresh protocol core: candidate 56 vs champion 55 of 58. Weak revision-reason labels: candidate 1 vs champion 2 of 2 (not gated).

Fixed: Gate 2 36/48 (regression 16/18), bfv3 40/40, bfv4 88/90.

Gate checks: {"fresh_core_gain": false, "gate2_joint": true, "gate2_regression": true, "bfv4": true, "bfv3": true, "valid_json": true}. Result: champion kept.

All protocols are development sets; nothing here is a sealed-test score.
