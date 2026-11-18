from pathlib import Path
import os

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "aam.db"
PORT = 8710
DEFAULT_GATEWAY_KEY = "aam-local-key"
VERSION = "1.1.39(10101039)"
# Loomy 登录签名凭据：优先读环境变量（可在 systemd unit 注入轮换），缺省保持现值
LOOMY_AK_ID = os.environ.get("LOOMY_AK_ID", "")
LOOMY_AK_SECRET = os.environ.get("LOOMY_AK_SECRET", "")
LOOMY_APPID = os.environ.get("LOOMY_APPID", "GM3LOOMY")
