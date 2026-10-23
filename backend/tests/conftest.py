import os
import tempfile
from pathlib import Path

# Force an isolated test environment BEFORE the app is imported (settings are read at import).
# Never reuse the dev DATABASE_URL: the API tests drop and recreate every table.
_ROOT = Path(__file__).resolve().parents[2]
_TMP = Path(tempfile.mkdtemp(prefix="onboardiq-test-"))

os.environ["DATABASE_URL"] = os.getenv("TEST_DATABASE_URL", f"sqlite:///{_TMP / 'test.db'}")
os.environ["KAFKA_ENABLED"] = "false"
os.environ["JWT_SECRET"] = "test-secret-not-for-production"
os.environ["CORE_BANKING_KEY"] = "test-core-banking-key"
os.environ["UPLOAD_DIR"] = str(_TMP / "uploads")
os.environ["BUSINESS_DATE"] = "2026-03-04"
os.environ["SELF_SERVICE_ONBOARDING"] = "true"   # existing tests cover online self-service; branch tests switch it off
if not Path(os.getenv("DATA_DIR", "/nonexistent")).exists():
    os.environ["DATA_DIR"] = str(_ROOT / "data" / "pack")
