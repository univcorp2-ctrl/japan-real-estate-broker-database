# CODEX.md

## Project intent

Maintain a source-backed database of Japanese real-estate brokerages, with emphasis on detached houses, income-producing properties, contact forms, and clickable official URLs.

## Required checks

- Never invent company facts.
- Mark uncertain values as `要確認`.
- Keep source URLs and verification dates.
- Run `ruff check src tests`, `pytest -q`, and `python -m real_estate_db.build_excel` before committing.
- Do not commit API tokens or credentials.

## Data contract

The canonical source is `data/real_estate_brokers.csv`. Generated files under `database/` must be produced by `real_estate_db.build_excel`.
