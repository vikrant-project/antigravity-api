"""Comprehensive Integration Test Suite for Antigravity Direct API.
Validates authentication, Gemini 3.8 Flash tiers, Claude, and OpenAI adapter.
"""

import sys
import unittest
from antigravity_api.auth import TokenManager
from antigravity_api.client import AntigravityClient
from antigravity_api.adapters.openai_adapter import OpenAIAdapter
from antigravity_api.models import AVAILABLE_MODELS, resolve_model_id


class TestAntigravityAPI(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        print("\n================== TESTING ALL ANTIGRAVITY DIRECT MODELS ==================")
        cls.token_mgr = TokenManager(auto_refresh_loop=False)
        cls.client = AntigravityClient(token_manager=cls.token_mgr)
        cls.openai_adapter = OpenAIAdapter(cls.client)

    def test_01_token_discovery_and_refresh(self):
        print("\n[Test 1] Testing Token Discovery & Refresh...")
        self.assertIsNotNone(self.token_mgr.access_token, "Access token must be loaded")
        self.assertIsNotNone(self.token_mgr.refresh_token, "Refresh token must be present")
        print(f"  Authenticated User: {self.token_mgr.user_email}")
        refreshed = self.token_mgr.refresh()
        self.assertTrue(refreshed, "OAuth token refresh should succeed")
        print("  Token refresh verified successfully!")

    def test_02_gemini_3_8_flash_high(self):
        print("\n[Test 2] Testing Gemini 3.8 Flash (High)...")
        result = self.client.generate_content(
            model="gemini-3.8-flash-high",
            prompt="Respond with: GEMINI_3_8_FLASH_HIGH_VERIFIED"
        )
        print(f"  Model: {result.get('model')}")
        print(f"  Response: {result.get('text', '').strip()[:80]}")
        self.assertIn("GEMINI_3_8_FLASH_HIGH_VERIFIED", result.get("text", ""))

    def test_03_gemini_3_8_flash_medium(self):
        print("\n[Test 3] Testing Gemini 3.8 Flash (Medium)...")
        result = self.client.generate_content(
            model="gemini-3.8-flash-medium",
            prompt="Respond with: GEMINI_3_8_FLASH_MEDIUM_VERIFIED"
        )
        print(f"  Model: {result.get('model')}")
        print(f"  Response: {result.get('text', '').strip()[:80]}")
        self.assertIn("GEMINI_3_8_FLASH_MEDIUM_VERIFIED", result.get("text", ""))

    def test_04_gemini_3_8_flash_low(self):
        print("\n[Test 4] Testing Gemini 3.8 Flash (Low)...")
        result = self.client.generate_content(
            model="gemini-3.8-flash-low",
            prompt="Respond with: GEMINI_3_8_FLASH_LOW_VERIFIED"
        )
        print(f"  Model: {result.get('model')}")
        print(f"  Response: {result.get('text', '').strip()[:80]}")
        self.assertIn("GEMINI_3_8_FLASH_LOW_VERIFIED", result.get("text", ""))

    def test_05_claude_sonnet_4_6(self):
        print("\n[Test 5] Testing Claude Sonnet 4.6 (Thinking)...")
        result = self.client.generate_content(
            model="claude-sonnet-4-6",
            prompt="Respond with: CLAUDE_SONNET_ONLINE"
        )
        print(f"  Model: {result.get('model')}")
        print(f"  Response: {result.get('text', '').strip()[:80]}")
        self.assertIn("CLAUDE_SONNET_ONLINE", result.get("text", ""))

    def test_06_openai_adapter_gemini_3_8(self):
        print("\n[Test 6] Testing OpenAI Adapter with Gemini 3.8 Flash...")
        req = {
            "model": "gemini-3.8-flash",
            "messages": [
                {"role": "user", "content": "Respond with: OPENAI_ADAPTER_3_8_OK"}
            ],
            "temperature": 0.5
        }
        res = self.openai_adapter.chat_completion_sync(req)
        content = res["choices"][0]["message"]["content"]
        print(f"  Model in response: {res.get('model')}")
        print(f"  Content: {content.strip()[:80]}")
        self.assertIn("OPENAI_ADAPTER_3_8_OK", content)


if __name__ == "__main__":
    unittest.main()
