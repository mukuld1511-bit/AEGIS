"""AEGIS Distributed Storage & Drive Sync Engine.
Coordinates file transfer across the 8 isolated DGX nodes via dictated Google Drive CLI commands.
Maintains zero peer-to-peer DGX networking; all file handoffs are orchestrated through the Raspberry Pi.
"""
import os
import uuid
from typing import Dict, Any, Optional

class AEGISStorageSystem:
    def __init__(self, remote_name: str = "gdrive", base_folder: str = "AEGIS_Cluster_Artifacts"):
        self.remote_name = remote_name
        self.base_folder = base_folder

    def create_task_storage_manifest(self, task_id: Optional[str] = None) -> Dict[str, Any]:
        """Creates an isolated Google Drive workspace path for a specific task."""
        tid = task_id or f"tsk_{uuid.uuid4().hex[:8]}"
        base_remote = f"{self.remote_name}:{self.base_folder}/{tid}"
        return {
            "task_id": tid,
            "base_remote": base_remote,
            "input_dir": f"{base_remote}/inputs",
            "output_dir": f"{base_remote}/outputs",
            "review_dir": f"{base_remote}/reviews"
        }

    def generate_worker_upload_command(self, manifest: Dict[str, Any], local_filepath: str, stage: str = "outputs") -> str:
        """Generates the exact CLI command dictated to DGX Node 1 to upload output to Google Drive."""
        fname = os.path.basename(local_filepath)
        target_remote = f"{manifest['base_remote']}/{stage}/{fname}"
        # rclone copyto with fast streaming and progress stats
        return f"rclone copyto '{local_filepath}' '{target_remote}' --fast-list --transfers 4"

    def generate_handoff_download_command(self, manifest: Dict[str, Any], filename: str, stage: str = "outputs", local_dest: str = "./workspace") -> str:
        """Generates the exact CLI command dictated to DGX Node 2 to download files from Google Drive."""
        source_remote = f"{manifest['base_remote']}/{stage}/{filename}"
        return f"mkdir -p '{local_dest}' && rclone copyto '{source_remote}' '{local_dest}/{filename}' --fast-list"

    def format_dgx_task_instructions(self, prompt: str, manifest: Dict[str, Any], expected_output_file: str) -> Dict[str, Any]:
        """Packages instructions for DGX node: local LLM prompt + dictated storage commands."""
        upload_cmd = self.generate_worker_upload_command(manifest, f"./{expected_output_file}")
        return {
            "task_id": manifest["task_id"],
            "prompt": prompt,
            "expected_file": expected_output_file,
            "storage_protocol": "google_drive",
            "dictated_upload_command": upload_cmd,
            "post_execution_action": f"Execute `{upload_cmd}` and return output json to Raspberry Pi hub."
        }
