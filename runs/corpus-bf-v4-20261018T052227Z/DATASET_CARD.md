# DATASET CARD

Created by Claude (Anthropic).

Version: basic-finance-v4. Train/dev/sealed rows: 6225/358/360; dev protocol 90 questions (5 per task).

100 owner-website companies not used by any earlier corpus (stratified 40 10-K / 45 10-Q / 15 8-K by latest form), split 70/15/15 by company. Synthetic fixtures use new generator numbers, so none repeats basic-finance-v3. Task semantics, prompt contracts and gold checks are identical to basic-finance-v3 (same generator functions). Website values/headings are literal owner-source labels, not independent SEC verification; synthetic rows are explicitly hypothetical. basic_instruction and reserve_movement are train-only: the generator yields only 4 and 2 distinct prompts, all already present in v3, so they cannot be evaluated fresh. No human review. Exact prompt/company/document overlap across splits is zero; exact-input overlap with v3 open files is reported in manifest.json. The sealed test is not to be loaded for training or selection.
