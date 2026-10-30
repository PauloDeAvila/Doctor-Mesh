"""Create a labeled contact sheet for visual QA, using Pillow outside Blender."""
import json
import math
from pathlib import Path
from PIL import Image, ImageDraw
root = Path(__file__).resolve().parents[1]
result = json.loads((root/"capture-test-results.json").read_text(encoding="utf-8"))
manifest = json.loads(Path(result["manifest"]).read_text(encoding="utf-8"))
files = manifest["files"]
columns, width, height = 8, 160, 110
sheet = Image.new("RGB", (columns*width, math.ceil(len(files)/columns)*height), (24,24,24))
draw = ImageDraw.Draw(sheet)
for index, entry in enumerate(files):
    with Image.open(entry["path"]) as frame:
        frame = frame.convert("RGB")
        frame.thumbnail((width,90))
        x,y = (index%columns)*width, (index//columns)*height
        sheet.paste(frame,(x,y))
        draw.text((x+2,y+91), entry["purpose"], fill=(240,240,240))
output = root/"reports/capture-test-sheet.jpg"
sheet.save(output,quality=92)
print(output)
