import os
from pathlib import Path
import secrets

PROJECT_ROOT = Path(__file__).resolve().parent
ENV_FILE = PROJECT_ROOT / ".env"

try:
    from dotenv import load_dotenv
    load_dotenv(ENV_FILE)
except ImportError:
    pass

SECRET_KEY         = os.environ.get("SECRET_KEY") or secrets.token_urlsafe(32)
JWT_SECRET         = os.environ.get("JWT_SECRET") or secrets.token_urlsafe(32)
JWT_EXPIRY_SECONDS = 3600

DATABASE      = os.environ.get("DATABASE_PATH", str(PROJECT_ROOT / "tickets.db"))
KB_PATH       = str(PROJECT_ROOT / "knowledge_base" / "banking_support_fraud.json")
MODEL_PATH    = str(PROJECT_ROOT / "milestones" / "m1_ticket_classification" / "models" / "banking77_classifier.pkl")
TRAIN_DATA_PATH = str(PROJECT_ROOT / "milestones" / "m1_ticket_classification" / "dataset" / "banking77" / "train.csv")
TEST_DATA_PATH = str(PROJECT_ROOT / "milestones" / "m1_ticket_classification" / "dataset" / "banking77" / "test.csv")
TOP_K         = 3
MIN_RELEVANCE = 0.05

# ──────────────────────────────────────────────
# Groq LLM Configuration (Sole LLM Provider)
# ──────────────────────────────────────────────
GROQ_API_KEY  = os.environ.get("GROQ_API_KEY", "")
GROQ_BASE_URL = os.environ.get("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
GROQ_MODEL    = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
GROQ_TIMEOUT  = 45

# ──────────────────────────────────────────────
# System Settings Defaults
# ──────────────────────────────────────────────
DEFAULT_AUTO_RESOLVE_THRESHOLD = 70.0
DEFAULT_WORKFLOW_STRATEGY      = "Standard"
DEFAULT_LLM_PROVIDER           = "Groq"
DEFAULT_LLM_MODEL              = "openai/gpt-oss-120b"
DEFAULT_TOP_K                  = 3
DEFAULT_MIN_SIMILARITY         = 0.05
DEFAULT_HIGH_RISK_AMOUNT       = 10000.0
DEFAULT_P1_SLA_HOURS           = 4
DEFAULT_P2_SLA_HOURS           = 24
DEFAULT_P3_SLA_HOURS           = 48

SMTP_SERVER   = os.environ.get("SMTP_SERVER",   "smtp.gmail.com")
SMTP_PORT     = int(os.environ.get("SMTP_PORT", "587"))
SMTP_EMAIL    = os.environ.get("SMTP_EMAIL",    "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")

JIRA_URL             = os.environ.get("JIRA_URL",             "").rstrip("/")
JIRA_EMAIL           = os.environ.get("JIRA_EMAIL",           "")
JIRA_API_TOKEN       = os.environ.get("JIRA_API_TOKEN",       "")
JIRA_PROJECT_KEY     = os.environ.get("JIRA_PROJECT_KEY",     "BANK")
JIRA_SIMULATION_MODE = os.environ.get("JIRA_SIMULATION_MODE", "true").lower() in ("true", "1", "yes")

AUTO_RESOLVE_THRESHOLD = float(os.environ.get("AUTO_RESOLVE_THRESHOLD", "70.0"))

SEED_RETRIEVAL_ACCURACY = 0.92
SEED_RESOLUTION_RATE    = 0.78
SEED_AVG_RESPONSE_TIME  = 2.4
