"""Deterministic Chinese/English date-time extraction.

Exists so the common cases ("明天下午三点开会") resolve **without** a model
call: cheaper, faster, and it keeps the message text on-device. The model
confirmer is the fallback for what this cannot parse, not the default path.

Returns the date and clock separately: only the caller knows what a missing
clock should mean (a deadline defaults to end-of-day, a meeting to morning).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Optional

_CN_DIGITS = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}

_WEEKDAY_CHARS = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}

_RELATIVE_DAYS = {
    "今天": 0, "今晚": 0, "今早": 0, "今日": 0,
    "明天": 1, "明早": 1, "明晚": 1, "明日": 1,
    "后天": 2, "後天": 2,
    "大后天": 3, "大後天": 3,
}

_MERIDIEM_SHIFT = ("下午", "晚上", "傍晚")
_MERIDIEM_MORNING = ("上午", "早上", "凌晨", "早晨")

_ISO_DATE = re.compile(r"(20\d{2})-(\d{1,2})-(\d{1,2})")
_CN_DATE = re.compile(r"(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]")
_WEEKDAY = re.compile(r"(?:周|星期|礼拜)([一二三四五六日天])")
_CLOCK = re.compile(r"(\d{1,2})\s*[:：]\s*(\d{2})")
_CN_HOUR = re.compile(r"([0-9]{1,2}|[零一二两三四五六七八九十]{1,3})\s*点\s*(半|[0-9]{1,2}\s*分|[零一二两三四五六七八九十]{1,3}\s*分)?")


@dataclass(frozen=True)
class ParsedWhen:
    day: Optional[date] = None
    clock: Optional[time] = None

    @property
    def has_any(self) -> bool:
        return self.day is not None or self.clock is not None

    def to_datetime(self, *, base: date, default_clock: time) -> datetime:
        return datetime.combine(self.day or base, self.clock or default_clock)


def _cn_number(text: str) -> Optional[int]:
    text = text.strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)

    # Handles 十, 十一, 二十, 二十三 — enough for clock hours.
    if "十" in text:
        left, _, right = text.partition("十")
        tens = _CN_DIGITS.get(left, 1) if left else 1
        ones = _CN_DIGITS.get(right, 0) if right else 0
        return tens * 10 + ones

    total = 0
    for char in text:
        if char not in _CN_DIGITS:
            return None
        total = total * 10 + _CN_DIGITS[char]
    return total or None


def _parse_day(text: str, today: date) -> Optional[date]:
    iso = _ISO_DATE.search(text)
    if iso:
        try:
            return date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
        except ValueError:
            return None

    cn = _CN_DATE.search(text)
    if cn:
        try:
            candidate = date(today.year, int(cn.group(1)), int(cn.group(2)))
        except ValueError:
            return None
        # A date more than a month behind us almost certainly means next year.
        if (today - candidate).days > 31:
            try:
                candidate = candidate.replace(year=today.year + 1)
            except ValueError:
                return candidate
        return candidate

    for word, offset in _RELATIVE_DAYS.items():
        if word in text:
            return today + timedelta(days=offset)

    weekday = _WEEKDAY.search(text)
    if weekday:
        target = _WEEKDAY_CHARS.get(weekday.group(1))
        if target is None:
            return None
        delta = (target - today.weekday()) % 7
        # "周三" spoken on a Wednesday means today; "下周三" is out of scope here.
        return today + timedelta(days=delta)

    return None


def _parse_clock(text: str) -> Optional[time]:
    hour: Optional[int] = None
    minute = 0

    clock = _CLOCK.search(text)
    if clock:
        hour = int(clock.group(1))
        minute = int(clock.group(2))
    else:
        cn = _CN_HOUR.search(text)
        if cn:
            hour = _cn_number(cn.group(1))
            suffix = (cn.group(2) or "").strip()
            if suffix == "半":
                minute = 30
            elif suffix:
                parsed = _cn_number(suffix.replace("分", "").strip())
                minute = parsed if parsed is not None else 0

    if hour is None:
        if "中午" in text:
            return time(12, 0)
        return None

    if any(word in text for word in _MERIDIEM_SHIFT) and hour < 12:
        hour += 12
    elif "中午" in text and hour < 12:
        hour = 12
    elif any(word in text for word in _MERIDIEM_MORNING) and hour == 12:
        hour = 0

    if not (0 <= hour <= 23) or not (0 <= minute <= 59):
        return None

    return time(hour, minute)


def parse_when(text: str, *, now: Optional[datetime] = None) -> ParsedWhen:
    """Extract whatever date/clock the text states. Never guesses both."""
    reference = now or datetime.now()
    source = text or ""

    return ParsedWhen(day=_parse_day(source, reference.date()), clock=_parse_clock(source))
