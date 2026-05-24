# apex-wiki.schema.md

## naming
- concepts: kebab-case, prefix concept-
- entities: kebab-case, prefix entity-
- sources: kebab-case, prefix source-
- outputs: timestamp-prefixed slugs

## categories
- concept
- entity
- topic
- source
- output

## grounding
- every non-trivial claim needs source provenance
- confidence must be one of: low, medium, high
- contradictions should be surfaced in dashboards and lint reports

## compilation-rules
- new concepts and entities compile into wiki/candidates first
- canonical pages are updated through approval bundles only
- preserve manual edits and append inferred notes in separate sections
