"""CPU/meta logical parameter inspection. Created by ChatGPT (OpenAI)."""
from protocol import RUN, BETA, read, write


def main():
    import torch
    from transformers import AutoConfig, AutoModelForCausalLM
    source=BETA/'.runtime/model-sources/qwen3-4b'
    config=AutoConfig.from_pretrained(str(source),local_files_only=True)
    with torch.device('meta'):
        model=AutoModelForCausalLM.from_config(config)
    model.tie_weights()
    unique=sum(parameter.numel() for parameter in model.parameters())
    # q and v LoRA A/B matrices for each decoder block; validated from actual architecture shapes.
    adapter=sum(8*(module.in_features+module.out_features) for name,module in model.named_modules()
                if name.endswith(('.q_proj','.v_proj')))
    result={'author':'Created by ChatGPT (OpenAI)','scope':'Logical parameter count from actual pinned config on meta; no weights or GPU allocated',
        'unique_base_parameters':unique,'rank8_qv_trainable_parameters':adapter,
        'unique_base_plus_adapter_parameters':unique+adapter,'expanded_parameters':0,
        'layers':config.num_hidden_layers,'tied_embeddings':config.tie_word_embeddings,
        'revision':read(source/'model-source.json')['revision']}
    write(RUN/'parameter-counts.json',result)
    print(result)


if __name__=='__main__':main()
