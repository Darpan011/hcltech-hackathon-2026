"""Application settings, read once from environment variables (never hard-code secrets)."""
import os


def _bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    database_url: str = os.getenv(
        "DATABASE_URL", "postgresql+psycopg://onboard:onboard@localhost:5432/onboardiq"
    )
    jwt_secret: str = os.getenv("JWT_SECRET", "")
    jwt_expire_minutes: int = int(os.getenv("JWT_EXPIRE_MINUTES", "480"))
    extraction_provider: str = os.getenv("EXTRACTION_PROVIDER", "mock")
    core_banking_key: str = os.getenv("CORE_BANKING_KEY", "")
    data_dir: str = os.getenv("DATA_DIR", "/data/pack")
    upload_dir: str = os.getenv("UPLOAD_DIR", "/data/uploads")
    upload_demo_dir: str = os.getenv("UPLOAD_DEMO_DIR", "/data/upload_demo")
    output_dir: str = os.getenv("OUTPUT_DIR", "/output")
    cors_origins: list[str] = [
        o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()
    ]
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    # Business date used as application_date for new applications. The data pack is dated
    # 2026-03-04, so demos use that date; leave empty to use today's date (IST).
    business_date: str = os.getenv("BUSINESS_DATE", "")
    seed_password: str = os.getenv("SEED_PASSWORD", "Demo@123")
    # false (default) = branch onboarding: customers visit the branch, a KYC Officer enters their data
    # and creates their login. true = customers self-register and apply online.
    self_service_onboarding: bool = _bool("SELF_SERVICE_ONBOARDING", "false")

    kafka_enabled: bool = _bool("KAFKA_ENABLED", "true")
    kafka_bootstrap_servers: str = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:29092")
    kafka_topic_notifications: str = os.getenv("KAFKA_TOPIC_NOTIFICATIONS", "kyc.notifications")


settings = Settings()
