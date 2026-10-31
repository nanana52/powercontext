#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
BASE="https://huggingface.co/Xenova/all-MiniLM-L6-v2/resolve/main"
ROOT="public/models/Xenova/all-MiniLM-L6-v2"
command -v curl >/dev/null || { echo "ERROR: curl is required." >&2; exit 1; }

download() {
  local rel="$1" min_bytes="$2" dest="$ROOT/$1" tmp size
  mkdir -p "$(dirname "$dest")"
  if [[ -f "$dest" ]] && [[ "$(wc -c < "$dest")" -ge "$min_bytes" ]]; then
    echo "OK (cached): $rel"
    return
  fi
  tmp="$dest.partial"
  rm -f "$tmp"
  echo "Downloading: $rel"
  curl -fL --retry 3 --connect-timeout 15 --max-time 900 -o "$tmp" "$BASE/$rel"
  size="$(wc -c < "$tmp")"
  if [[ "$size" -lt "$min_bytes" ]]; then
    echo "ERROR: suspiciously small file $rel ($size bytes)." >&2
    rm -f "$tmp"
    exit 1
  fi
  mv "$tmp" "$dest"
  echo "OK: $rel ($size bytes)"
}

download config.json 100
download tokenizer.json 100000
download tokenizer_config.json 100
download special_tokens_map.json 20
download vocab.txt 100000
download onnx/model_quantized.onnx 20000000
download onnx/model.onnx 80000000
download onnx/model_fp16.onnx 40000000

echo "PASS: all three model variants available for browser-side inference."
echo "Model files are intentionally ignored by Git."
