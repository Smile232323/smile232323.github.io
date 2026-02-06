from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from typing import Dict, List

LOCATION_PATTERN = re.compile(r"^location:\s*(.+)$", re.IGNORECASE)
REPO_ROOT = pathlib.Path(__file__).resolve().parent


def clean_location_value(raw_value: str) -> str:
    value = raw_value.strip()
    if not value:
        return ""

    if value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1].strip()

    return value


def extract_front_matter(text: str) -> str:
    if not text.startswith("---"):
        return ""

    parts = text.split("---", 2)
    if len(parts) < 3:
        return ""

    return parts[1]


def extract_location(markdown_path: pathlib.Path) -> str:
    try:
        text = markdown_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = markdown_path.read_text(encoding="utf-8", errors="ignore")

    front_matter = extract_front_matter(text)
    if not front_matter:
        return ""

    for line in front_matter.splitlines():
        match = LOCATION_PATTERN.match(line.strip())
        if not match:
            continue

        location = clean_location_value(match.group(1))
        if location:
            return location

    return ""


def load_cache(path: pathlib.Path) -> Dict[str, Dict[str, float]]:
    if not path.exists():
        return {}

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def load_existing_output_cache(path: pathlib.Path) -> Dict[str, Dict[str, float]]:
    if not path.exists():
        return {}

    text = path.read_text(encoding="utf-8")
    if "=" not in text:
        return {}

    _, payload = text.split("=", 1)
    payload = payload.strip()
    if payload.endswith(";"):
        payload = payload[:-1].strip()

    try:
        points = json.loads(payload)
    except json.JSONDecodeError:
        return {}

    cache: Dict[str, Dict[str, float]] = {}
    for point in points:
        if not isinstance(point, list) or len(point) < 3:
            continue

        location = str(point[0]).strip()
        if not location:
            continue

        try:
            latitude = float(point[1])
            longitude = float(point[2])
        except (TypeError, ValueError):
            continue

        cache[location] = {"latitude": latitude, "longitude": longitude}

    return cache


def save_cache(path: pathlib.Path, cache: Dict[str, Dict[str, float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(cache, ensure_ascii=False, indent=2, sort_keys=True)
    path.write_text(serialized + "\n", encoding="utf-8")


def load_locations(talks_dir: pathlib.Path) -> List[str]:
    locations = set()

    for markdown_path in sorted(talks_dir.glob("*.md")):
        location = extract_location(markdown_path)
        if location:
            locations.add(location)

    return sorted(locations)


def geocode_missing_locations(
    locations: List[str],
    cache: Dict[str, Dict[str, float]],
    user_agent: str,
    min_delay: float,
    lookup_limit: int,
) -> tuple[int, int]:
    missing_locations = [
        location
        for location in locations
        if not cache.get(location) or "latitude" not in cache[location] or "longitude" not in cache[location]
    ]

    if lookup_limit > 0:
        missing_locations = missing_locations[:lookup_limit]

    if not missing_locations:
        return 0, 0

    try:
        from geopy import Nominatim
        from geopy.extra.rate_limiter import RateLimiter
    except ImportError:
        print(
            "ERROR: geopy is required for geocoding. Install it with `pip install geopy`.",
            file=sys.stderr,
        )
        return 0, len(missing_locations)

    geocoder = Nominatim(user_agent=user_agent, timeout=10)
    geocode = RateLimiter(geocoder.geocode, min_delay_seconds=min_delay, swallow_exceptions=True)

    resolved = 0
    unresolved = 0

    for location in missing_locations:
        result = geocode(location)
        if result is None:
            unresolved += 1
            continue

        cache[location] = {
            "latitude": float(result.latitude),
            "longitude": float(result.longitude),
        }
        resolved += 1

    return resolved, unresolved


def build_address_points(
    locations: List[str], cache: Dict[str, Dict[str, float]]
) -> tuple[List[List[float]], int]:
    points: List[List[float]] = []
    unresolved = 0

    for location in locations:
        location_data = cache.get(location)
        if not location_data:
            unresolved += 1
            continue

        latitude = location_data.get("latitude")
        longitude = location_data.get("longitude")

        if latitude is None or longitude is None:
            unresolved += 1
            continue

        points.append([location, float(latitude), float(longitude)])

    return points, unresolved


def write_locations_js(path: pathlib.Path, points: List[List[float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "var addressPoints = " + json.dumps(points, ensure_ascii=False, indent=2) + ";\n"
    path.write_text(content, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate talk map data from location fields in talk markdown files."
    )
    parser.add_argument(
        "--talks-dir",
        default=str(REPO_ROOT / "_talks"),
        help="Directory containing talk markdown files.",
    )
    parser.add_argument(
        "--output-js",
        default=str(REPO_ROOT / "talkmap/org-locations.js"),
        help="Path to generated JavaScript data file.",
    )
    parser.add_argument(
        "--cache-file",
        default=str(REPO_ROOT / "talkmap/geocode-cache.json"),
        help="Path to geocode cache JSON file.",
    )
    parser.add_argument(
        "--user-agent",
        default="smile232323-talkmap-generator",
        help="Nominatim user-agent used for geocoding requests.",
    )
    parser.add_argument(
        "--min-delay",
        type=float,
        default=1.1,
        help="Minimum delay in seconds between geocode requests.",
    )
    parser.add_argument(
        "--lookup-limit",
        type=int,
        default=0,
        help="Maximum number of uncached locations to geocode in this run. 0 means no limit.",
    )
    parser.add_argument(
        "--skip-geocode",
        action="store_true",
        help="Do not call external geocoding APIs; use cache only.",
    )
    parser.add_argument(
        "--allow-empty-output",
        action="store_true",
        help="Allow writing an empty addressPoints list when no coordinates are resolved.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    talks_dir = pathlib.Path(args.talks_dir)
    output_js = pathlib.Path(args.output_js)
    cache_file = pathlib.Path(args.cache_file)

    if not talks_dir.exists():
        print(f"talkmap: talks directory not found: {talks_dir}; skip updating {output_js}")
        return 0

    locations = load_locations(talks_dir)
    cache = load_cache(cache_file)

    existing_output_cache = load_existing_output_cache(output_js)
    for location, coordinates in existing_output_cache.items():
        cache.setdefault(location, coordinates)

    resolved = 0
    geocode_unresolved = 0

    if not args.skip_geocode:
        resolved, geocode_unresolved = geocode_missing_locations(
            locations=locations,
            cache=cache,
            user_agent=args.user_agent,
            min_delay=args.min_delay,
            lookup_limit=args.lookup_limit,
        )

    points, unresolved_from_cache = build_address_points(locations, cache)

    if locations and not points and not args.allow_empty_output:
        save_cache(cache_file, cache)
        print(
            f"talkmap: locations={len(locations)} points=0 unresolved={len(locations)}; "
            f"skip updating {output_js} (use --allow-empty-output to force)"
        )
        return 0

    save_cache(cache_file, cache)
    write_locations_js(output_js, points)

    unresolved_total = geocode_unresolved + unresolved_from_cache
    print(
        f"talkmap: locations={len(locations)} points={len(points)} "
        f"new_geocodes={resolved} unresolved={unresolved_total}"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
