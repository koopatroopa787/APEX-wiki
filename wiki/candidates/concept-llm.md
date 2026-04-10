---
id: concept-llm
type: concept
status: draft
updated_at: 2026-04-10
source_refs:
  - wiki/sources/llm-wiki.md
tags:
  - ai-agents
  - knowledge-management
  - llm
confidence: high
---

# llm

        ## Candidate summary
        Auto-compiled candidate from source claims. Review before promotion.

        ## Evidence
        - [c003] Instead of just retrieving from raw documents at query time, the LLM **incrementally builds and maintains a persistent wiki** — a structured, interlinked collection of markdown files that sits between you and the raw sources. (from [[wiki/sources/llm-wiki]])
- [c004] An example flow: the LLM reads the source, discusses key takeaways with you, writes a summary page in the wiki, updates the index, updates relevant entity and concept pages across the wiki, and appends an entry to the log. (from [[wiki/sources/llm-wiki]])
- [c005] CLAUDE.md for Claude Code or AGENTS.md for Codex) that tells the LLM how the wiki is structured, what the conventions are, and what workflows to follow when ingesting sources, answering questions, or maintaining the wiki. (from [[wiki/sources/llm-wiki]])
- [c007] Note that LLMs can't natively read markdown with inline images in one pass — the workaround is to have the LLM read the text first, then view some or all of the referenced images separately to gain additional context. (from [[wiki/sources/llm-wiki]])

        ## Notes
        - This page is generated in `wiki/candidates/`.
        - Promotion to canonical pages should happen through approval bundles.
