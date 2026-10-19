# Cycle 001

Created by Claude (Anthropic).

New training rows 797 (+ equal replay), 399 steps from `qwen4-bfv3mix-20261017`.

Fresh protocol core: candidate 72 vs champion 46 of 76. Weak revision-reason labels: candidate 5 vs champion 7 of 10 (not gated).

Fixed: Gate 2 37/48 (regression 17/18), bfv3 38/40, bfv4 89/90.

Gate checks: {"fresh_core_gain": true, "gate2_joint": true, "gate2_regression": true, "bfv4": true, "bfv3": true, "valid_json": false}. Result: champion kept.

All protocols are development sets; nothing here is a sealed-test score.
