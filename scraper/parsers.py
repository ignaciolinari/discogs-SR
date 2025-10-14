"""HTML parsers for Discogs search, release, and user pages."""

from __future__ import annotations

import logging
import re
from typing import Iterable, List, Optional, Tuple

from bs4 import BeautifulSoup
from bs4.element import NavigableString

from .models import (
    FormatInfo,
    LabelCredit,
    ReleaseDetail,
    ReleaseSummary,
    Review,
    UserProfile,
    coerce_date,
    coerce_float,
    coerce_int,
    coerce_year,
    unique,
)


logger = logging.getLogger(__name__)


_RE_RELEASE_ID = re.compile(r"/release/(\d+)")
_RE_MASTER_ID = re.compile(r"/master/(\d+)")
_RE_USER_FROM_HREF = re.compile(r"/(user|seller)/([^/?#]+)")
_RE_LABEL_ID = re.compile(r"/label/(\d+)")


def parse_search_results(html: str) -> List[ReleaseSummary]:
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select(".card, .card_large, .search_result")

    releases: List[ReleaseSummary] = []
    for card in cards:
        link = card.select_one("a[href*='/release/']")
        if not link or not link.get("href"):
            continue

        release_id = _extract_release_id(link.get("href", ""))
        if release_id is None:
            continue

        title = link.get_text(strip=True)
        artist_el = card.select_one(
            ".card-artist, .card_body .artist, .search_result_artist"
        )
        artists = artist_el.get_text(strip=True) if artist_el else ""

        year_el = card.find(class_=re.compile("year", re.I))
        year = coerce_year(year_el.get_text(strip=True)) if year_el else None

        stats = _parse_stats_list(card)
        have = stats.get("have")
        want = stats.get("want")
        ratings_total = stats.get("ratings")
        avg = stats.get("avg_rating")

        releases.append(
            ReleaseSummary(
                release_id=release_id,
                title=title,
                artists=artists,
                year=year,
                url=link.get("href", ""),
                have_count=have if isinstance(have, int) else None,
                want_count=want if isinstance(want, int) else None,
                average_rating=float(avg) if isinstance(avg, (int, float)) else None,
                ratings_count=ratings_total if isinstance(ratings_total, int) else None,
            )
        )

    return releases


def parse_release_detail(html: str) -> ReleaseDetail:
    soup = BeautifulSoup(html, "html.parser")

    title_el = soup.select_one("#profile_title, h1[itemprop='name'], h1.title")
    title = title_el.get_text(strip=True) if title_el else ""

    release_id = None
    canonical = soup.find("link", rel="canonical")
    if canonical and canonical.get("href"):
        release_id = _extract_release_id(canonical["href"])
    if release_id is None:
        first_link = soup.select_one("a[href*='/release/']")
        fallback_href = first_link.get("href") if first_link else None
        release_id = _extract_release_id(str(fallback_href)) if fallback_href else 0

    artist_el = soup.select_one(
        "#profile_title span[itemprop='byArtist'], h1 span.artist, h1 .profile"
    )
    artists = artist_el.get_text(" ", strip=True) if artist_el else ""

    year = None
    year_el = soup.find(string=re.compile("Released", re.I))
    if year_el and year_el.parent:
        year = coerce_year(year_el.parent.get_text(" ", strip=True))

    master_id = None
    master_link = soup.select_one("a[href*='/master/']")
    if master_link:
        href = master_link.get("href")
        if href:
            master_id = _extract_master_id(href)

    profile_entries = _extract_profile_entries(soup)

    country = _extract_value_text(profile_entries.get("country"))
    released = _extract_value_text(profile_entries.get("released"))

    label_node = profile_entries.get("label")
    label_summary = _extract_value_text(label_node)
    labels = _parse_label_entries(label_node)

    format_node = profile_entries.get("format")
    formats, format_summary = _parse_formats(format_node)

    genres = (
        _split_profile_list(profile_entries.get("genre"))
        or _extract_profile_tags(soup, "Genre")
        or [tag.get_text(strip=True) for tag in soup.select("a[href*='/genre/']")]
    )

    styles = (
        _split_profile_list(profile_entries.get("style"))
        or _extract_profile_tags(soup, "Style")
        or [tag.get_text(strip=True) for tag in soup.select("a[href*='/style/']")]
    )

    image_el = soup.select_one("meta[property='og:image']")
    image_url = image_el.get("content") if image_el else None

    have_users, want_users = _parse_statistics_users(soup)
    reviews = _parse_reviews(soup)

    return ReleaseDetail(
        release_id=release_id or 0,
        title=title,
        artists=artists,
        year=year,
        master_id=master_id,
        country=country,
        released=released,
        genres=genres,
        styles=styles,
        labels=labels,
        label_summary=label_summary,
        formats=formats,
        format_summary=format_summary,
        image_url=image_url,
        reviews=reviews,
        have_users=have_users,
        want_users=want_users,
    )


def parse_release_user_list(html: str) -> List[str]:
    """Parse usernames from the release community modal/listing pages."""

    soup = BeautifulSoup(html, "html.parser")
    usernames: List[str] = []

    def _append_from_elements(elements: Iterable) -> None:
        for link in elements:
            href = link.get("href", "")
            username = _username_from_href(href)
            if not username:
                username = (link.get("data-username") or "").strip()
            display = link.get_text(strip=True)
            if display:
                if username and display.lower() == username.lower():
                    username = display
                elif not username:
                    username = display
            if not username:
                continue
            usernames.append(username)

    _append_from_elements(soup.select("a[href*='/user/'], a[href*='/seller/']"))
    if not usernames:
        _append_from_elements(soup.select("[data-username]"))

    return unique(usernames)


def _parse_statistics_users(soup: BeautifulSoup) -> Tuple[List[str], List[str]]:
    have_users: List[str] = []
    want_users: List[str] = []

    stats_section = soup.find("div", id=re.compile("community")) or soup.find(
        "section", id=re.compile("statistics", re.I)
    )
    if not stats_section:
        return have_users, want_users

    for link in stats_section.select("a[href*='/user/'], a[href*='/seller/']"):
        href = link.get("href", "")
        username = _username_from_href(href)
        if not username:
            continue

        text = link.get_text(strip=True).lower()
        if "want" in text:
            want_users.append(username)
        elif "have" in text:
            have_users.append(username)
        else:
            data_label = (link.get("data-label") or "").lower()
            if "want" in data_label:
                want_users.append(username)
            elif "have" in data_label:
                have_users.append(username)

    return unique(have_users), unique(want_users)


def _username_from_href(href: str) -> Optional[str]:
    match = _RE_USER_FROM_HREF.search(href)
    if not match:
        return None
    username = match.group(2)
    return username.strip()


def _parse_reviews(soup: BeautifulSoup) -> List[Review]:
    reviews: List[Review] = []
    review_nodes = soup.select(".review, li.review, .community_reviews .card")

    for node in review_nodes:
        user_link = node.select_one("a[href*='/user/']")
        if not user_link:
            continue

        username = _username_from_href(user_link.get("href", ""))
        if not username:
            continue

        rating = _extract_rating(node)
        body_el = node.select_one(
            ".review_body, .content, .body, [class^='markup_'], [class*=' markup_'], p"
        )
        review_text = body_el.get_text(" ", strip=True) if body_el else ""

        date_el = node.select_one("time")
        review_date = None
        if date_el:
            review_date = coerce_date(date_el.get("datetime")) or coerce_date(
                date_el.get_text(strip=True)
            )

        reviews.append(
            Review(
                username=username,
                rating=rating,
                review_text=review_text,
                date=review_date,
            )
        )

    return reviews


def _extract_rating(node) -> Optional[float]:
    rating_el = node.select_one(
        "[data-rating], [data-value], [aria-label*='rated'], [class*='rating']"
    )
    if rating_el:
        data_rating = rating_el.get("data-rating")
        if data_rating:
            rating = coerce_float(data_rating)
            if rating is not None and rating > 5:
                rating = rating / 100
            return rating
        data_value = rating_el.get("data-value")
        if data_value:
            rating = coerce_float(data_value)
            if rating is not None and rating > 5:
                rating = rating / 100
            return rating
        aria_label = rating_el.get("aria-label")
        if aria_label:
            return coerce_float(_extract_number(aria_label))
        aria_descendant = rating_el.select_one("[aria-label]")
        if aria_descendant and aria_descendant.get("aria-label"):
            return coerce_float(_extract_number(aria_descendant["aria-label"]))
        text_rating = rating_el.get_text(" ", strip=True)
        if text_rating:
            return coerce_float(_extract_number(text_rating))
    return None


def parse_user_profile(html: str, username: str) -> UserProfile:
    soup = BeautifulSoup(html, "html.parser")

    user_id = _extract_user_id(soup) or username
    location = _extract_profile_field(soup, "Location")
    joined_text = _extract_profile_field(soup, "Joined")
    join_date = coerce_date(joined_text)

    collection_size = coerce_int(_extract_profile_stat(soup, "collection"))
    wantlist_size = coerce_int(_extract_profile_stat(soup, "wantlist"))

    return UserProfile(
        username=username,
        user_id=user_id,
        location=location,
        join_date=join_date,
        collection_size=collection_size,
        wantlist_size=wantlist_size,
    )


def _extract_profile_field(soup: BeautifulSoup, label: str) -> Optional[str]:
    field = soup.find("span", string=re.compile(label, re.I))
    if not field:
        return None
    value = field.find_next("span")
    return value.get_text(strip=True) if value else None


def _extract_profile_stat(soup: BeautifulSoup, key: str) -> Optional[str]:
    stat = soup.find("a", href=re.compile(key, re.I))
    if not stat:
        return None
    return stat.get_text(strip=True)


def _extract_user_id(soup: BeautifulSoup) -> Optional[str]:
    meta = soup.find("meta", property="profile:username")
    if meta and meta.get("content"):
        return meta["content"]
    return None


def _extract_profile_tags(soup: BeautifulSoup, label: str) -> List[str]:
    heading = soup.find(
        lambda tag: tag.name in {"h3", "dt", "span"}
        and label.lower() in tag.get_text(strip=True).lower()
    )
    if not heading:
        return []

    container = heading.find_next(lambda tag: tag.name in {"div", "dd", "span", "p"})
    if not container:
        return []

    tags = [link.get_text(strip=True) for link in container.find_all("a")]
    return [tag for tag in tags if tag]


def _extract_release_id(href: str) -> Optional[int]:
    """Extrae release_id de una URL de Discogs.

    Args:
        href: URL que puede contener /release/NNNN

    Returns:
        ID del release o None si no se encuentra
    """
    match = _RE_RELEASE_ID.search(href or "")
    if not match:
        logger.debug(
            f"No se encontró release_id en href: {href[:100] if href else 'None'}"
        )
        return None
    try:
        return int(match.group(1))
    except ValueError as e:
        logger.warning(
            f"Error convirtiendo release_id a int desde '{match.group(1)}': {e}"
        )
        return None


def _extract_master_id(href: str) -> Optional[int]:
    """Extrae master_id de una URL de Discogs.

    Args:
        href: URL que puede contener /master/NNNN

    Returns:
        ID del master o None si no se encuentra
    """
    match = _RE_MASTER_ID.search(href or "")
    if not match:
        logger.debug(
            f"No se encontró master_id en href: {href[:100] if href else 'None'}"
        )
        return None
    try:
        return int(match.group(1))
    except ValueError as e:
        logger.warning(
            f"Error convirtiendo master_id a int desde '{match.group(1)}': {e}"
        )
        return None


def _extract_number(text: str) -> str:
    match = re.search(r"([0-9]+(?:[.,][0-9]+)?)", text)
    return match.group(1) if match else ""


def _parse_stats_list(node) -> dict[str, Optional[float | int]]:
    stats: dict[str, Optional[float | int]] = {
        "have": None,
        "want": None,
        "avg_rating": None,
        "ratings": None,
    }

    for li in node.select(
        ".card_stats li, .card-stats li, .stats li, .community_stats li"
    ):
        text = li.get_text(" ", strip=True)
        lower = text.lower()
        if "have" in lower:
            stats["have"] = coerce_int(_extract_number(text))
        elif "want" in lower:
            stats["want"] = coerce_int(_extract_number(text))
        elif "avg" in lower and "rating" in lower:
            stats["avg_rating"] = coerce_float(_extract_number(text))
        elif "rating" in lower:
            stats["ratings"] = coerce_int(_extract_number(text))

    if stats["avg_rating"] is None:
        rating_el = node.select_one("[data-rating], .rating")
        if rating_el:
            stats["avg_rating"] = coerce_float(
                rating_el.get("data-rating")
                or _extract_number(rating_el.get_text(" ", strip=True))
            )

    return stats


def _extract_profile_entries(soup: BeautifulSoup) -> dict[str, BeautifulSoup]:
    entries: dict[str, BeautifulSoup] = {}
    selectors = (
        "#profile ul li",
        ".profile ul li",
        "#release-information ul li",
        "section.profile ul li",
        "div.profile ul.list li",
    )
    for selector in selectors:
        for li in soup.select(selector):
            key = _profile_entry_key(li)
            if not key or key in entries:
                continue
            entries[key] = li
    return entries


def _profile_entry_key(node) -> Optional[str]:
    if node is None:
        return None
    label_candidate = node.find(
        lambda tag: tag.name in {"span", "strong"}
        and tag.get_text(" ", strip=True).endswith(":")
    )
    if not label_candidate:
        text = node.get_text(" ", strip=True)
        if ":" not in text:
            return None
        label_text = text.split(":", 1)[0]
    else:
        label_text = label_candidate.get_text(" ", strip=True)
    label_text = label_text.strip().rstrip(":")
    if not label_text:
        return None
    return label_text.lower()


def _extract_value_text(node) -> Optional[str]:
    if node is None:
        return None
    text = node.get_text(" ", strip=True)
    if ":" in text:
        text = text.split(":", 1)[1]
    text = text.strip()
    return text or None


def _split_profile_list(node) -> List[str]:
    text = _extract_value_text(node)
    if not text:
        return []
    values = [
        part.strip() for part in text.replace(";", ",").split(",") if part.strip()
    ]
    return unique(values)


def _parse_label_entries(node) -> List[LabelCredit]:
    if node is None:
        return []

    credits: List[LabelCredit] = []
    label_links = node.select("a[href*='/label/']")
    if not label_links:
        summary = _extract_value_text(node)
        if summary:
            credits.append(
                LabelCredit(label_id=None, name=summary, catalog_number=None)
            )
        return credits

    for link in label_links:
        href = link.get("href", "")
        label_id = _parse_label_id(href)
        name = link.get_text(" ", strip=True)
        catalog_number = _collect_catalog_text(link)
        credits.append(
            LabelCredit(
                label_id=label_id,
                name=name,
                catalog_number=catalog_number,
            )
        )
    return credits


def _parse_label_id(href: str) -> Optional[int]:
    """Extrae label_id de una URL de Discogs.

    Args:
        href: URL que puede contener /label/NNNN

    Returns:
        ID del label o None si no se encuentra
    """
    match = _RE_LABEL_ID.search(href or "")
    if not match:
        logger.debug(
            f"No se encontró label_id en href: {href[:100] if href else 'None'}"
        )
        return None
    try:
        return int(match.group(1))
    except ValueError as e:
        logger.warning(
            f"Error convirtiendo label_id a int desde '{match.group(1)}': {e}"
        )
        return None


def _collect_catalog_text(link) -> Optional[str]:
    parts: List[str] = []
    for sibling in link.next_siblings:
        if getattr(sibling, "name", None) == "a" and sibling.get("href", "").startswith(
            "/label/"
        ):
            break
        if getattr(sibling, "name", None) == "br":
            break
        if isinstance(sibling, NavigableString):
            text = str(sibling)
        else:
            text = sibling.get_text(" ", strip=True)
        text = (text or "").strip()
        text = text.lstrip("-,–— ").rstrip(",; ")
        if text:
            parts.append(text)
    catalog = " ".join(parts).strip()
    return catalog or None


def _parse_formats(node) -> tuple[List[FormatInfo], Optional[str]]:
    summary = _extract_value_text(node)
    if not summary:
        return [], None

    formats: List[FormatInfo] = []
    segments = re.split(r";|\n", summary)
    for segment in segments:
        segment = segment.strip()
        if not segment:
            continue
        fmt = _format_from_segment(segment)
        if fmt is not None:
            formats.append(fmt)
    return formats, summary


def _format_from_segment(segment: str) -> Optional[FormatInfo]:
    tokens = [token.strip() for token in segment.split(",") if token.strip()]
    if not tokens:
        return None

    first = tokens[0]
    quantity = None
    match = re.match(r"^(\d+)\s*[×x]\s*(.+)$", first)
    if match:
        try:
            quantity = int(match.group(1))
        except ValueError:
            quantity = None
        base = match.group(2).strip()
    else:
        base = first

    descriptions = tokens[1:] if len(tokens) > 1 else []
    return FormatInfo(name=base, quantity=quantity, descriptions=descriptions)
