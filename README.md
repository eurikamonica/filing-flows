# Isolated model expansion lab

Created by ChatGPT (OpenAI).

This independent local Git repository implements the supplied Gate 0/1 audit and data preparation, followed by one bounded Gate 2 continuation protocol. It does not touch other labs, production code or the completed overnight controller. The existing Beta virtual environment is reused without modifying dependencies; all new runtime files live under `runs/<UTC run ID>/`. `current-run.json` identifies the active experiment.

Read the nine English reports under the selected run directory. All source snapshots, split manifests, pinned dependency versions, checkpoints and raw answers remain in that run and are excluded from source control. Historical champions are independently copied, with hashes. The new sealed test is never read by token packing or development evaluation. Procedural sealing is not access control.

From the Beta directory, use its Python executable directly:

```powershell
.\.venv\Scripts\python.exe model-expansion-lab/lab.py
.\.venv\Scripts\python.exe model-expansion-lab/protocol.py prepare
.\.venv\Scripts\python.exe model-expansion-lab/protocol.py execute
```

These are sequential one-time preparation/execution commands, not an automatic retry workflow. Inspect the current run and reports before rerunning anything. A failed thermal/resource gate stops; it does not automatically resume identical work. Preparation refuses archive replacement through unique run directories; execution owns a run-scoped lock.

`inspect_parameters.py` is a CPU/meta architecture inspection. `merge_export.py` is a separate optional CPU same-base export pilot, dry-run by default; it has not been merged or deployed by Gate 2. Compatible LoRA APIs and limitations were checked against installed PEFT 0.21.2 and the [official PEFT documentation](https://huggingface.co/docs/peft/developer_guides/model_merging). The [official LoRA reference](https://huggingface.co/docs/peft/package_reference/lora) explains layer replication; shared replicas must not be counted as independent new dense weights. [Qwen3-8B](https://huggingface.co/Qwen/Qwen3-8B) is a possible separate future base, not a download or training promise. No 8B or expanded-layer experiment is launched here.
