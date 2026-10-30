from pathlib import Path
import zipfile
import ast
root = Path(__file__).resolve().parents[1]
tree=ast.parse((root/'ai_mesh_doctor/__init__.py').read_text(encoding='utf-8'))
info=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='bl_info' for t in n.targets))
version='.'.join(map(str,info['version']))
output = root / f"dist/ai_mesh_doctor-{version}.zip"
output.parent.mkdir(exist_ok=True)
with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
    for path in sorted((root/"ai_mesh_doctor").rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts:
            archive.write(path, path.relative_to(root))
print(output)
