"""
scrapers.crossref — Crossref research knowledge ingestion & enrichment package.

Modules
-------
doi_utils       — Canonicalization and validation of DOIs
models          — Normalized internal representations of Crossref works, authors, and sources
response_models — Structural dataclasses mirroring Crossref API JSON messages
client          — HTTP client for Crossref REST API (polite pool, 429 backoff, retries)
normalizer      — Raw Crossref JSON → normalized models (JATS XML cleaning, author/date parsing)
validator       — Validation rules for normalized Crossref models
enricher        — Metadata enrichment & precedence logic for research_works
"""
