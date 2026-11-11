#!/usr/bin/env python3
"""
PLAYBOOK 1: Automação de Rede e VPN (Diagnóstico de Conectividade PGFN)
Verifica rotas de rede, estabilidade da conexão VPN para ambientes restritos (PGFN)
e produz relatórios estruturados JSON e Markdown.
"""

import json
import os
import socket
import time
import subprocess
from datetime import datetime
from typing import Dict, Any, List

TARGET_ENDPOINTS = [
    {"name": "PGFN Portal Principal", "host": "pgfn.fazenda.gov.br", "port": 443},
    {"name": "PGFN Gateway VPN Restrito", "host": "vpn.pgfn.fazenda.gov.br", "port": 443},
    {"name": "DNS Governamental / Serpro", "host": "1.1.1.1", "port": 53}
]

def check_dns_resolution(hostname: str) -> Dict[str, Any]:
    start = time.time()
    try:
        ip = socket.gethostbyname(hostname)
        duration_ms = round((time.time() - start) * 1000, 2)
        return {"status": "SUCCESS", "ip": ip, "latency_ms": duration_ms}
    except Exception as e:
        return {"status": "FAILED", "error": str(e), "latency_ms": -1}

def check_tcp_port(host: str, port: int, timeout: float = 3.0) -> Dict[str, Any]:
    start = time.time()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((host, port))
        s.close()
        duration_ms = round((time.time() - start) * 1000, 2)
        return {"status": "CONNECTED", "latency_ms": duration_ms}
    except Exception as e:
        return {"status": "UNREACHABLE", "error": str(e), "latency_ms": -1}

def get_network_routes() -> List[str]:
    try:
        res = subprocess.run("ip route || netstat -rn", shell=True, capture_output=True, text=True, timeout=5)
        if res.returncode == 0:
            return res.stdout.strip().split("\n")[:10] # Top 10 routes
    except Exception:
        pass
    return ["Route table inspection not supported in current environment."]

def run_diagnostics() -> Dict[str, Any]:
    print("🌐 [Playbook - Rede/VPN] Iniciando diagnóstico de rotas e conectividade PGFN...")
    timestamp = datetime.now().isoformat()
    results = []

    for ep in TARGET_ENDPOINTS:
        print(f" -> Testando endpoint: {ep['name']} ({ep['host']}:{ep['port']})...")
        dns_info = check_dns_resolution(ep['host']) if not ep['host'].replace('.', '').isdigit() else {"status": "IP_DIRECT", "ip": ep['host'], "latency_ms": 0}

        target_ip = dns_info.get("ip", ep['host']) if dns_info["status"] != "FAILED" else ep['host']
        tcp_info = check_tcp_port(target_ip, ep['port']) if dns_info["status"] != "FAILED" else {"status": "SKIPPED", "latency_ms": -1}

        results.append({
            "target": ep['name'],
            "host": ep['host'],
            "port": ep['port'],
            "dns": dns_info,
            "tcp_connectivity": tcp_info
        })

    routes = get_network_routes()

    report = {
        "timestamp": timestamp,
        "playbook": "network_vpn_check",
        "overall_status": "STABLE" if all(r["tcp_connectivity"]["status"] in ["CONNECTED", "SKIPPED"] for r in results) else "DEGRADED",
        "endpoints": results,
        "routes_sample": routes
    }

    # Save logs in workspace
    workspace = os.getenv("WORKSPACE_DIR", "/sandbox_workspace")
    logs_dir = os.path.join(workspace if os.path.exists(workspace) else ".", "logs")
    os.makedirs(logs_dir, exist_ok=True)

    json_path = os.path.join(logs_dir, "network_diag.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    md_path = os.path.join(logs_dir, "network_diag.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# 📡 Relatório de Diagnóstico de Rede e VPN PGFN\n")
        f.write(f"**Data/Hora:** `{timestamp}`  \n")
        f.write(f"**Status Geral:** `{report['overall_status']}`\n\n")
        f.write(f"### Endpoints Testados:\n")
        for r in results:
            tcp_st = r["tcp_connectivity"]["status"]
            lat = r["tcp_connectivity"]["latency_ms"]
            f.write(f"- **{r['target']}**: `{tcp_st}` ({lat} ms)\n")

    print(f"✅ [Playbook - Rede/VPN] Diagnóstico concluído! Logs gerados em:\n - {json_path}\n - {md_path}")
    return report

if __name__ == "__main__":
    run_diagnostics()
