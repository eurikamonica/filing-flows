# Cycle 002

Created by Claude (Anthropic).

New training rows 863 (+ equal replay), 432 steps from `qwen4-bfv3mix-20261017`.

Fresh protocol core: candidate 58 vs champion 43 of 63. Weak revision-reason labels: candidate 6 vs champion 2 of 14 (not gated).

Fixed: Gate 2 37/48 (regression 17/18), bfv3 38/40, bfv4 87/90.

Gate checks: {"fresh_core_gain": true, "gate2_joint": true, "gate2_regression": true, "bfv4": true, "bfv3": true, "valid_json": true}. Result: promoted cycle-002.

All protocols are development sets; nothing here is a sealed-test score.
