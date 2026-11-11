#!/usr/bin/env python3
"""
PLAYBOOK 3: Relatório de Status Diário da Infraestrutura (Discord Webhook)
Lê os logs de infraestrutura gerados no dia, consolida métricas e dispara
um resumo formatado com status em cores diretamente para o webhook do Discord.
"""

import json
import os
import requests
from datetime import datetime
from typing import Dict, Any

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/mock/test")

def generate_and_send_status_report() -> Dict[str, Any]:
    print("📢 [Playbook - Discord Status] Lendo logs de infraestrutura do dia...")

    workspace = os.getenv("WORKSPACE_DIR", "/sandbox_workspace")
    logs_dir = os.path.join(workspace if os.path.exists(workspace) else ".", "logs")

    network_diag_path = os.path.join(logs_dir, "network_diag.json")
    agent_exec_path = os.path.join(logs_dir, "agent_execution.json")

    net_status = "UNKNOWN"
    endpoints_tested = 0
    if os.path.exists(network_diag_path):
        try:
            with open(network_diag_path, "r", encoding="utf-8") as f:
                net_data = json.load(f)
                net_status = net_data.get("overall_status", "STABLE")
                endpoints_tested = len(net_data.get("endpoints", []))
        except Exception:
            pass

    agent_status = "SUCCESS"
    attempts_taken = 1
    if os.path.exists(agent_exec_path):
        try:
            with open(agent_exec_path, "r", encoding="utf-8") as f:
                exec_data = json.load(f)
                agent_status = "SUCCESS" if exec_data.get("success") else "FAILED"
                attempts_taken = exec_data.get("attempts", 1)
        except Exception:
            pass

    status_icon = "🟢" if net_status == "STABLE" and agent_status == "SUCCESS" else "🟡"
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    # Discord Embed Payload
    embed_payload = {
        "username": "Agente Autônomo de Infraestrutura",
        "avatar_url": "https://cdn-icons-png.flaticon.com/512/2092/2092663.png",
        "embeds": [
            {
                "title": f"{status_icon} Relatório Diário de Infraestrutura & Agente",
                "description": "Resumo consolidade das execuções de automação e verificação de saúde dos sistemas.",
                "color": 3066993 if status_icon == "🟢" else 15844367,
                "fields": [
                    {
                        "name": "📡 Conectividade e VPN PGFN",
                        "value": f"**Status:** `{net_status}`\n**Endpoints Testados:** `{endpoints_tested}`",
                        "inline": True
                    },
                    {
                        "name": "🤖 Agente de Automação",
                        "value": f"**Execução:** `{agent_status}`\n**Tentativas (Self-Healing):** `{attempts_taken}`",
                        "inline": True
                    },
                    {
                        "name": "⚙️ Ambiente Execution Sandbox",
                        "value": "Docker Isolated Container (Cap Drop: ALL, Read-Only Rootfs)",
                        "inline": False
                    }
                ],
                "footer": {
                    "text": f"Ollama Qwen2.5-Coder • Open Interpreter Engine • {now_str}"
                }
            }
        ]
    }

    print(f" -> Disparando notificação para o Discord Webhook ({DISCORD_WEBHOOK_URL[:30]}...)...")

    response_info = {"status": "SKIPPED_MOCK", "http_code": 200}

    if "mock" not in DISCORD_WEBHOOK_URL:
        try:
            resp = requests.post(DISCORD_WEBHOOK_URL, json=embed_payload, timeout=5)
            response_info = {"status": "SENT", "http_code": resp.status_code}
            print(f"✅ Webhook enviado com sucesso (HTTP {resp.status_code})")
        except Exception as e:
            response_info = {"status": "FAILED", "error": str(e)}
            print(f"⚠️ Falha ao disparar webhook para Discord ({e})")
    else:
        print("ℹ️ Webhook mock detectado. Simulação concluída com sucesso sem envio HTTP externo.")

    report_result = {
        "timestamp": now_str,
        "net_status": net_status,
        "agent_status": agent_status,
        "webhook_delivery": response_info,
        "payload": embed_payload
    }

    return report_result

if __name__ == "__main__":
    generate_and_send_status_report()
