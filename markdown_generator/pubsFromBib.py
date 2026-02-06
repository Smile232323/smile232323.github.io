#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import html
import pathlib
import re
import sys
from dataclasses import dataclass
from typing import Dict, Iterable, Tuple

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent


@dataclass(frozen=True)
class SourceConfig:
    file: pathlib.Path
    venue_key: str
    venue_prefix: str
    collection_name: str = "publications"
    collection_permalink: str = "/publication/"


DEFAULT_SOURCES: Dict[str, SourceConfig] = {
    "proceeding": SourceConfig(
        file=SCRIPT_DIR / "proceedings.bib",
        venue_key="booktitle",
        venue_prefix="In the proceedings of ",
    ),
    "journal": SourceConfig(
        file=SCRIPT_DIR / "pubs.bib",
        venue_key="journal",
        venue_prefix="",
    ),
}

MONTH_NAME_MAP = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


def normalize(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none"} else text


def strip_bibtex_markup(text: str) -> str:
    return normalize(text).replace("{", "").replace("}", "").replace("\\", "")


def yaml_quote(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "publication"


def parse_month(value: str) -> int:
    raw = normalize(value)
    if not raw:
        return 1

    cleaned = raw.strip("{} ").lower()

    if cleaned.isdigit():
        month = int(cleaned)
        if 1 <= month <= 12:
            return month
        raise ValueError(f"invalid month number: {value}")

    month_token = cleaned[:3]
    if month_token in MONTH_NAME_MAP:
        return MONTH_NAME_MAP[month_token]

    raise ValueError(f"invalid month format: {value}")


def parse_day(value: str) -> int:
    raw = normalize(value)
    if not raw:
        return 1

    cleaned = raw.strip("{} ")
    if cleaned.isdigit():
        day = int(cleaned)
        if 1 <= day <= 31:
            return day

    raise ValueError(f"invalid day format: {value}")


def parse_date(fields: Dict[str, str]) -> str:
    raw_year = normalize(fields.get("year"))
    if not raw_year or not raw_year.isdigit():
        raise ValueError("missing or invalid year")

    year = int(raw_year)
    month = parse_month(fields.get("month", "1"))
    day = parse_day(fields.get("day", "1"))

    try:
        return dt.date(year, month, day).isoformat()
    except ValueError as error:
        raise ValueError(f"invalid date combination: {error}") from error


def build_citation(entry, title: str, venue: str, year: str) -> str:
    author_parts = []
    for author in entry.persons.get("author", []):
        first = normalize(" ".join(author.first_names))
        last = normalize(" ".join(author.last_names))
        full_name = normalize(f"{first} {last}")
        if full_name:
            author_parts.append(full_name)

    author_text = ", ".join(author_parts)
    components = [author_text, f'"{title}."', venue, f"{year}."]
    return " ".join(part for part in components if part).strip()


def render_markdown(
    title: str,
    pub_date: str,
    venue: str,
    citation: str,
    permalink: str,
    collection_name: str,
    note: str,
    paper_url: str,
) -> str:
    front_matter = [
        "---",
        f"title: {yaml_quote(title)}",
        f"collection: {collection_name}",
        f"permalink: {permalink}",
        f"date: {pub_date}",
        f"venue: {yaml_quote(venue)}",
    ]

    if note:
        front_matter.append(f"excerpt: {yaml_quote(note)}")
    if paper_url:
        front_matter.append(f"paperurl: {yaml_quote(paper_url)}")

    front_matter.append(f"citation: {yaml_quote(citation)}")
    front_matter.append("---")

    body = []
    if note:
        body.append(note)

    if paper_url:
        body.append(f"[Access paper here]({paper_url})")
    else:
        scholar_query = html.escape(title.replace(" ", "+"))
        body.append(
            "Use "
            f"[Google Scholar](https://scholar.google.com/scholar?q={scholar_query}) "
            "for full citation"
        )

    return "\n".join(front_matter) + "\n\n" + "\n\n".join(body).rstrip() + "\n"


def write_if_changed(path: pathlib.Path, content: str, dry_run: bool) -> str:
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return "unchanged"

    if dry_run:
        return "dry-run"

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return "written"


def iter_sources(selected_sources: Iterable[str]) -> Iterable[Tuple[str, SourceConfig]]:
    for source_name in selected_sources:
        config = DEFAULT_SOURCES.get(source_name)
        if config is None:
            raise ValueError(f"unknown source: {source_name}")
        yield source_name, config


def create_bib_parser() -> object | None:
    try:
        from pybtex.database.input import bibtex
    except ImportError:
        return None

    return bibtex.Parser()


def process_source(
    source_name: str,
    config: SourceConfig,
    output_dir: pathlib.Path,
    dry_run: bool,
    parser: object,
) -> tuple[int, int, int, int]:
    if not config.file.exists():
        print(f"WARNING source={source_name}: missing bib file: {config.file}", file=sys.stderr)
        return 0, 0, 0, 0

    bibdata = parser.parse_file(str(config.file))

    written_files = 0
    unchanged_files = 0
    skipped_entries = 0
    total_entries = 0

    seen_filenames = set()

    for bib_id, entry in bibdata.entries.items():
        total_entries += 1
        fields = entry.fields

        try:
            title = strip_bibtex_markup(fields["title"])
            pub_date = parse_date(fields)
            year = pub_date[:4]
            venue_raw = strip_bibtex_markup(fields[config.venue_key])
            venue = normalize(f"{config.venue_prefix}{venue_raw}")
            note = strip_bibtex_markup(fields.get("note", ""))
            paper_url = normalize(fields.get("url", ""))

            url_slug = slugify(title)
            html_filename = f"{pub_date}-{url_slug}"
            md_filename = f"{html_filename}.md"

            if md_filename in seen_filenames:
                skipped_entries += 1
                print(
                    f"WARNING source={source_name} id={bib_id}: duplicate output filename {md_filename}",
                    file=sys.stderr,
                )
                continue

            seen_filenames.add(md_filename)

            citation = build_citation(entry=entry, title=title, venue=venue, year=year)
            permalink = f"{config.collection_permalink}{html_filename}"

            markdown = render_markdown(
                title=title,
                pub_date=pub_date,
                venue=venue,
                citation=citation,
                permalink=permalink,
                collection_name=config.collection_name,
                note=note,
                paper_url=paper_url,
            )

            status = write_if_changed(output_dir / md_filename, markdown, dry_run=dry_run)
            if status == "unchanged":
                unchanged_files += 1
            else:
                written_files += 1

            print(f"parsed source={source_name} id={bib_id} file={md_filename}")
        except KeyError as error:
            skipped_entries += 1
            print(
                f"WARNING source={source_name} id={bib_id}: missing expected field {error}",
                file=sys.stderr,
            )
        except ValueError as error:
            skipped_entries += 1
            print(
                f"WARNING source={source_name} id={bib_id}: {error}",
                file=sys.stderr,
            )

    return total_entries, written_files, unchanged_files, skipped_entries


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate publication markdown files from BibTeX sources."
    )
    parser.add_argument(
        "--sources",
        nargs="+",
        default=tuple(DEFAULT_SOURCES.keys()),
        help="Source names to process (default: all).",
    )
    parser.add_argument(
        "--output-dir",
        default=str(SCRIPT_DIR.parent / "_publications"),
        help="Directory where generated markdown files are written.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and render without writing files.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = pathlib.Path(args.output_dir)

    parser = create_bib_parser()
    if parser is None:
        print(
            "WARNING: pybtex is not installed. Install with `pip install pybtex` to enable BibTeX generation.",
            file=sys.stderr,
        )
        print("pubsFromBib: mode=skipped entries=0 written=0 unchanged=0 skipped=0")
        return 0

    try:
        source_iter = list(iter_sources(args.sources))
    except ValueError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    total_entries = 0
    written_files = 0
    unchanged_files = 0
    skipped_entries = 0

    for source_name, config in source_iter:
        total, written, unchanged, skipped = process_source(
            source_name=source_name,
            config=config,
            output_dir=output_dir,
            dry_run=args.dry_run,
            parser=parser,
        )
        total_entries += total
        written_files += written
        unchanged_files += unchanged
        skipped_entries += skipped

    mode_text = "dry-run" if args.dry_run else "write"
    print(
        f"pubsFromBib: mode={mode_text} entries={total_entries} written={written_files} "
        f"unchanged={unchanged_files} skipped={skipped_entries}"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
