"""Portable source + demo + compact evidence; no credentials, caches or vendored SDK."""
from pathlib import Path
import zipfile
import hashlib
import json
import ast
root = Path(__file__).resolve().parents[1]
tree=ast.parse((root/'ai_mesh_doctor/__init__.py').read_text(encoding='utf-8'))
info=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='bl_info' for t in n.targets))
version='.'.join(map(str,info['version']))
output = root/f"dist/ai_mesh_doctor-project-{version}.zip"
output.parent.mkdir(exist_ok=True)
with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if any(p in {"dist", "__pycache__", "runtime", "captures", "measurement_cache"} for p in relative.parts):
            continue
        if path.suffix.lower() not in {".py", ".md", ".json", ".ps1", ".txt", ".blend", ".log"} and path.name != ".gitignore":
            continue
        archive.write(path, Path("ai_mesh_doctor")/relative)
manifest = {"project_zip": str(output), "project_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            "addon_zip": str(root/f"dist/ai_mesh_doctor-{version}.zip"),
            "addon_sha256": hashlib.sha256((root/f"dist/ai_mesh_doctor-{version}.zip").read_bytes()).hexdigest(),
            "version":version}
(root/"dist/SHA256.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
print(output)
