import json
import os
import re
from typing import Tuple, List, Dict, Any

class SecurityGuardrails:
    """
    Enforces security policies, command blacklists, path isolation, and credential masking
    for the autonomous execution agent.
    """

    def __init__(self, config_path: str = "config/security_guardrails.json"):
        self.config_path = config_path
        self.blacklisted_commands: List[str] = []
        self.restricted_paths: List[str] = []
        self.secret_patterns: List[str] = []
        self.allowed_workspace: str = "/sandbox_workspace"
        self.masked_replacement: str = "[REDACTED_SECRET]"
        self._load_config()

    def _load_config(self) -> None:
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    rules = data.get("guardrails", {})
                    self.blacklisted_commands = rules.get("blacklisted_commands", [])
                    self.restricted_paths = rules.get("restricted_system_paths", [])
                    self.secret_patterns = rules.get("secret_patterns", [])
                    self.allowed_workspace = rules.get("allowed_workspace", "/sandbox_workspace")
                    self.masked_replacement = rules.get("masked_replacement", "[REDACTED_SECRET]")
            except Exception as e:
                print(f"[SecurityGuardrails] Warning: Failed to load config ({e}). Using strict defaults.")
                self._apply_strict_defaults()
        else:
            self._apply_strict_defaults()

    def _apply_strict_defaults(self) -> None:
        self.blacklisted_commands = [
            "rm -rf /", "rm -rf /*", "mkfs", "dd if=", ":(){ :|:& };:", "chmod -R 777 /", "shutdown", "reboot"
        ]
        self.restricted_paths = ["/etc", "/usr", "/boot", "/var/log", "/root", "/proc", "/sys"]
        self.secret_patterns = [
            r"FIGMA_[A-Z0-9_]*",
            r"DISCORD_WEBHOOK_[A-Z0-9_]*",
            r"https://discord\.com/api/webhooks/[0-9]+/[a-zA-Z0-9_-]+"
        ]

    def validate_command(self, command: str) -> Tuple[bool, str]:
        """
        Validates whether a command is safe to execute.
        Returns (is_safe, rejection_reason).
        """
        if not command or not command.strip():
            return False, "Command is empty."

        cmd_lower = command.lower().strip()

        # Check blacklisted commands
        for blacklisted in self.blacklisted_commands:
            if blacklisted.lower() in cmd_lower:
                return False, f"Security Violation: Command contains prohibited operation '{blacklisted}'."

        # Check restricted path modifications
        for restricted in self.restricted_paths:
            # Match attempts to delete or alter restricted system directories
            pattern = rf"(rm|mv|cp|chmod|chown)\s+.*{re.escape(restricted)}"
            if re.search(pattern, cmd_lower):
                return False, f"Security Violation: Attempted unauthorized file operation on system directory '{restricted}'."

        return True, "Command validated successfully."

    def enforce_sandbox_path(self, target_path: str) -> bool:
        """
        Verifies that a given file path is strictly within the allowed workspace sandbox.
        """
        try:
            abs_workspace = os.path.abspath(self.allowed_workspace)
            abs_target = os.path.abspath(target_path)
            # Allow /tmp for temporary sandbox files
            if abs_target.startswith("/tmp") or abs_target.startswith("/workspace") or abs_target.startswith(abs_workspace):
                return True
            return False
        except Exception:
            return False

    def sanitize_output(self, text: str) -> str:
        """
        Masks API tokens, webhook URLs, and secrets in logs and terminal stdout/stderr outputs.
        """
        if not text:
            return ""

        sanitized = text

        # Mask environment variable secret values if present in process environment
        sensitive_keys = ["FIGMA_TOKEN", "DISCORD_WEBHOOK_URL", "API_KEY", "SECRET_KEY", "PASSWORD"]
        for key in sensitive_keys:
            val = os.environ.get(key)
            if val and len(val) > 4:
                sanitized = sanitized.replace(val, self.masked_replacement)

        # Mask regex matching patterns
        for pattern in self.secret_patterns:
            try:
                sanitized = re.sub(pattern, self.masked_replacement, sanitized)
            except Exception:
                pass

        return sanitized
