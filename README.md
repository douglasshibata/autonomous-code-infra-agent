# 🤖 Agente Autônomo de Código e Infraestrutura (Open Interpreter + Ollama)

Este repositório contém a arquitetura completa, as configurações containerizadas, o motor de execução e os playbooks de automação para um **Agente Executor de Código e Infraestrutura** operando **100% localmente e off-grid**.

---

## 📐 1. Arquitetura do Agente Executor

O diagrama ASCII abaixo descreve o fluxo de orquestração interativa, isolamento em sandbox e ciclo de auto-recuperação de erros (Self-Healing):

```
+-----------------------------------------------------------------------------------+
|                                 USUÁRIO (Terminal)                                |
|             Comando em Linguagem Natural / Chamada de Playbook                    |
+-----------------------------------------------------------------------------------+
                                          │
                                          ▼
+-----------------------------------------------------------------------------------+
|                     OPEN INTERPRETER (Orquestrador Local)                        |
|   - Carrega perfil de execução (`config/open_interpreter_config.yaml`)            |
|   - Aplica System Prompt (`config/system_prompt.txt`)                             |
|   - Valida comandos contra Guardrails (`core/security.py`)                        |
+-----------------------------------------------------------------------------------+
                                    │           ▲
                       Prompt / Task│           │ Código Gerado
                                    ▼           │
+-----------------------------------------------------------------------------------+
|                        OLLAMA ENGINE (LLM Local Privada)                          |
|   - Modelo Especializado: `qwen2.5-coder:7b` ou `llama3`                         |
|   - Endpoint HTTP: `http://ollama:11434`                                          |
|   - Garantia: Zero dados ou tokens enviados para APIs externas                     |
+-----------------------------------------------------------------------------------+
                                          │
                            Código Python/Bash Aprovado
                                          │
                                          ▼
+-----------------------------------------------------------------------------------+
|                  CONTAINER DOCKER SANDBOX (Execução Segura)                       |
|   - Imagem: `python:3.12-slim` (User `agentuser` UID 1000)                        |
|   - Restrições: `read_only: true`, `cap_drop: ALL`, tmpfs `/tmp`                  |
|   - Diretório Isolado: `/sandbox_workspace`                                       |
+-----------------------------------------------------------------------------------+
                                          │
                            Retorno Stdout / Stderr / Exit Code
                                          │
                        ┌─────────────────┴─────────────────┐
                        │                                   │
              Exit Code = 0 (Sucesso)                    Exit Code != 0 (Erro)
                        │                                   │
                        ▼                                   ▼
          +---------------------------+       +------------------------------------+
          | LOGS E RESULTADOS         |       | MOTOR DE SELF-HEALING              |
          | - `/sandbox_workspace/`   |       | - Classifica Erro (Missing Pkg,    |
          | - `network_diag.json`     |       |   Network Timeout, Syntax)         |
          | - `sync_manifest.json`    |       | - Injeta Fix (`pip install`)       |
          | - `agent_execution.json`  |       | - Aplica Retry / Re-gera Código    |
          +---------------------------+       +------------------------------------+
                                                                │
                                                                └─► Re-executa até 3x
```

---

## 🛠️ 2. Stack Tecnológica & Configuração do Ambiente Local

### Stack Principal:
- **Motor de Orquestração:** Open Interpreter CLI / Engine.
- **LLM Engine Local:** Ollama rodando `qwen2.5-coder:7b` ou `llama3`.
- **Ambiente Isolado (Sandbox):** Docker Containers com restrição de privilégios (`cap_drop: ALL`, `read_only: true`).
- **Linguagens de Automação:** Python 3.12 e Bash Shell Scripting.
- **Integrações Nativas:** APIs REST (Figma), Webhooks (Discord), utilitários de rede (`ping`, `socket`, `ip route`).

### Arquivos de Configuração:

1. **`docker-compose.yml`**: Orquestra o servidor Ollama, o serviço autônomo de download de modelo (`ollama-init`), o orquestrador Open Interpreter e o container executor de sandbox.
2. **`config/system_prompt.txt`**: Define as instruções do agente para execução não-interativa (*headless*), logging estruturado e masking de credenciais.
3. **`config/open_interpreter_config.yaml`**: Parâmetros de execução do Open Interpreter amarrados ao Ollama local.
4. **`config/security_guardrails.json`**: Blacklist de comandos destrutivos, isolamento de sistema de arquivos e expressões regulares para mascarar segredos.

---

## 📦 3. Casos de Uso e Playbooks de Automação

### 📡 Playbook 1: Automação de Rede e VPN PGFN (`playbooks/network_vpn_check.py`)
- **Objetivo:** Inspeciona interfaces de rede, rotas e testa a estabilidade da conexão para endpoints da Procuradoria-Geral da Fazenda Nacional (PGFN).
- **Execução:**
  ```bash
  python3 core/orchestrator.py --playbook playbooks/network_vpn_check.py
  ```
- **Entregáveis:** Produz `/sandbox_workspace/logs/network_diag.json` e `/sandbox_workspace/logs/network_diag.md`.

### 🎨 Playbook 2: Sincronização de Assets do Figma SIPAF (`playbooks/figma_sipaf_sync.py`)
- **Objetivo:** Conecta à API REST do Figma usando `FIGMA_TOKEN`, consulta atualizações do arquivo de design do projeto SIPAF e organiza os ícones e componentes baixados.
- **Execução:**
  ```bash
  python3 core/orchestrator.py --playbook playbooks/figma_sipaf_sync.py
  ```
- **Entregáveis:** Estrutura pastas `/sandbox_workspace/assets/sipaf/icons/`, `/sandbox_workspace/assets/sipaf/components/` e o manifesto `sync_manifest.json`.

### 📢 Playbook 3: Relatório Diário de Status no Discord (`playbooks/discord_status_report.py`)
- **Objetivo:** Consolida os logs de infraestrutura e execução gerados durante o dia, formata um resumo com indicadores visuais (`🟢` / `🟡` / `🔴`) e dispara uma notificação formatada para o webhook da daily no Discord.
- **Execução:**
  ```bash
  python3 core/orchestrator.py --playbook playbooks/discord_status_report.py
  ```

---

## 🔄 4. Mecanismo de Recuperação de Erro (Self-Healing)

O módulo `core/self_healing.py` intercepta falhas do terminal (códigos de saída Unix `!= 0`) e executa o seguinte fluxo autônomo:

1. **Captura do Stacktrace:** Analisa `stderr` e identifica o tipo da falha.
2. **Classificação Automática:**
   - `MISSING_DEPENDENCY` (`ModuleNotFoundError`): Extrai o nome do pacote e executa automaticamente `pip install <pacote>`.
   - `NETWORK_TIMEOUT`: Aplica retry com tempo de espera em backoff exponencial ($2^{tentativa}$ segundos).
   - `SYNTAX_RUNTIME_ERROR`: Submete o código com falha e o erro para o modelo local `qwen2.5-coder:7b` via Ollama solicitando o patch corrigido.
3. **Re-execução Segura:** Re-executa o script corrigido até o limite configurado (padrão: 3 tentativas).

---

## 🛡️ 5. Guia de Segurança e Guardrails

O módulo `core/security.py` garante que o agente nunca comprometa a máquina host:

1. **Bloqueio de Comandos Perigosos:** Impede a execução de `rm -rf /`, `mkfs`, `dd`, `chmod 777 /`, desligamento do sistema ou tentativas de bind de shell reversa.
2. **Isolamento em Sandbox:** Toda gravação de arquivos é restrita ao diretório `/sandbox_workspace`.
3. **Sanitização e Masking de Credenciais:** Antes de exibir logs ou saídas do terminal, o agente substitui chaves sensíveis (`FIGMA_TOKEN`, `DISCORD_WEBHOOK_URL`, tokens JWT) pela string `[REDACTED_SECRET]`.
4. **Ambiente Não-Raiz no Docker:** O container roda com usuário sem privilégios (`agentuser` UID 1000) e capacidades Linux removidas (`cap_drop: ALL`).

---

## 🧪 6. Como Executar e Validar

### Subir o Ambiente Containerizado via Docker Compose:
```bash
docker-compose up -d --build
```

### Executar a Suíte Completa de Testes Automatizados:
```bash
PYTHONPATH=. python3 -m pytest tests/ -v
```

Output esperado dos testes:
```text
tests/test_agent.py::TestAutonomousAgent::test_orchestrator_playbook_execution PASSED
tests/test_agent.py::TestAutonomousAgent::test_playbook_discord_status_report PASSED
tests/test_agent.py::TestAutonomousAgent::test_playbook_figma_sipaf_sync PASSED
tests/test_agent.py::TestAutonomousAgent::test_playbook_network_vpn_check PASSED
tests/test_agent.py::TestAutonomousAgent::test_security_guardrails_command_validation PASSED
tests/test_agent.py::TestAutonomousAgent::test_security_guardrails_secret_masking PASSED
tests/test_agent.py::TestAutonomousAgent::test_self_healing_error_classification PASSED
tests/test_agent.py::TestAutonomousAgent::test_self_healing_execution_success PASSED
```
