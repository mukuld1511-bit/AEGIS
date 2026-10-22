"""AEGIS Persistent Terminal Session Manager.
Runs asynchronous sub-processes, captures live streaming stdout/stderr, and ensures resilient execution on DGX nodes.
"""
import asyncio
import os
import sys
import subprocess
from typing import AsyncGenerator, Optional, Tuple

class TerminalSession:
    def __init__(self, session_id: str, working_dir: Optional[str] = None):
        self.session_id = session_id
        self.working_dir = working_dir or os.getcwd()
        self.process: Optional[asyncio.subprocess.Process] = None
        self.is_running = False
        self.exit_code: Optional[int] = None
        self.full_log: str = ""

    async def execute_command_stream(self, command: str) -> AsyncGenerator[Tuple[str, str], None]:
        """Executes a shell command and yields ('stdout'|'stderr', chunk) as it arrives."""
        self.is_running = True
        self.full_log = ""

        # Shell execution syntax
        if os.name == "nt":
            shell_cmd = ["powershell", "-NoProfile", "-Command", command]
        else:
            shell_cmd = ["/bin/bash", "-c", command]

        try:
            self.process = await asyncio.create_subprocess_exec(
                *shell_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.working_dir
            )

            async def read_stream(stream, stream_name: str, queue: asyncio.Queue):
                while True:
                    line = await stream.readline()
                    if not line:
                        break
                    decoded = line.decode("utf-8", errors="replace")
                    await queue.put((stream_name, decoded))
                await queue.put((stream_name, None))

            queue = asyncio.Queue()
            t_stdout = asyncio.create_task(read_stream(self.process.stdout, "stdout", queue))
            t_stderr = asyncio.create_task(read_stream(self.process.stderr, "stderr", queue))

            active_streams = 2
            while active_streams > 0:
                stream_name, chunk = await queue.get()
                if chunk is None:
                    active_streams -= 1
                else:
                    self.full_log += chunk
                    yield (stream_name, chunk)

            await self.process.wait()
            self.exit_code = self.process.returncode
        except Exception as e:
            err_msg = f"\n[Execution Error]: {str(e)}\n"
            self.full_log += err_msg
            yield ("stderr", err_msg)
            self.exit_code = -1
        finally:
            self.is_running = False

    def terminate(self):
        """Safely terminates the running process."""
        if self.process and self.is_running:
            try:
                self.process.terminate()
            except Exception:
                pass
            self.is_running = False
