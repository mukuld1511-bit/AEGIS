"""Test verifying Claude-style iterative editing, context recall, and per-node vault storage.
"""
import unittest
import os
import shutil
from aegis_core.session_memory import SessionMemory

class TestClaudeStyleContextMemory(unittest.TestCase):
    def setUp(self):
        self.test_vault = "test_storage_vault"
        self.memory = SessionMemory(storage_vault_root=self.test_vault)

    def tearDown(self):
        if os.path.exists(self.test_vault):
            shutil.rmtree(self.test_vault)

    def test_iterative_file_editing_and_recall(self):
        session_id = "test_iterative_session"

        # Turn 1: Initial creation
        self.memory.add_user_message(session_id, "Create math_utils.py with add function")
        initial_code = "def add(a, b):\n    return a + b\n"
        rec1 = self.memory.save_or_update_file(session_id, "math_utils.py", initial_code, "dgx-node-1")
        self.assertEqual(rec1["version"], 1)

        # Turn 2: Follow-up edit prompt ("Now add multiply function")
        prompt_with_context = self.memory.build_context_prompt_for_dgx(session_id, "Now add multiply function to math_utils.py")
        
        # Verify that previous code is recalled and embedded in prompt
        self.assertIn("EXISTING WORKSPACE FILES", prompt_with_context)
        self.assertIn("def add(a, b):", prompt_with_context)
        self.assertIn("Version 1", prompt_with_context)

        # Updated code generated
        updated_code = "def add(a, b):\n    return a + b\n\ndef multiply(a, b):\n    return a * b\n"
        rec2 = self.memory.save_or_update_file(session_id, "math_utils.py", updated_code, "dgx-node-1")
        self.assertEqual(rec2["version"], 2)

        # Verify latest version content
        latest_content = self.memory.get_file_content(session_id, "math_utils.py")
        self.assertIn("def multiply(a, b):", latest_content)

if __name__ == "__main__":
    unittest.main()
