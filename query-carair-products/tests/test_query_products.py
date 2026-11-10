from __future__ import annotations

import contextlib
import importlib.util
import io
import os
from pathlib import Path
import unittest
from unittest import mock


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "query_products.py"
SPEC = importlib.util.spec_from_file_location("query_products", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
query_products = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(query_products)


class ResolveTokenTests(unittest.TestCase):
    def test_missing_credential_fails_before_request(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch.object(query_products.platform, "system", return_value="Darwin"):
                with mock.patch.object(query_products, "keychain_token", return_value=""):
                    with self.assertRaisesRegex(ValueError, "API token is not configured"):
                        query_products.validated_config(15)

    def test_environment_token_has_precedence(self) -> None:
        with mock.patch.dict(os.environ, {"CAR_AIR_CODEX_API_TOKEN": "env-token"}, clear=False):
            with mock.patch.object(query_products, "windows_credential_token") as windows_token:
                token, source = query_products.resolve_token()

        self.assertEqual(token, "env-token")
        self.assertEqual(source, "environment")
        windows_token.assert_not_called()

    def test_macos_keychain_fallback(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch.object(query_products.platform, "system", return_value="Darwin"):
                with mock.patch.object(query_products, "keychain_token", return_value="mac-token"):
                    token, source = query_products.resolve_token()

        self.assertEqual(token, "mac-token")
        self.assertEqual(source, "macos_keychain")

    def test_windows_credential_manager_fallback(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch.object(query_products.platform, "system", return_value="Windows"):
                with mock.patch.object(
                    query_products, "windows_credential_token", return_value="windows-token"
                ):
                    token, source = query_products.resolve_token()

        self.assertEqual(token, "windows-token")
        self.assertEqual(source, "windows_credential_manager")

    def test_missing_windows_credential_has_platform_specific_error(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch.object(query_products.platform, "system", return_value="Windows"):
                with mock.patch.object(query_products, "windows_credential_token", return_value=""):
                    with self.assertRaisesRegex(ValueError, "Windows Credential Manager"):
                        query_products.resolve_token()


class ConfigureCredentialTests(unittest.TestCase):
    def test_windows_configuration_saves_without_printing_token(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with mock.patch.object(query_products.platform, "system", return_value="Windows"):
            with mock.patch.object(query_products.getpass, "getpass", return_value="secret-value"):
                with mock.patch.object(query_products, "save_windows_credential") as save_credential:
                    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                        result = query_products.configure_credential()

        self.assertEqual(result, 0)
        save_credential.assert_called_once_with("secret-value")
        self.assertNotIn("secret-value", stdout.getvalue())
        self.assertNotIn("secret-value", stderr.getvalue())
        self.assertIn("windows_credential_manager", stdout.getvalue())

    def test_configure_keychain_remains_macos_only(self) -> None:
        stdout = io.StringIO()
        with mock.patch.object(query_products.platform, "system", return_value="Windows"):
            with contextlib.redirect_stdout(stdout):
                result = query_products.configure_keychain()

        self.assertEqual(result, 2)
        self.assertIn("only available on macOS", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
