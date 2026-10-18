# FSA hourly bank, SEC questions and research-report governance

This extension is additive to PR #20. The hourly job **generates and archives study questions**; it NEVER automatically trains Qwen3-4B, downloads paywalled reports, publishes model weights, promotes a candidate, or modifies the production website.

## Schedule and outputs

- GitHub Actions -> **FSA Hourly Question Bank** runs at minute **17** of each UTC hour. GitHub cron is best-effort, may run late or be skipped. The schedule activates **only when the workflow exists on the default branch**; reviewing and merging PR #20 is therefore required.
- Each successful hour creates **18 deterministic hypothetical exercises** (3 examples each: balanced journal entries, accounting equation, IS/BS/SCF, accrual ratio, sign/percent growth, and no-evidence abstention), with independent arithmetic checks.
- When \`SEC_USER_AGENT\` is set in repository Variables or Secrets (with descriptive real contact details), the generator additionally queries a small bounded list of SEC companyfacts sources. It uses approximately one request per second. No request is sent without a configured identifiable User-Agent. A failing SEC request never invents a fact.
- Newly sourced SEC problems include original API reference, CIK/ticker where available, XBRL concept, accession and fiscal periods. These are **candidate questions requiring human review**, not production-ready gold labels.
- New questions, source metadata, and the new task backlog are committed to **fsa-question-bank** (a separate output branch, not \`main\`, \`model\`, or \`narratives\`), under \`hourly/YYYY-MM-DD/HH.json\` and \`HH-tasks.json\`. \`LATEST.md\` summarizes the most recent run. The list \`index/seen_ids.txt\` deduplicates across hourly runs.
- Workflow run summary and a 14-day GitHub Artifact also contain question bank and backlog. The job does **not** run a 4B training job each hour.

## P0 / P1 / P2 implementation matrix

| Level | Area | Implementation |
| --- | --- | --- |
| P0 | historical replay | every hour produce replay review task; existing manual QLoRA workflow retains the old corpus replay |
| P0 | journal entry / three statements | machine-checked balanced entries, A=L+E, NI / CFO / cash bridge |
| P1 | real SEC fields | bounded annual 10-K calculations from official SEC companyfacts, with original provenance and period checks |
| P1 | wrong-answer mining | optional reviewed \`index/latest_evaluation.json\` containing evaluation protocols with per-example correctness; records weakest tasks |
| P2 | reasoning and abstention | intermediate checks for chain calculations; explicit null when evidence absent |
| P2 | distillation | teacher suggestions are review tasks only; teacher model is NOT invoked automatically, and outputs must be independently verified |
| research | analyst research reports | local-only document staging + strict rights and numeric fact review before allowing derived questions |

This is a staged implementation, not completion of every future training objective. In particular, no automatically graded multi-hop real filing benchmark or teacher-model distillation exists yet.

## Importing research reports legally and usefully

Research reports may include broker research, sector notes, authorized investment-bank research, company-sponsored research, trade association papers, issuer investor presentations, and public-sector research. **Publicly accessible is not always licensed for ML training or redistribution.** Do not commit paywalled PDF text, unlicensed third-party analyst narratives, or private client materials to this public GitHub repository.

For your own files:
1. Create a private local report inbox (PDF/DOCX/MD/TXT).
2. Record a report filename, title, publisher, date, exact source and processing/training rights with supporting authorization.
3. Run the local staging helper to extract *candidate* metrics. It deliberately provides **no gold labels**. Humans must verify page, date, value, unit and original source against the actual report.
4. Convert authorized and reviewed data into structured entries in \`research_reports/approved_manifest.json\`. Examples are in \`research_reports/manifest.example.json\`. Only report records with \`review_status=approved\`, \`public_redistribution_allowed=true\`, \`ml_rights\` (owned/licensed_for_training/public_domain), and \`rights_evidence\` are exported to the PUBLIC hourly bank. For privately licensed materials not permitted to redistribute, process only on a private runner/storage; never feed them to this public job.
5. Analyst target prices, future earnings predictions, and recommendations are **opinions/forecasts**; never promote these to historical fact labels. Use source-grounded comparison tasks and separate dates, attribution and confidence in later model phases.

If no approved report records exist (the committed manifest is intentionally empty), the hourly job still produces synthetic FSA questions. It must not claim it has trained on research documents.

## Suggested train-review lifecycle

Accumulate and review new samples for a day or week, deduplicate by underlying company/document and accounting scenario, then curate a train-only JSONL separate from the old and new held-out test companies. QLoRA on the Windows GPU runner should warm-start from an explicitly pinned champion, retain at least a 30% historical replay mix, and run a **bounded 50-step pilot** before 100/200 steps. Existing synthetic validation questions are not sufficient for promotion. Use unseen SEC documents and human-graded journal entries, report evidence checks, and regression gates.

When a candidate is approved, update the champion through a *separate deliberate owner decision*. This repo addition intentionally avoids that action.

## Security and operational notes

Github-hosted schedule executions consume Actions/artifact/LFS quotas and may be delayed. Automatic commits to fsa-question-bank need repository Actions permissions permitting \`GITHUB_TOKEN\` to write contents. Do not add unrestricted self-hosted runners to this hourly CPU workflow. The staged report parser should only run on documents you have permission to process. \`SEC_USER_AGENT\` should name your project and a valid contact method; the SEC publishes an access limit of 10 requests/second, while this script requests at less than 1/second.


## Local report staging: example commands

On Windows, choose a PRIVATE folder for documents you are allowed to process. Store private rights metadata separately from this public GitHub repo, e.g.:

\`reports-rights.json\` keyed by local filename:
\`\`\`json
{
  "own-note.pdf": {
    "id": "local-research-001",
    "ml_rights": "owned",
    "rights_evidence": "Author holds the rights for model development"
  }
}
\`\`\`

Run:
\`\`\`powershell
python -m pip install pypdf
python scripts/fsa_report_stage.py --inbox "C:\FSA\research-inbox" --metadata "C:\FSA\reports-rights.json" --out "C:\FSA\research-review.json"
\`\`\`

It detects *candidate* financial amounts from PDF/DOCX/MD/TXT text. This is not OCR, may miss tables and scans, and DOES NOT turn matches into approved gold; verify them against each report. Only **explicitly approved, factual, redistribution-allowed** records can be added to the public \`research_reports/approved_manifest.json\`.

## Optional manual training with an approved hourly bank

In the **FSA Qwen3-4B Experimental Lab** Action, after the bank branch first exists, choose \`mode: audit\` and \`hourly_count: 18\` to check the mixed train pack. For a separately approved 50-step GPU pilot, choose \`mode: train\`, \`hourly_count: 18\`, \`steps: 50\`, and \`max_length: 512\` in direct CLI if required. The workflow presently sets max length to 384; longer multi-statement exercises may be dropped and recorded, not truncated.

\`hourly_count\` options are 0, 18, 72, and 200. It reads up to 168 recent hourly batches, keeps only rows explicitly marked as verified for training, checks for known open-dev prompt overlap and dynamically raises replay size if needed to retain at least 30% historical training examples. This opt-in still requires the self-hosted Windows CUDA runner. No automatic promotion and no hourly GPU training.

Reviewed larger-model answers can be staged locally:
\`\`\`powershell
python scripts/fsa_distill_review.py --candidates "C:\FSA\teacher-candidates.jsonl" --out "C:\FSA\teacher-reviewed-train.jsonl"
\`\`\`
This accepts only independently gold-matched responses with an explicit human reviewer, verified source, and training rights. It does **not** request an external teacher model or silently add the output to live training.

### GitHub permissions required

Repository **Settings → Actions → General → Workflow permissions** must allow the workflow's \`contents: write\` request for the question-bank branch. Restrict who can dispatch or modify workflows. Cron schedules can be delayed or skipped and for inactive public repos can be automatically disabled. The scheduled flow does not guarantee exactly 24 successful runs per day.
