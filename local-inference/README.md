# Optional Windows Qwen3-8B companion

Created by ChatGPT (OpenAI).

This is an experimental local evidence assistant for the company earnings page. It runs on the reader's own Windows computer. GitHub Pages serves the interface; it does not host inference. The existing charts, deterministic valuation math and rule-based analysis keep their own behavior. No remote API key, adapter or weights are included.

The tested source is `Qwen/Qwen3-8B`, Apache 2.0, revision `b968826d9c46dd6066d109eabc6255188de91218`. It is the unadapted 8B base; the historical 4B financial adapter cannot be loaded into it. This is inference, not new 8B training or a combination of model parameter counts.

## Start in the isolated Beta environment

The owner already has the complete pinned weights and a verified independent virtual environment. From the Beta directory, call its Python executable directly; activation is unnecessary. Paths below are relative to that Beta checkout and its isolated integration snapshot:

```powershell
& '.venv\Scripts\python.exe' -u 'model-expansion-lab\operations\20261016-windows8b-integration\checkout\local-inference\local8b_service.py' --model-source 'model-expansion-lab\operations\20261016T182700Z\qwen3-8b-source' --runtime 'model-expansion-lab\operations\20261016-windows8b-integration\runtime-v2'
```

Do not start this command while the existing companion or a training/evaluation GPU job is running. The server checks GPU usage and refuses startup above 700 MiB. It listens only on `127.0.0.1:8768`; do not expose it on a LAN or public interface. Stop this foreground command with Ctrl+C when done; it is not installed as a system service or scheduled job.

Open a company earnings page, expand **Ask local Qwen3-8B**, and paste the contents of the runtime's `client-token.txt` into **Local access token**. Select **Connect** and allow browser local network access if prompted. The token is generated on startup, stays in browser page memory, and is cleared on disconnect/reload. Do not place it in a URL, GitHub secret for public JavaScript, or source control. Other computers require their own local companion and model installation.

For a fresh installation, use a separate virtual environment and the versions in `requirements-windows.txt`. CUDA PyTorch uses the official `https://download.pytorch.org/whl/cu128` index. Provision the pinned Hugging Face snapshot separately after checking disk space (raw model shards total 16,381,516,776 bytes). This server never downloads weights automatically. The provided versions were measured on Python 3.14.7, driver 581.83 and an RTX 3050 Laptop 6GB; other platforms and browsers have not been validated.

## Limits and checks

- NF4 double quantization, BF16 compute, 36 decoder blocks on the GPU. Embeddings and output head reside in RAM and Accelerate stages them on the GPU for execution. This is explicit offload, not full CPU-only inference.
- Greedy decoding, thinking disabled, batch one, at most 192 output tokens and a 90-second generation budget (checked between generation iterations). Full input plus output budget is limited to 2048 tokens. Overlength examples fail explicitly; gold evidence is not cut mid-passage.
- The interface ranks complete website summaries/chart values/excerpts by literal query terms. It sends at most three passages and 3600 text characters. It does not fetch original PDFs, OCR, full notes or arbitrary URLs.
- JSON schema, supplied source IDs and exact quote substrings are checked. These checks do not prove that the answer follows from the quote, that a website label matches the original SEC document, or that arithmetic is correct. Review the linked filing and use deterministic calculations.
- Unsupported answers must use `answer: null`. Malformed JSON, fabricated quotes and unknown source IDs are rejected; no accepted answer is shown. There is no automatic retry or repair that could hide the original failure.
- The companion accepts authenticated requests from `https://filing-flows.com` and `https://www.filing-flows.com`, uses exact Host checks and one active inference lock, rejects oversized bodies, and does not log questions/tokens/answers. Local HTTP is loopback-only; public site traffic remains HTTPS.
- Existing experiment policy is used: require <=78 C before a new request; check the 86 C stop threshold every eight generated tokens. This is an operational cutoff, not an OEM safety certification.

CPU tests: run `python local-inference/test_local8b.py` and `node tests/test_local_model.cjs` with the appropriate isolated interpreter. Do not interpret a few successful smoke cases as financial-domain accuracy or held-out benchmark results.

Chrome's [Local Network Access documentation](https://developer.chrome.com/blog/local-network-access) explains the browser permission. Do not disable browser security protections to make a connection work. Other browser behavior may differ.
