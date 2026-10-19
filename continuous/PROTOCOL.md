# Continuous loop protocol

Created by Claude (Anthropic), 2026-10-18. This protocol is fixed before cycle 1. Changing it means starting a new protocol version, written down here, and never editing past decisions.

## Owner decisions

- **Duration:** run until stopped.
- **Publishing:** after every cycle, push only small files to `eurikamonica/filing-flows`, branch `lab/qwen3-4b-fsa-20261018`. Small files are cycle data rows, protocols, evaluations, reports, adapters, state and code. No GGUF or merged weights are pushed. Raw SEC and website downloads are deleted after each cycle's build; only their manifests are kept.
- **Task A** (revision reason): rule-derived weak labels. They are trained on and reported separately, and excluded from the gate.
- **GPU temperature:** no cutoff. Readings are logged.
- **Model size:** Qwen3-4B only. 8B is not used.

## Each cycle

1. **New companies.** No company used by any earlier dataset or cycle is reused.
   - 30 NYSE/Nasdaq SEC filers produce tasks A and C. The held-out tags of task C are the 13 fixed by `runs/v3-data-20261018T052500Z/heldout-tags.json`. They never enter training in any cycle.
   - 40 owner-website companies plus new synthetic fixtures produce basic-finance rows. The generators are unchanged. The two degenerate tasks (basic_instruction, reserve_movement) are skipped.
2. **Splits and fresh protocol.**
   - Companies are split 70/15/15 into train, dev and sealed.
   - An input seen anywhere before (any split, any corpus, any cycle) is excluded from the new data.
   - The fresh protocol is built from this cycle's dev split before any inference: up to 20 A rows, up to 40 C rows (about half on held-out tags), and 2 rows per basic-finance task.
   - Rows longer than 768 tokens (prompt plus answer) are dropped, never truncated.
3. **Training.**
   - Start from the current champion adapter, with a fresh optimizer.
   - Data: this cycle's training rows plus an equal-size random replay sample from all earlier training rows, in all output contracts.
   - Settings: NF4 QLoRA, rank 8 on q_proj and v_proj, context 768, gradient accumulation 4, learning rate 5e-5.
   - Steps: ceil(train rows / 4), capped at 600.
4. **Evaluation.** Greedy decoding, thinking disabled.
   - The candidate runs Gate 2 dev48, basic-finance-v3 dev40, basic-finance-v4 dev90 and the fresh protocol.
   - The champion runs the fresh protocol. Its fixed-protocol numbers are carried over from the cycle where it was promoted.
5. **Gate.** The candidate is promoted only if all of the following hold:
   - Fresh protocol, excluding task A: correct ≥ champion + 2.
   - Gate 2 joint ≥ champion − 1, and Gate 2 historical regression ≥ champion − 1.
   - basic-finance-v4 dev90 ≥ champion − 2, and basic-finance-v3 dev40 ≥ champion − 2.
   - Valid JSON on every fixed protocol ≥ champion − 1.
6. **After the gate.**
   - Promoted adapters are copied to `champions/cycle-NNN`.
   - The cycle's training rows join the replay pool.
   - Checkpoints are deleted.

## Stop conditions

- `continuous/STOP` exists. It is checked between cycles, and training stops at its next 5-step check.
- Free disk space drops below 25 GiB.
- Three consecutive cycles fail.
- Five consecutive cycles end without a promotion (plateau).

## Protocol v2 (2026-10-19, from the restart after cycle 4)

The owner changed only publishing and housekeeping. Data, training and the gate are unchanged.

- **On every promotion:**
  - The new champion is merged NF4-faithfully, exported as a Q8_0 GGUF and split into shards under 1.9 GB.
  - The split file is evaluated on the fixed protocols.
  - The export is published in `exports/<champion>/`.
- **Local cleanup:** older champions' local exports are deleted. Champion adapters are kept.
- **Publishing:**
  - Each cycle still commits locally, and the local branch keeps the full history.
  - The remote branch is force-pushed (`--force-with-lease`) as a single-commit snapshot of the current useful tree.
  - The snapshot leaves out older champions' exports and all non-promoted candidate adapters.
  - GitHub keeps LFS objects that were already uploaded, so this does not reduce LFS storage or quota.

## Caveats

- Fixed protocols are reused every cycle, so repeated selection on them gradually overfits the choice. The fresh protocol is new each cycle, but its tasks come from the same generators and rules as the training rows.
- Sealed splits are written and published but never scored.
