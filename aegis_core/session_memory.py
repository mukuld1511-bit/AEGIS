"""AEGIS Session Context & Memory Engine (Claude-style iterative editing).
Maintains conversational history, workspace file states, and versioned diffs across tasks.
Allows follow-up prompts to recall, inspect, and edit previously generated code and documents.
"""
import os
import json
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone

class SessionMemory:
    def __init__(self, storage_vault_root: str = "aegis_storage_vault"):
        self.storage_vault_root = storage_vault_root
        self.sessions: Dict[str, Dict[str, Any]] = {}
        os.makedirs(storage_vault_root, exist_ok=True)

    def get_or_create_session(self, session_id: str, assigned_node: str = "dgx-node-1") -> Dict[str, Any]:
        """Retrieves active session state or initializes a new one with isolated node storage."""
        if session_id not in self.sessions:
            node_dir = os.path.join(self.storage_vault_root, assigned_node, "workspaces", session_id)
            os.makedirs(node_dir, exist_ok=True)
            self.sessions[session_id] = {
                "session_id": session_id,
                "assigned_node": assigned_node,
                "workspace_path": node_dir,
                "messages": [],
                "files": {},  # {filename: {"content": ..., "version": 1, "path": ...}}
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
        return self.sessions[session_id]

    def add_user_message(self, session_id: str, prompt: str):
        session = self.get_or_create_session(session_id)
        session["messages"].append({
            "role": "user",
            "content": prompt,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        session["updated_at"] = datetime.now(timezone.utc).isoformat()

    def add_assistant_message(self, session_id: str, text: str, node_id: str):
        session = self.get_or_create_session(session_id)
        session["messages"].append({
            "role": "assistant",
            "node_id": node_id,
            "content": text,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        session["updated_at"] = datetime.now(timezone.utc).isoformat()

    def save_or_update_file(self, session_id: str, filename: str, content: str, node_id: str) -> Dict[str, Any]:
        """Saves a new file or creates an updated revision of an existing file."""
        session = self.get_or_create_session(session_id, assigned_node=node_id)
        node_workspace = os.path.join(self.storage_vault_root, node_id, "workspaces", session_id)
        os.makedirs(node_workspace, exist_ok=True)

        file_path = os.path.join(node_workspace, filename)
        version = 1

        if filename in session["files"]:
            version = session["files"][filename]["version"] + 1

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

        file_record = {
            "filename": filename,
            "file_path": file_path,
            "version": version,
            "size_bytes": len(content.encode("utf-8")),
            "last_modified_by": node_id,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        session["files"][filename] = file_record
        return file_record

    def get_file_content(self, session_id: str, filename: str) -> Optional[str]:
        """Retrieves existing content of a file for follow-up editing."""
        if session_id in self.sessions and filename in self.sessions[session_id]["files"]:
            fpath = self.sessions[session_id]["files"][filename]["file_path"]
            if os.path.exists(fpath):
                with open(fpath, "r", encoding="utf-8") as f:
                    return f.read()
        return None

    def build_context_prompt_for_dgx(self, session_id: str, latest_prompt: str) -> str:
        """Constructs Claude-style contextual prompt with previous conversation and existing file states."""
        session = self.get_or_create_session(session_id)
        context_parts = []

        # 1. Existing Workspace Files (if any)
        if session["files"]:
            context_parts.append("### EXISTING WORKSPACE FILES (Recall & Edit if requested):")
            for fname in session["files"]:
                content = self.get_file_content(session_id, fname)
                if content:
                    context_parts.append(f"\n--- File: `{fname}` (Version {session['files'][fname]['version']}) ---\n```\n{content}\n```")

        # 2. Recent Conversation History (up to last 6 turns)
        recent_msgs = session["messages"][-6:]
        if recent_msgs:
            context_parts.append("\n### RECENT CONVERSATION HISTORY:")
            for msg in recent_msgs:
                role = "User" if msg["role"] == "user" else f"Assistant ({msg.get('node_id', 'DGX')})"
                context_parts.append(f"{role}: {msg['content']}")

        # 3. Latest Instruction
        context_parts.append(f"\n### CURRENT USER INSTRUCTION:\n{latest_prompt}")
        context_parts.append("\nINSTRUCTION TO MODEL: If modifying an existing file, output the updated full implementation or clean edits.")

        return "\n".join(context_parts)
