import os
import tempfile

# The app creates its store at import time; point it at a throwaway SQLite file first.
# An empty DATABASE_URL keeps a production value in the environment from being used.
os.environ["DATABASE_URL"] = ""
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ["DASHBOARD_PASSWORD"] = "test-password"
