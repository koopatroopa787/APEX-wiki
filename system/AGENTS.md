# LLM Wiki Maintainer Contract

## Mission
Maintain a persistent markdown wiki from immutable sources. Prioritize accurate synthesis, explicit linking, traceable provenance, and reviewable promotion.

## Hard rules
1. Never edit files under `raw/`.
2. Always use wiki-links (`[[...]]`) for internal references.
3. Non-trivial claims must include source references.
4. Prefer updating existing pages over creating duplicates.
5. Every operation appends an entry to `logs/log.md`.
6. Keep `index.md` updated after ingest/output filing.
7. Save-first query behavior: useful answers go to `wiki/outputs/` by default.
8. New concepts/entities go to `wiki/candidates/` first; canonical pages are promoted via approval bundles.
9. Graph edges must be marked as `extracted`, `inferred`, or `ambiguous`.

## Required frontmatter for wiki pages
```yaml
id: <kebab-case-id>
type: entity|concept|topic|source|output
status: draft|active|superseded
updated_at: YYYY-MM-DD
source_refs: []
tags: []
confidence: low|medium|high
```

Optional but recommended:
- freshness_days
- community
- provenance_refs

## Ingest workflow
1. Read source from `raw/inbox/`.
2. Create/update `wiki/sources/<source>.md`.
3. Update impacted entity/concept/topic pages.
4. Update `index.md`.
5. Append ingest entry in `logs/log.md`.
6. Append machine event in `logs/ingest-history.jsonl`.
7. Move source to `raw/processed/` when complete.

## Query workflow
1. Read `index.md`, then relevant wiki pages.
2. Answer with citations to wiki pages and source pages.
3. Save answers to `wiki/outputs/<slug>.md` by default.
4. Link output page from related pages and `index.md`.

## Lint workflow
Check and report:
- contradictions,
- stale claims,
- orphan pages,
- missing high-value concept/entity pages,
- taxonomy drift,
- provenance gaps in graph edges.

