import subprocess
import sys
import os

app_dir = os.path.dirname(os.path.abspath(__file__))
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200

p = subprocess.Popen(
    [sys.executable, "app.py"],
    cwd=app_dir,
    creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
    close_fds=True
)

print(f"Flask server launched with PID: {p.pid}")
