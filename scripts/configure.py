"""Create a local deployment key once. Never overwrite existing credentials."""
import json
import os
import secrets
from pathlib import Path

path = Path('.env')
try:
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
except FileExistsError:
    print('.env already exists; preserving configuration')
else:
    with os.fdopen(fd, 'w') as file:
        file.write("SPEECH_API_KEYS='" + json.dumps({'owner': secrets.token_urlsafe(32)}) + "'\n")
    print('Created .env. Read SPEECH_API_KEYS there for your client; keep this file private.')
