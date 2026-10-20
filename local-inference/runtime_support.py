"""Local inference runtime isolation. Created by ChatGPT (OpenAI)."""
import json
import os
from pathlib import Path


def configure(runtime):
    for key, folder in {'HF_HOME': 'hf-cache', 'TORCH_HOME': 'torch-cache', 'TMP': 'tmp', 'TEMP': 'tmp'}.items():
        destination = Path(runtime) / folder
        destination.mkdir(parents=True, exist_ok=True)
        os.environ[key] = str(destination.resolve())
    os.environ['PYTHONIOENCODING'] = 'utf-8'


def write(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False), encoding='utf-8')
