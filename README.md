# APEX-wiki Local Implementation

This vault is an Obsidian-first, LLM-assisted persistent knowledge system.

## Highlights implemented
- Schema-guided compilation via `apex-wiki.schema.md`
- Save-first queries into `wiki/outputs/`
- Managed sources (`source add|list|reload|review|guide|session|delete`)
- Guided sessions under `wiki/outputs/source-sessions/`
- Approval bundles in `state/approval-bundles/`
- Knowledge graph with provenance, confidence, freshness, communities, god/bridge nodes
- Contradiction detection (`lint --conflicts`)
- Semantic auto-tagging in frontmatter + graph nodes
- Dashboards in `wiki/dashboards/`
- Optional model providers (heuristic + API-backed adapters)
- MCP stdio server (`apex-wiki.py mcp`)
- Automation helpers (watch, git hooks, schedule, inbox import)
- External graph sinks (HTML/SVG/GraphML/Cypher + optional Neo4j push)

## Core commands
- `python scripts/apex-wiki.py source add "name" "path-or-url" --guide`
- `python scripts/apex-wiki.py source reload <source-id> --guide`
- `python scripts/apex-wiki.py ingest <source-id> --guide`
- `python scripts/apex-wiki.py compile --approve`
- `python scripts/apex-wiki.py bundle list`
- `python scripts/apex-wiki.py bundle apply <bundle-id>`
- `python scripts/apex-wiki.py lint --conflicts`
- `python scripts/apex-wiki.py graph`
- `python scripts/apex-wiki.py query "question" --format markdown`
- `python scripts/apex-wiki.py dashboards`
- `python scripts/apex-wiki.py mcp`
- `powershell -ExecutionPolicy Bypass -File scripts/publish-github.ps1 -Owner <your-username> -Repo APEX-wiki`

## Model providers
Supported in config:
- heuristic (offline/local)
- anthropic native API
- OpenAI-compatible endpoints (OpenAI, Gemini OpenAI-compatible endpoint, Ollama, OpenRouter, Groq, Together, xAI, Cerebras, generic OpenAI-compatible)
- custom adapter placeholder (command-based)

Provider behavior:
- If provider is not configured with API key/base URL, query falls back to heuristic pipeline and records diagnostics.

## Obsidian + manual edits
Manual edits are supported and expected. The compiler writes new material into `wiki/candidates/` first; canonical pages update only through approval bundles.

## MCP server list config
Use `system/agent-integrations/mcp-servers.jsonc` as a shared MCP list entry for clients that support file-based MCP server configuration.
