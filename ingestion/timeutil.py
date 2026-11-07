"""timeutil.py – Single source of truth for 'now' in the project timezone."""
from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytz

from config import settings


def now_local() -> pd.Timestamp:
    """Current time in settings.timezone (IST), as a tz-naive Timestamp."""
    return pd.Timestamp(datetime.now(pytz.timezone(settings.timezone)).replace(tzinfo=None))
