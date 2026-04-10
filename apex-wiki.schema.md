# apex-wiki.schema.md

## naming rules
- concepts: `concept-<kebab-case>`
- entities: `entity-<kebab-case>`
- topics: `topic-<kebab-case>`
- sources: `source-<kebab-case>`
- outputs: `<timestamp>-<kebab-case>`

## categories
- entity
- concept
- topic
- source
- output

## grounding requirements
1. Each non-trivial claim must be traceable to at least one source page.
2. Every graph edge carries provenance and kind (`extracted|inferred|ambiguous`).
3. Contradictions must be surfaced in dashboards and lint reports.
4. Confidence tags must be present on generated pages (`low|medium|high`).

## compilation requirements
1. New concepts/entities compile into `wiki/candidates/` first.
2. `compile --approve` stages approval bundles under `state/approval-bundles/`.
3. Canonical mutation should happen through explicit bundle application.
4. Guided session mode routes promoted pages to canonical folders or `wiki/insights/`.

