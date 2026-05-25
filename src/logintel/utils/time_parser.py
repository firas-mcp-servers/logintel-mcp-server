"""Time parsing utilities for relative and absolute timestamps."""

from datetime import UTC, datetime, timedelta


class TimeRange:
    """Internal time range representation."""

    def __init__(self, from_time: datetime, to_time: datetime | None = None) -> None:
        self.from_time = from_time
        self.to_time = to_time or datetime.now(UTC)

    def contains(self, ts: datetime) -> bool:
        """Check if a timestamp falls within this range."""
        return self.from_time <= ts <= self.to_time


def parse_relative_time(value: str, reference: datetime | None = None) -> datetime:
    """Parse a relative time string like 'now', 'now-1h', 'now-30m'."""
    reference = reference or datetime.now(UTC)
    value = value.strip()

    # Try ISO 8601 first (before lowercasing, normalize T and Z)
    iso_value = value.upper().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(iso_value)
    except ValueError:
        pass

    value_lower = value.lower()

    if value_lower == "now":
        return reference

    if value_lower.startswith("now-"):
        delta_str = value_lower[4:]
        return reference - _parse_delta(delta_str)

    if value_lower.startswith("now+"):
        delta_str = value_lower[4:]
        return reference + _parse_delta(delta_str)

    raise ValueError(f"Unable to parse time: {value}")


def _parse_delta(delta_str: str) -> timedelta:
    """Parse a delta string like '1h', '30m', '1d', '1s'."""
    delta_str = delta_str.strip()
    if not delta_str:
        return timedelta()

    total_seconds = 0.0
    current_number = ""
    i = 0

    while i < len(delta_str):
        char = delta_str[i]
        if char.isdigit() or char == ".":
            current_number += char
            i += 1
        elif char in "dhms":
            if not current_number:
                raise ValueError(f"Invalid delta format: {delta_str}")
            num = float(current_number)
            if char == "d":
                total_seconds += num * 86400
            elif char == "h":
                total_seconds += num * 3600
            elif char == "m":
                total_seconds += num * 60
            elif char == "s":
                total_seconds += num
            current_number = ""
            i += 1
        else:
            raise ValueError(f"Invalid delta format: {delta_str}")

    if current_number:
        raise ValueError(f"Invalid delta format: {delta_str}")

    return timedelta(seconds=total_seconds)
