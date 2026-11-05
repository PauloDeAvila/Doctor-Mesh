"""Read-only monitor for explicit messages in an OpenCode session."""
from __future__ import annotations
import json
import subprocess
import sys
import time

SESSION = sys.argv[1] if len(sys.argv) > 1 else "ses_e5658d56bffe1Gvg3OMeBleaeq"
OPENCODE = r"C:\Users\phsra\AppData\Roaming\npm\opencode.cmd"
seen = set()
header_shown = False
colors = {"user": "\x1b[36m", "assistant": "\x1b[35m", "tool": "\x1b[33m"}
reset = "\x1b[0m"

def read_export():
    p = subprocess.run([OPENCODE, "export", SESSION], capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=30)
    start = p.stdout.find("{")
    if start < 0:
        raise RuntimeError(p.stderr.strip() or "export sem JSON")
    return json.loads(p.stdout[start:])

def show(kind, sender, recipient, text, ident):
    if not text or ident in seen:
        return
    seen.add(ident)
    print(f"{colors.get(kind, '')}[{sender} -> {recipient}]{reset}")
    print(text)
    print("-" * 80, flush=True)

print(f"OPENCODE SESSION MONITOR: {SESSION}", flush=True)
print("Mostrando apenas mensagens explícitas e ferramentas; reasoning interno é omitido.", flush=True)
while True:
    try:
        data = read_export()
        info = data.get("info", {})
        global_header = f"Sessão: {info.get('title', SESSION)} | modelo: {info.get('model', {}).get('id', '?')} | diretório: {info.get('directory', '?')}"
        if not header_shown:
            print(global_header, flush=True)
            header_shown = True
        for message in data.get("messages", []):
            role = message.get("info", {}).get("role", "assistant")
            sender = "usuário" if role == "user" else "opencode"
            for part in message.get("parts", []):
                pid = part.get("id") or f"{message.get('info', {}).get('id')}:{part.get('type')}"
                if part.get("type") == "text":
                    show("user" if role == "user" else "assistant", sender, "opencode" if role == "user" else "usuário", part.get("text", ""), pid)
                elif part.get("type") == "tool":
                    tool = part.get("tool", "tool")
                    state = part.get("state", {}).get("status", "")
                    show("tool", "opencode", tool, f"ferramenta: {tool}\nstatus: {state}", pid)
    except Exception as exc:
        print(f"[monitor] aguardando sessão: {exc}", flush=True)
        if header_shown and not any(
            (part.get("id") in seen) is False
            for message in data.get("messages", [])
            for part in message.get("parts", [])
            if part.get("type") in {"text", "tool"}
        ):
            print("[monitor] aguardando novas mensagens...", flush=True)
    time.sleep(3)
