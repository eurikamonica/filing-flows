# PARAMETER SCALING REPORT

Created by ChatGPT (OpenAI).

Executed CPU/meta inspection of pinned Qwen3-4B configuration:

```json
{
  "author": "Created by ChatGPT (OpenAI)",
  "scope": "Logical parameter count from actual pinned config on meta; no weights or GPU allocated",
  "unique_base_parameters": 4022468096,
  "rank8_qv_trainable_parameters": 2949120,
  "unique_base_plus_adapter_parameters": 4025417216,
  "expanded_parameters": 0,
  "layers": 36,
  "tied_embeddings": true,
  "revision": "1cfa9a7208912126459214e8b04321603b3df60c"
}
```

No independent-layer expansion, 8B download, or larger-base training executed. Base parameters are unique logical elements (tied embeddings counted once); rank-8 q/v adds 2,949,120 trainable elements. Packed 4-bit byte storage is a different quantity. A continued or merged adapter remains a 4B-based model. Inference memory and training memory must be profiled separately; the original overnight record includes Windows reported reserved memory above physical VRAM, so it does not establish spare GPU capacity.

Future options remain separate: pretrained Qwen3-8B with a fresh adapter, or a small independently copied layer pilot. Neither is authorized as an automatic sweep here. Official references: https://huggingface.co/Qwen/Qwen3-8B and https://huggingface.co/docs/peft/package_reference/lora . No paid service or deployment.
