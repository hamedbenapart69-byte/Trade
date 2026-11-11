"""Unit tests for the detective policy guard."""
import importlib.util
from pathlib import Path
import unittest

SCRIPT = Path(__file__).with_name("policy_guard.py")
SPEC = importlib.util.spec_from_file_location("policy_guard", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class PolicyGuardTests(unittest.TestCase):
    def test_rejects_secret_like_paths(self):
        secret, _ = MODULE.classify_paths([
            ".env", "config/prod.env", "certs/server.pem", "config/secrets.prod",
            ".env.example", "README.md",
        ])
        self.assertEqual(secret, [".env", "config/prod.env", "certs/server.pem", "config/secrets.prod"])

    def test_detects_sensitive_workflow_changes(self):
        _, sensitive = MODULE.classify_paths([
            ".github/workflows/telegram-notify.yml",
            ".github/workflows/cloudflare-pages.yml",
            ".github/workflows/ci.yml",
        ])
        self.assertEqual(
            sensitive,
            [".github/workflows/telegram-notify.yml", ".github/workflows/cloudflare-pages.yml"],
        )

    def test_does_not_classify_docs_as_secret(self):
        secret, sensitive = MODULE.classify_paths(["docs/security-policy.md", "web/app.js"])
        self.assertEqual(secret, [])
        self.assertEqual(sensitive, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
