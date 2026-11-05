"""Visible message relay for a small Doctor Mesh agent conversation.

This layer records explicit prompts, responses and tool names. It does not
attempt to expose private model reasoning.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "agent-mesh-chat.jsonl"
MODEL = "opencode/nemotron-3.5-super-vl-free"
OPENCODE = r"C:\Users\phsra\AppData\Roaming\npm\opencode.cmd"
ROLES = {
    "delegado": ("\x1b[31m", "mesh-orchestrator"),
    "geometria": ("\x1b[34m", "mesh-geometry"),
    "qualidade": ("\x1b[32m", "mesh-quality"),
    "testes": ("\x1b[33m", "mesh-test"),
}
RESET = "\x1b[0m"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def emit(sender: str, recipient: str, text: str, kind: str = "message") -> None:
    record = {
        "time": datetime.now(timezone.utc).isoformat(),
        "sender": sender,
        "recipient": recipient,
        "kind": kind,
        "text": text,
    }
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    color = ROLES.get(sender, ("", ""))[0]
    print(f"{color}[{sender} -> {recipient}]{RESET} {text}\n", flush=True)


def run_agent(agent: str, prompt: str) -> tuple[str, list[str]]:
    command = [
        OPENCODE, "run", "--model", MODEL, "--agent", agent,
        "--dir", str(ROOT), "--format", "json", prompt,
    ]
    result = subprocess.run(command, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=240)
    texts: list[str] = []
    tools: list[str] = []
    for line in result.stdout.splitlines():
        try:
            item = json.loads(line)
            part = item.get("part", {})
            if part.get("type") == "text" and part.get("text"):
                texts.append(part["text"])
            if part.get("type") == "tool":
                tool = part.get("tool")
                if tool:
                    tools.append(tool)
        except json.JSONDecodeError:
            continue
    if result.returncode and not texts:
        texts.append(f"Falha ao executar o agente (código {result.returncode}): {result.stderr[-1000:]}")
    return "\n".join(texts).strip() or "Sem resposta textual.", tools


def ask(sender: str, recipient: str, agent: str, prompt: str) -> str:
    emit(sender, recipient, prompt, "delegation" if sender == "delegado" else "message")
    answer, tools = run_agent(agent, prompt)
    if tools:
        emit(recipient, sender, f"[ferramentas: {', '.join(tools)}]", "tools")
    emit(recipient, sender, answer, "response")
    return answer


def main() -> int:
    parser = argparse.ArgumentParser(description="Conversa visível entre agentes do Doctor Mesh")
    parser.add_argument("task", nargs="?", default="Revise o cálculo central do Doctor Mesh e explique como a malha 3D influencia o resultado.")
    args = parser.parse_args()
    LOG.write_text("", encoding="utf-8")
    emit("sistema", "todos", f"Início da rodada. Projeto: {ROOT}", "system")

    answers: dict[str, str] = {}
    answers["geometria"] = ask("delegado", "geometria", ROLES["geometria"][1],
        f"Tarefa do delegado: {args.task}\nAnalise somente geometria e fórmulas. Liste arquivos lidos, evidências e dúvidas.")
    answers["qualidade"] = ask("delegado", "qualidade", ROLES["qualidade"][1],
        f"Tarefa do delegado: {args.task}\nAnalise somente gates de qualidade, validações e riscos. Liste arquivos lidos e evidências.")
    answers["testes"] = ask("delegado", "testes", ROLES["testes"][1],
        f"Tarefa do delegado: {args.task}\nLocalize testes relevantes. Liste comandos reproduzíveis, pré-requisitos e resultados esperados.")

    peer_context = "\n\n".join(f"RELATÓRIO {name.upper()}:\n{text[:5000]}" for name, text in answers.items())
    for name, agent in (("geometria", ROLES["geometria"][1]), ("qualidade", ROLES["qualidade"][1]), ("testes", ROLES["testes"][1])):
        ask(name, "todos", agent,
            "Leia as mensagens dos outros agentes abaixo e responda apenas com concordâncias, correções ou perguntas explícitas.\n\n" + peer_context)

    final_prompt = f"Você é o delegado. Sintetize a conversa abaixo sobre: {args.task}\nMostre decisões, divergências e próximos passos. Não edite arquivos.\n\n{peer_context}"
    ask("delegado", "usuário", ROLES["delegado"][1], final_prompt)
    emit("sistema", "usuário", f"Fim da rodada. Histórico salvo em {LOG}", "system")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
