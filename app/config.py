import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env file from root
env_path = BASE_DIR / ".env"
load_dotenv(dotenv_path=env_path)


class Settings:
    APP_ENV: str = os.getenv("APP_ENV", "development")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./data/database/filingguard.db")
    SEC_USER_AGENT: str = os.getenv("SEC_USER_AGENT", "FilingGuardAI/1.0 (auditor-team@filingguard.org; Financial Statement Audit Platform)")
    SEC_REQUEST_TIMEOUT: int = int(os.getenv("SEC_REQUEST_TIMEOUT", "30"))
    SEC_CACHE_ENABLED: bool = os.getenv("SEC_CACHE_ENABLED", "true").lower() in ("true", "1", "yes")
    SEC_CACHE_TTL_HOURS: int = int(os.getenv("SEC_CACHE_TTL_HOURS", "24"))
    REVIEWER_ID: str = os.getenv("REVIEWER_ID", "demo_reviewer")
    LLM_ENABLED: bool = os.getenv("LLM_ENABLED", "false").lower() in ("true", "1", "yes")
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
    AUDIT_SIGNING_SECRET: str = os.getenv("AUDIT_SIGNING_SECRET", "fg_audit_secure_hmac_secret_2026_vault_key")

    # Workspace Paths
    BASE_DIR: Path = BASE_DIR
    DATA_DIR: Path = BASE_DIR / "data"
    CONFIG_DIR: Path = BASE_DIR / "config"
    DATABASE_DIR: Path = BASE_DIR / "data" / "database"

    @property
    def sqlite_db_path(self) -> Path:
        """Extract Path for SQLite database from DATABASE_URL."""
        if self.DATABASE_URL.startswith("sqlite:///"):
            relative_or_absolute = self.DATABASE_URL.replace("sqlite:///", "")
            if relative_or_absolute.startswith("./"):
                return self.BASE_DIR / relative_or_absolute[2:]
            return Path(relative_or_absolute)
        return self.DATABASE_DIR / "filingguard.db"


settings = Settings()
