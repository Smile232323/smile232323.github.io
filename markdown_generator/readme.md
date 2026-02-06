# Markdown generator

`markdown_generator/publications.py` and `markdown_generator/talks.py` convert TSV files into Jekyll collection markdown files.
`markdown_generator/pubsFromBib.py` converts BibTeX files into publication markdown files.

## Usage

From this `markdown_generator` directory:

```bash
python3 publications.py --dry-run
python3 publications.py

python3 talks.py --dry-run
python3 talks.py

python3 pubsFromBib.py --dry-run
python3 pubsFromBib.py
```

## Inputs

- `publications.tsv` requires: `pub_date`, `title`, `venue`, `citation`
- `talks.tsv` requires: `title`, `date`

Optional columns are preserved when present (`url_slug`, `excerpt`, `paper_url`, `slides_url`, `type`, `location`, `talk_url`, `description`).

## Behaviors

- Validates required columns and ISO dates (`YYYY-MM-DD`)
- Auto-generates slug from title when `url_slug` is empty
- Skips invalid rows with clear warnings
- Writes files idempotently (unchanged content is not rewritten)
- Supports `--input`, `--output-dir`, and `--dry-run`

## BibTeX source behavior

- `pubsFromBib.py` reads configured BibTeX sources in `markdown_generator/`
- Validates year/month/day with stricter parsing and graceful warnings
- Generates deterministic slugs and skips duplicate filename collisions
- Supports `--sources`, `--output-dir`, and `--dry-run`
