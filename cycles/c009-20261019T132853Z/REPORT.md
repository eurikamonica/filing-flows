# Cycle 009

Created by Claude (Anthropic).

New training rows 855 (+ equal replay), 428 steps from `cycle-004`.

Fresh protocol core: candidate 65 vs champion 64 of 67. Weak revision-reason labels: candidate 3 vs champion 0 of 3 (not gated).

Fixed: Gate 2 36/48 (regression 17/18), bfv3 39/40, bfv4 86/90.

Gate checks: {"fresh_core_gain": false, "gate2_joint": true, "gate2_regression": true, "bfv4": true, "bfv3": true, "valid_json": true}. Result: champion kept.

All protocols are development sets; nothing here is a sealed-test score.
