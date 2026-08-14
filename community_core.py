import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import app_v2 as site

BRAND_NAME = "小飞侠设计100%"
ROLE_XIAOFEIXIA = "xiaofeixia"
ROLE_XIAOYOUXIA = "xiaoyouxia"
USER_COOKIE = "design100_user"
SESSION_SECRET = os.getenv("TOOLBOARD_SESSION_SECRET", "") or site.SESSION_SECRET
CAD_LICENSE_DB = Path(os.getenv("CAD100_LICENSE_DB", "/opt