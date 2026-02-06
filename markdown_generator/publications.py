from __future__ import annotations

import argparse
import csv
import datetime as dt
import pathlib
import re
import sys
from typing import Dict

REQUIRED_COLUMNS = ("pub_date", "title", "venue", "citation")
SCRIPT_DIR = pathlib.Path(__file__).resolve().parent


def normalize(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none"} else text


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "publication"


def yaml_quote(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def parse_iso_date(value: str) -> str:
    dt.date.fromisoformat(value)
    return value


def write_if_changed(path: pathlib.Path, content: str, dry_run: bool) -> str:
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return "unchanged"

    if dry_run:
        return "dry-run"

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return "written"


def render_markdown(row: Dict[str, str]) -> tuple[str, str]:
    pub_date = parse_iso_date(normalize(row.get("pub_date")))
    title = normalize(row.get("title"))
    venue = normalize(row.get("venue"))
    citation = normalize(row.get("citation"))
    excerpt = normalize(row.get("excerpt"))
    paper_url = normalize(row.get("paper_url"))
    slides_url = normalize(row.get("slides_url"))
    url_slug = normalize(row.get("url_slug")) or slugify(title)

    html_filename = f"{pub_date}-{url_slug}"
    md_filename = f"{html_filename}.md"

    front_matter = [
        "---",
        f"title: {yaml_quote(title)}",
        "collection: publications",
        f"permalink: /publication/{html_filename}",
        f"date: {pub_date}",
        f"venue: {yaml_quote(venue)}",
    ]

    if excerpt:
        front_matter.append(f"excerpt: {yaml_quote(excerpt)}")
    if paper_url:
        front_matter.append(f"paperurl: {yaml_quote(paper_url)}")
    if slides_url:
        front_matter.append(f"slidesurl: {yaml_quote(slides_url)}")

    front_matter.append(f"citation: {yaml_quote(citation)}")
    front_matter.append("---")

    body = []
    if paper_url:
        body.append(f"[Download paper]({paper_url})")
    if slides_url:
        body.append(f"[Download slides]({slides_url})")
    if excerpt:
        body.append(excerpt)

    body.append(f"Recommended citation: {citation}")

    markdown = "\n".join(front_matter) + "\n\n" + "\n\n".join(body).rstrip() + "\n"
    return md_filename, markdown


def process_file(input_path: pathlib.Path, output_dir: pathlib.Path, dry_run: bool) -> int:
    with input_path.open("r", encoding="utf-8-sig", newline="") as file_handle:
        reader = csv.DictReader(file_handle, delimiter="\t")
        if not reader.fieldnames:
            print("ERROR: TSV header is missing.", file=sys.stderr)
            return 1

        missing_columns = [column for column in REQUIRED_COLUMNS if column not in reader.fieldnames]
        if missing_columns:
            print(f"ERROR: Missing required TSV columns: {', '.join(missing_columns)}", file=sys.stderr)
            return 1

        seen_filenames = set()
        total_rows = 0
        skipped_rows = 0
        written_files = 0
        unchanged_files = 0

        for row_index, row in enumerate(reader, start=2):
            total_rows += 1

            missing_values = [
                column for column in REQUIRED_COLUMNS if not normalize(row.get(column))
            ]
            if missing_values:
                skipped_rows += 1
                print(
                    f"WARNING row {row_index}: missing required values: {', '.join(missing_values)}",
                    file=sys.stderr,
                )
                continue

            try:
                md_filename, markdown = render_markdown(row)
            except ValueError as error:
                skipped_rows += 1
                print(f"WARNING row {row_index}: {error}", file=sys.stderr)
                continue

            if md_filename in seen_filenames:
                skipped_rows += 1
                print(f"WARNING row {row_index}: duplicate output filename {md_filename}", file=sys.stderr)
                continue

            seen_filenames.add(md_filename)

            status = write_if_changed(output_dir / md_filename, markdown, dry_run=dry_run)
            if status == "unchanged":
                unchanged_files += 1
            else:
                written_files += 1

        mode_text = "dry-run" if dry_run else "write"
        print(
            f"publications: mode={mode_text} rows={total_rows} written={written_files} "
            f"unchanged={unchanged_files} skipped={skipped_rows}"
        )

    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate publication markdown files from a TSV source.")
    parser.add_argument(
        "--input",
        default=str(SCRIPT_DIR / "publications.tsv"),
        help="Path to the publications TSV file.",
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
    input_path = pathlib.Path(args.input)
    output_dir = pathlib.Path(args.output_dir)

    if not input_path.exists():
        print(f"ERROR: Input TSV does not exist: {input_path}", file=sys.stderr)
        return 1

    return process_file(input_path=input_path, output_dir=output_dir, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
