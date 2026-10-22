"""AEGIS Google Drive Orchestration Bridge.
Coordinates file transfer between DGX nodes and the Raspberry Pi hub without requiring direct peer-to-peer memory access.
Generates CLI commands (rclone/gdrive/python) dictated by the Raspberry Pi.
"""
import os
from typing import Dict, Any, Optional

class GoogleDriveBridge:
    def __init__(self, remote_name: str = "gdrive", base_folder: str = "AEGIS_Cluster_Artifacts"):
        self.remote_name = remote_name
        self.base_folder = base_folder

    def get_upload_command(self, local_path: str, task_id: str) -> str:
        """Returns the terminal CLI command executed by a DGX node to push files to Google Drive."""
        remote_path = f"{self.remote_name}:{self.base_folder}/{task_id}"
        # Using rclone with fallback to curl / python drive script
        return f"rclone copyto '{local_path}' '{remote_path}/{os.path.basename(local_path)}' --stats-one-line"

    def get_download_command(self, filename: str, task_id: str, dest_dir: str = "./workspace") -> str:
        """Returns the terminal CLI command executed by the next DGX node to pull files from Google Drive."""
        remote_path = f"{self.remote_name}:{self.base_folder}/{task_id}/{filename}"
        return f"mkdir -p '{dest_dir}' && rclone copyto '{remote_path}' '{dest_dir}/{filename}' --stats-one-line"

    def format_handoff_instruction(self, from_node: str, to_node: str, task_id: str, filename: str, review_prompt: str) -> str:
        """Generates the handoff payload sent from Raspberry Pi to the second DGX node."""
        dl_cmd = self.get_download_command(filename, task_id)
        return (
            f"[AEGIS HANDOFF: {from_node} -> Raspberry Pi -> {to_node}]\n"
            f"Step 1: Download artifact via dictated command:\n  $ {dl_cmd}\n"
            f"Step 2: Execute task with local 125B-150B LLM:\n  Prompt: {review_prompt}\n"
        )
