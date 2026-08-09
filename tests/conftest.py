from __future__ import annotations

import os
from pathlib import Path


os.environ.setdefault("JOB_SEARCH_LOCATION_PREFERENCES", str(Path(__file__).with_name("empty_location_preferences.json")))
