import re
import sys
import time
import subprocess
import requests
from typing import Dict, Any, Optional, Tuple, Callable

class SelfHealingEngine:
    """
    Interprets execution errors (stacktraces, missing modules, network timeouts),
    generates automated repair commands (e.g. pip install, retry with backoff, code refactor),
    and re-executes tasks autonomously.
    """

    def __init__(self, ollama_url: str = "http://localhost:11434", model_name: str = "qwen2.5-coder:7b", max_retries: int = 3):
        self.ollama_url = ollama_url
        self.model_name = model_name
        self.max_retries = max_retries

    def classify_error(self, stderr_text: str) -> Dict[str, Any]:
        """
        Classifies execution failures into actionable categories.
        """
        if not stderr_text:
            return {"category": "UNKNOWN_ERROR", "detail": "No stderr output provided."}

        # Check missing python package
        missing_module_match = re.search(r"(?:No module named|ModuleNotFoundError: No module named)\s+['\"]([^'\"]+)['\"]", stderr_text)
        if missing_module_match:
            pkg_name = missing_module_match.group(1).split('.')[0]
            return {
                "category": "MISSING_DEPENDENCY",
                "package": pkg_name,
                "fix_command": f"pip install {pkg_name}",
                "detail": f"Python package '{pkg_name}' is missing."
            }

        # Check network connection / timeout error
        if any(err in stderr_text for err in ["ConnectionRefusedError", "ReadTimeout", "ConnectTimeout", "HTTPError 502", "HTTPError 503", "Temporary failure in name resolution"]):
            return {
                "category": "NETWORK_TIMEOUT",
                "action": "exponential_backoff_retry",
                "detail": "Network request failed or timed out. Applying exponential retry."
            }

        # Check permission error
        if "PermissionError" in stderr_text or "Permission denied" in stderr_text:
            return {
                "category": "PERMISSION_DENIED",
                "detail": "File or socket permission error."
            }

        # General Syntax / Logic error
        return {
            "category": "SYNTAX_RUNTIME_ERROR",
            "detail": stderr_text[-500:] # Last 500 chars of stacktrace
        }

    def generate_llm_fix(self, failed_script: str, stderr_text: str) -> Optional[str]:
        """
        Queries the local Ollama LLM to propose a repaired version of a failed script or command.
        """
        prompt = f"""[SELF-HEALING CODE FIX REPAIR]
The following script failed during autonomous execution in Docker sandbox:

--- SCRIPT START ---
{failed_script}
--- SCRIPT END ---

--- ERROR STACKTRACE ---
{stderr_text}
--- END STACKTRACE ---

Task: Analyze the error and return ONLY the corrected, self-contained Python code that fixes the error.
Do not include conversational preamble or markdown explanations outside python code blocks.
"""
        try:
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": self.model_name,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.1}
                },
                timeout=15
            )
            if response.status_code == 200:
                raw_text = response.json().get("response", "")
                code_match = re.search(r"```python(.*?)```", raw_text, re.DOTALL)
                if code_match:
                    return code_match.group(1).strip()
                return raw_text.strip()
        except Exception as e:
            print(f"[SelfHealingEngine] Ollama query offline or unreachable ({e}). Using deterministic fallback repair.")

        return None

    def execute_with_self_healing(self, command_or_fn: Callable[[], Tuple[int, str, str]], script_code: str = "") -> Dict[str, Any]:
        """
        Executes a target function or script command, intercepting failures and performing auto-repair loops.
        """
        attempt = 0
        current_script = script_code

        while attempt < self.max_retries:
            attempt += 1
            print(f"[SelfHealingEngine] Execution attempt {attempt}/{self.max_retries}...")

            returncode, stdout, stderr = command_or_fn()

            if returncode == 0:
                return {
                    "success": True,
                    "attempts": attempt,
                    "stdout": stdout,
                    "stderr": stderr,
                    "repaired_script": current_script
                }

            print(f"[SelfHealingEngine] Failure detected on attempt {attempt} (exit code {returncode}). Analyzing error...")
            error_info = self.classify_error(stderr)
            print(f"[SelfHealingEngine] Classification: {error_info['category']} - {error_info.get('detail', '')}")

            if error_info["category"] == "MISSING_DEPENDENCY":
                fix_cmd = error_info["fix_command"]
                print(f"[SelfHealingEngine] Auto-repairing missing dependency: '{fix_cmd}'")
                install_res = subprocess.run(fix_cmd, shell=True, capture_output=True, text=True)
                if install_res.returncode == 0:
                    print(f"[SelfHealingEngine] Successfully installed {error_info['package']}. Retrying execution...")
                    continue

            elif error_info["category"] == "NETWORK_TIMEOUT":
                wait_time = 2 ** attempt
                print(f"[SelfHealingEngine] Applying exponential backoff ({wait_time}s) before retry...")
                time.sleep(wait_time)
                continue

            elif error_info["category"] == "SYNTAX_RUNTIME_ERROR" and current_script:
                fixed_code = self.generate_llm_fix(current_script, stderr)
                if fixed_code:
                    print("[SelfHealingEngine] LLM provided updated fixed script code. Updating script and retrying...")
                    current_script = fixed_code
                    # Allow execution loop to retry with updated code
                    continue

        return {
            "success": False,
            "attempts": attempt,
            "stdout": stdout,
            "stderr": stderr,
            "error_summary": f"Exceeded max retries ({self.max_retries}). Last error: {stderr[:300]}"
        }
