"""HTML parsers for Discogs search, release, and user pages."""

from __future__ import annotations

import re
from typing import Iterable, List, Optional, Tuple, cast

from bs4 import BeautifulSoup

from .models import (
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


_RE_RELEASE_ID = re.compile(r"/release/(\d+)")
_RE_USER_FROM_HREF = re.compile(r"/(user|seller)/([^/?#]+)")


def _extract_release_id(url: str) -> Optional[int]:
    match = _RE_RELEASE_ID.search(url)
    if match:
        return int(match.group(1))
    return None


def parse_search_results(html: str) -> List[ReleaseSummary]:
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select(".card, .card_large, .search_result")
    releases: List[ReleaseSummary] = []

    for card in cards:
        link = card.select_one("a[href*='/release/']")
        if not link or not link.get("href"):
            continue

        release_id = _extract_release_id(link["href"])
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

        releases.append(
            ReleaseSummary(
                release_id=release_id,
                title=title,
                artists=artists,
                year=year,
                url=link["href"],
                have_count=cast(Optional[int], stats.get("have")),
                want_count=cast(Optional[int], stats.get("want")),
                average_rating=cast(Optional[float], stats.get("avg_rating")),
                ratings_count=cast(Optional[int], stats.get("ratings")),
            )
        )

    return releases


def _parse_stats_list(container) -> dict[str, float | int | None]:
    stats: dict[str, float | int | None] = {}

    stat_items = container.select("li") or container.select(".card_stat")
    for item in stat_items:
        text = item.get_text(" ", strip=True).lower()
        if "have" in text:
            stats["have"] = coerce_int(text)
        elif "want" in text:
            stats["want"] = coerce_int(text)
        elif "avg" in text and "rating" in text:
            stats["avg_rating"] = coerce_float(_extract_number(text))
        elif "rating" in text:
            stats["ratings"] = coerce_int(text)

    return stats


def _extract_number(text: str) -> str:
    match = re.search(r"([0-9]+(?:[.,][0-9]+)?)", text)
    return match.group(1) if match else ""


def parse_release_detail(html: str) -> ReleaseDetail:
    soup = BeautifulSoup(html, "html.parser")

    title_el = soup.select_one("#profile_title, h1[itemprop='name'], h1.title")
    title = title_el.get_text(strip=True) if title_el else ""

    release_id = None
    canonical = soup.find("link", rel="canonical")
    if canonical and canonical.get("href"):
        release_id = _extract_release_id(canonical["href"])
    if release_id is None:
        # fallback: first review link maybe
        first_link = soup.select_one("a[href*='/release/']")
        release_id = _extract_release_id(first_link["href"]) if first_link else 0

    artist_el = soup.select_one(
        "#profile_title span[itemprop='byArtist'], h1 span.artist, h1 .profile"
    )
    artists = artist_el.get_text(" ", strip=True) if artist_el else ""

    year = None
    year_el = soup.find(string=re.compile("Released", re.I))
    if year_el and year_el.parent:
        year = coerce_year(year_el.parent.get_text(" ", strip=True))

    genres = _extract_profile_tags(soup, "Genre") or [
        tag.get_text(strip=True) for tag in soup.select("a[href*='/genre/']")
    ]

    styles = _extract_profile_tags(soup, "Style") or [
        tag.get_text(strip=True) for tag in soup.select("a[href*='/style/']")
    ]

    image_el = soup.select_one("meta[property='og:image']")
    image_url = image_el.get("content") if image_el else None

    have_users, want_users = _parse_statistics_users(soup)
    reviews = _parse_reviews(soup)

    return ReleaseDetail(
        release_id=release_id or 0,
        title=title,
        artists=artists,
        year=year,
        genres=genres,
        styles=styles,
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
                # Some pages expose a data attribute instead of href
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
        # Fallback: look for data-username spans/buttons
        _append_from_elements(soup.select("[data-username]"))

    return unique(usernames)


def _parse_statistics_users(soup: BeautifulSoup) -> Tuple[List[str], List[str]]:
    have_users: List[str] = []
    want_users: List[str] = []

    # Discogs a veces presenta estadísticas en tooltips con data-attributes
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
            # fallback: inspect data attribute
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
        body_el = node.select_one(".review_body, .content, .body, p")
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
    rating_el = node.select_one("[data-rating], .rating")
    if rating_el:
        # data-rating es 1-5, rating text puede ser "4.5 of 5"
        data_rating = rating_el.get("data-rating")
        if data_rating:
            rating = coerce_float(data_rating)
            if rating is not None and rating > 5:
                rating = rating / 100
            return rating
        aria_label = rating_el.get("aria-label")
        if aria_label:
            return coerce_float(_extract_number(aria_label))
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
