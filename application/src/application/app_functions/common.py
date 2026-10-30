from datetime import datetime
import json
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel
from slugify import slugify

PARIS_TZ = ZoneInfo("Europe/Paris")


def to_naive(dt: datetime | None) -> datetime | None:
    """Convert a datetime (aware or naive) to a naive datetime in the Europe/Paris timezone."""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(PARIS_TZ).replace(tzinfo=None)
    return dt


def normalize_date_str(date_val: datetime | str | None) -> str | None:
    """Normalize a datetime or ISO date string into YYYY_MM_DD format."""
    if date_val is None or date_val == "":
        return None
    if isinstance(date_val, str):
        try:
            date_val = datetime.fromisoformat(date_val)
        except ValueError:
            return slugify(date_val, separator="_") or None
    if isinstance(date_val, datetime):
        return date_val.strftime("%Y_%m_%d")
    return None


def json_safe_dict(model: BaseModel) -> dict[str, Any]:
    """Convert a Pydantic BaseModel instance into a JSON-compatible dictionary."""
    return json.loads(model.model_dump_json())


def serialize_ai_value(val: Any) -> Any:
    """Recursively convert Pydantic models and AI extraction dictionaries into JSON-serializable structures."""
    if isinstance(val, BaseModel):
        data = json_safe_dict(val)
        data.pop("reasoning_thinking", None)
        return data
    if isinstance(val, dict):
        return {
            k: serialize_ai_value(v)
            for k, v in val.items()
            if k not in ("_id", "id", "execution_times", "reasoning_thinking")
        }
    if isinstance(val, list):
        return [serialize_ai_value(item) for item in val]
    return val
