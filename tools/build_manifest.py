import hashlib
import json
import os
import sys

def main(model_dir):
    manifest = {}
    for name in os.listdir(model_dir):
        if not name.endswith(".onnx"):
            continue
        h = hashlib.sha256()
        with open(os.path.join(model_dir, name), "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        manifest[name] = h.hexdigest()
    out = os.path.join(model_dir, "manifest.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"written {out} ({len(manifest)} files)")

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "models")
