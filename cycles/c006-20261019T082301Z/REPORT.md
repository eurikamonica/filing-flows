# Cycle 006

Created by Claude (Anthropic).

New training rows 799 (+ equal replay), 400 steps from `cycle-004`.

Fresh protocol core: candidate 66 vs champion 65 of 68. Weak revision-reason labels: candidate 3 vs champion 2 of 9 (not gated).

Fixed: Gate 2 35/48 (regression 16/18), bfv3 39/40, bfv4 88/90.

Gate checks: {"fresh_core_gain": false, "gate2_joint": true, "gate2_regression": true, "bfv4": true, "bfv3": true, "valid_json": true}. Result: champion kept.

All protocols are development sets; nothing here is a sealed-test score.
