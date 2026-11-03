"""Answer one prompt with a model far bigger than the GPU, through AirLLM (layer by layer from disk: a 70B model on a
4-8 GB card). Slow - seconds to minutes per word - so for one important answer, never for an agent's every turn.

    python airllm_generate.py --model Qwen/Qwen2.5-72B-Instruct --prompt-file q.txt --out answer.txt [--max-new 400] [--cache DIR]
"""
import argparse, os, sys

ap = argparse.ArgumentParser()
ap.add_argument("--model", required=True)
ap.add_argument("--prompt-file", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--max-new", type=int, default=400)
ap.add_argument("--cache", default="")
a = ap.parse_args()
if a.cache:
    os.makedirs(a.cache, exist_ok=True)
    os.environ["HF_HOME"] = a.cache          # the model's layers go here (its own folder, never the system disk's cache)
from airllm import AutoModel  # noqa: E402

prompt = open(a.prompt_file, encoding="utf-8").read()
model = AutoModel.from_pretrained(a.model)
tok = model.tokenizer
if getattr(tok, "chat_template", None):
    prompt = tok.apply_chat_template([{"role": "user", "content": prompt}], tokenize=False, add_generation_prompt=True)
ids = tok([prompt], return_tensors="pt", truncation=True, max_length=4096)["input_ids"]
try:
    import torch
    if torch.cuda.is_available():
        ids = ids.cuda()
except Exception:
    pass
out = model.generate(ids, max_new_tokens=a.max_new, use_cache=True, return_dict_in_generate=True)
text = tok.decode(out.sequences[0][ids.shape[1]:], skip_special_tokens=True)
open(a.out, "w", encoding="utf-8").write(text)
print(f"LOKI_OUT {a.out} ({len(text.split())} words)")
sys.exit(0)
