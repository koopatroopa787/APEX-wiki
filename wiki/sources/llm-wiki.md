---
id: source-llm-wiki
type: source
status: active
updated_at: 2026-04-10
source_refs:
  - source://raw/inbox/llm-wiki-idea-c240874d/LLM Wiki.md
tags:
  - ai-agents
  - claim
  - ingest
  - knowledge-management
  - llm
  - rag
confidence: high
---

# LLM Wiki

            ## Summary
            A pattern for building personal knowledge bases using LLMs. This is an idea file, it is designed to be copy pasted to your own LLM Agent (e.g. OpenAI Codex, Claude Code, OpenCode / Pi, or etc.). Its goal is to communicate the high level idea, but your agent will build out the specifics in collaboration with you.

            ## Claims
            - [claim:c001] Look for: contradictions between pages, stale claims that newer sources have superseded, orphan pages with no inbound links, important concepts mentioned but lacking their own page, missing cross-references, data gaps that could be filled with a web search.
- [claim:c002] It reads it, extracts the key information, and integrates it into the existing wiki — updating entity pages, revising topic summaries, noting where new data contradicts old claims, strengthening or challenging the evolving synthesis.
- [claim:c003] Instead of just retrieving from raw documents at query time, the LLM **incrementally builds and maintains a persistent wiki** — a structured, interlinked collection of markdown files that sits between you and the raw sources.
- [claim:c004] An example flow: the LLM reads the source, discusses key takeaways with you, writes a summary page in the wiki, updates the index, updates relevant entity and concept pages across the wiki, and appends an entry to the log.
- [claim:c005] CLAUDE.md for Claude Code or AGENTS.md for Codex) that tells the LLM how the wiki is structured, what the conventions are, and what workflows to follow when ingesting sources, answering questions, or maintaining the wiki.
- [claim:c006] The important insight: **good answers can be filed back into the wiki as new pages.** A comparison you asked for, an analysis, a connection you discovered — these are valuable and shouldn't disappear into chat history.
- [claim:c007] Note that LLMs can't natively read markdown with inline images in one pass — the workaround is to have the LLM read the text first, then view some or all of the referenced images separately to gain additional context.
- [claim:c008] Think of fan wikis like [Tolkien Gateway](https://tolkiengateway.net/wiki/Main_Page) — thousands of interlinked pages covering characters, places, events, languages, built by a community of volunteers over years.

            ## Provenance
            - source_file: `E:\Anti-gravity\LLM-wiki\knowledge-system\raw\inbox\llm-wiki-idea-c240874d\LLM Wiki.md`
            - ingested_at: `2026-04-10T10:04:01+00:00`
            - provider: `heuristic`

            ## Related pages
            - [[llm-wiki]]
