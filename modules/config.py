import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

APP_PASSWORD = os.getenv("APP_PASSWORD", "123456")

ZHIPUAI_API_KEY = os.getenv("ZHIPUAI_API_KEY", "")
KNOWLEDGE_BASE_ID = os.getenv("KNOWLEDGE_BASE_ID", "")
ZHIPUAI_BASE_URL = os.getenv("ZHIPUAI_BASE_URL", "https://open.bigmodel.cn/api/llm")
ZHIPUAI_KB_BASE_URL = os.getenv("ZHIPUAI_KB_BASE_URL", "https://open.bigmodel.cn/api/llm-application")

ZHIHU_ACCESS_SECRET = os.getenv("ZHIHU_ACCESS_SECRET", "")

EXTRACT_MODEL = os.getenv("EXTRACT_MODEL", "deepseek-v4-flash")
EXTRACT_API_KEY = os.getenv("EXTRACT_API_KEY", "")
EXTRACT_BASE_URL = os.getenv("EXTRACT_BASE_URL", "https://api.deepseek.com")

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
EXPORT_DIR = DATA_DIR / "exports"
DB_PATH = DATA_DIR / "projects.db"

UPLOAD_MAX_SIZE = 10 * 1024 * 1024

UPLOAD_CATEGORIES = {
    "上期报告": "previous_report",
    "本期模板": "current_template",
    "本期资料": "current_materials",
    "参考报告": "reference_reports",
}
