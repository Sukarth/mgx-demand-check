import os
import tempfile

# The app creates its store at import time; point it at a throwaway database first.
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ["DASHBOARD_PASSWORD"] = "test-password"
