"""Data models representing Discogs entities extracted from HTML."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, List, Optional


@dataclass(slots=True)
class LabelCredit:
    label_id: Optional[int]
    name: str
    catalog_number: Optional[str] = None


@dataclass(slots=True)
class FormatInfo:
    name: str
    quantity: Optional[int] = None
    descriptions: List[str] = field(default_factory=list)
    notes: Optional[str] = None


@dataclass(slots=True)
class ReleaseSummary:
    release_id: int
    title: str
    artists: str
    year: Optional[int]
    url: str
    have_count: Optional[int] = None
    want_count: Optional[int] = None
    average_rating: Optional[float] = None
    ratings_count: Optional[int] = None


@dataclass(slots=True)
class Review:
    username: str
    rating: Optional[float]
    review_text: str
    date: Optional[datetime] = None


@dataclass(slots=True)
class ReleaseDetail:
    release_id: int
    title: str
    artists: str
    year: Optional[int]
    master_id: Optional[int] = None
    country: Optional[str] = None
    released: Optional[str] = None
    genres: List[str] = field(default_factory=list)
    styles: List[str] = field(default_factory=list)
    labels: List[LabelCredit] = field(default_factory=list)
    label_summary: Optional[str] = None
    formats: List[FormatInfo] = field(default_factory=list)
    format_summary: Optional[str] = None
    image_url: Optional[str] = None
    reviews: List[Review] = field(default_factory=list)
    have_users: List[str] = field(default_factory=list)
    want_users: List[str] = field(default_factory=list)


@dataclass(slots=True)
class UserProfile:
    username: str
    user_id: str
    location: Optional[str]
    join_date: Optional[datetime]
    collection_size: Optional[int]
    wantlist_size: Optional[int]


def coerce_int(value: str | None) -> Optional[int]:
    if value is None:
        return None
    cleaned = "".join(ch for ch in value if ch.isdigit())
    if not cleaned:
        return None
    try:
        return int(cleaned)
    except ValueError:
        return None


def coerce_float(value: str | None) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value.replace(",", "."))
    except (ValueError, AttributeError):
        return None


def coerce_date(value: str | None) -> Optional[datetime]:
    if not value:
        return None
    for fmt in ("%d %B %Y", "%B %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value.strip(), fmt)
        except ValueError:
            continue
    return None


def unique(items: Iterable[str]) -> List[str]:
    seen: set[str] = set()
    ordered: List[str] = []
    for item in items:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(item)
    return ordered


_YEAR_PATTERN = re.compile(r"(\d{4})")


def coerce_year(
    value: str | None, *, earliest: int = 1800, latest: int = 2100
) -> Optional[int]:
    if not value:
        return None
    match = _YEAR_PATTERN.search(value)
    if not match:
        return None
    try:
        year = int(match.group(1))
    except ValueError:
        return None
    if earliest <= year <= latest:
        return year
    return None
