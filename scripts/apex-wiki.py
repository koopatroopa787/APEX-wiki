#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import re
import shutil
import sys
import textwrap
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "raw"
WIKI_DIR = ROOT / "wiki"
STATE_DIR = ROOT / "state"
LOGS_DIR = ROOT / "logs"
EXPORT_GRAPH_DIR = ROOT / "exports" / "graph"
SYSTEM_DIR = ROOT / "system"
CONFIG_PATH = ROOT / "apex-wiki.config.json"
SCHEMA_PATH = ROOT / "apex-wiki.schema.md"
SOURCES_STATE_PATH = STATE_DIR / "sources.json"
DIAGNOSTICS_PATH = LOGS_DIR / "diagnostics.jsonl"
APPROVAL_BUNDLES_DIR = STATE_DIR / "approval-bundles"

WIKI_SOURCES_DIR = WIKI_DIR / "sources"
WIKI_ENTITIES_DIR = WIKI_DIR / "entities"
WIKI_CONCEPTS_DIR = WIKI_DIR / "concepts"
WIKI_TOPICS_DIR = WIKI_DIR / "topics"
WIKI_OUTPUTS_DIR = WIKI_DIR / "outputs"
WIKI_DASHBOARDS_DIR = WIKI_DIR / "dashboards"
WIKI_CANDIDATES_DIR = WIKI_DIR / "candidates"
WIKI_INSIGHTS_DIR = WIKI_DIR / "insights"

SOURCE_BRIEFS_DIR = WIKI_OUTPUTS_DIR / "source-briefs"
SOURCE_SESSIONS_DIR = WIKI_OUTPUTS_DIR / "source-sessions"
SOURCE_GUIDES_DIR = WIKI_OUTPUTS_DIR / "source-guides"
OUTPUT_ASSETS_DIR = WIKI_OUTPUTS_DIR / "assets"

LINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
CLAIM_RE = re.compile(r"\[claim:([^\]]+)\]\s*(.+)")
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9\-]+")
SUPPORTED_SOURCE_EXTS = {
    ".md",
    ".txt",
    ".rst",
    ".adoc",
    ".json",
    ".csv",
    ".html",
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".go",
    ".java",
    ".rs",
    ".c",
    ".cpp",
    ".h",
    ".hpp",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".sql",
    ".sh",
    ".ps1",
    ".dockerfile",
}
STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "this",
    "that",
    "from",
    "into",
    "look",
    "note",
    "instead",
    "between",
    "there",
    "their",
    "about",
    "while",
    "where",
    "which",
    "would",
    "could",
    "should",
    "when",
    "what",
    "how",
    "have",
    "has",
    "been",
    "being",
    "were",
    "was",
    "also",
    "just",
    "more",
    "less",
}

DEFAULT_CONFIG: dict[str, Any] = {
    "vaultId": "llm-wiki",
    "linkedVaults": [],
    "profile": {
        "presets": ["personal-research"],
        "dashboardPack": "default",
        "guidedSessionMode": "canonical",
        "dataviewBlocks": False,
    },
    "model": {
        "provider": "heuristic",
        "model": "heuristic-v1",
    },
    "graph": {
        "includeLinkedDefault": False,
    },
    "providers": {
        "heuristic": {"enabled": True},
        "openai": {"baseUrl": "https://api.openai.com/v1/chat/completions", "apiKeyEnv": "OPENAI_API_KEY", "enabled": False},
        "anthropic": {"baseUrl": "https://api.anthropic.com/v1/messages", "apiKeyEnv": "ANTHROPIC_API_KEY", "enabled": False},
        "gemini": {"baseUrl": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", "apiKeyEnv": "GEMINI_API_KEY", "enabled": False},
        "ollama": {"baseUrl": "http://localhost:11434/v1/chat/completions", "apiKeyEnv": "", "enabled": False},
        "openrouter": {"baseUrl": "https://openrouter.ai/api/v1/chat/completions", "apiKeyEnv": "OPENROUTER_API_KEY", "enabled": False},
        "groq": {"baseUrl": "https://api.groq.com/openai/v1/chat/completions", "apiKeyEnv": "GROQ_API_KEY", "enabled": False},
        "together": {"baseUrl": "https://api.together.xyz/v1/chat/completions", "apiKeyEnv": "TOGETHER_API_KEY", "enabled": False},
        "xai": {"baseUrl": "https://api.x.ai/v1/chat/completions", "apiKeyEnv": "XAI_API_KEY", "enabled": False},
        "cerebras": {"baseUrl": "https://api.cerebras.ai/v1/chat/completions", "apiKeyEnv": "CEREBRAS_API_KEY", "enabled": False},
        "openai-compatible": {"baseUrl": "", "apiKeyEnv": "OPENAI_API_KEY", "enabled": False},
        "custom": {"enabled": False, "command": ""},
    },
    "semanticTagRules": {
        "llm": ["llm", "language model", "transformer", "token"],
        "ai-agents": ["agent", "tool use", "autonomous", "workflow"],
        "rag": ["retrieval", "rag", "embedding", "vector", "chunk"],
        "knowledge-management": ["knowledge", "wiki", "index", "taxonomy", "ontology"],
        "obsidian": ["obsidian", "vault", "dataview", "graph view", "wikilink"],
    },
}

DEFAULT_SCHEMA = textwrap.dedent(
    """\
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
    """
)


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def today() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d")


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "untitled"


def ensure_dirs() -> None:
    for p in [
        RAW_DIR / "inbox",
        RAW_DIR / "processed",
        RAW_DIR / "assets",
        WIKI_SOURCES_DIR,
        WIKI_ENTITIES_DIR,
        WIKI_CONCEPTS_DIR,
        WIKI_TOPICS_DIR,
        WIKI_OUTPUTS_DIR,
        WIKI_DASHBOARDS_DIR,
        WIKI_CANDIDATES_DIR,
        WIKI_INSIGHTS_DIR,
        SOURCE_BRIEFS_DIR,
        SOURCE_SESSIONS_DIR,
        SOURCE_GUIDES_DIR,
        OUTPUT_ASSETS_DIR,
        STATE_DIR,
        APPROVAL_BUNDLES_DIR,
        LOGS_DIR,
        EXPORT_GRAPH_DIR,
        SYSTEM_DIR / "agent-integrations",
    ]:
        p.mkdir(parents=True, exist_ok=True)


def read_text(path: Path, default: str = "") -> str:
    if not path.exists():
        return default
    return path.read_text(encoding="utf-8", errors="ignore")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def merge_dict(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = merge_dict(out[k], v)
        else:
            out[k] = v
    return out


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        save_json(CONFIG_PATH, DEFAULT_CONFIG)
        return DEFAULT_CONFIG
    return merge_dict(DEFAULT_CONFIG, load_json(CONFIG_PATH, {}))


def save_config(config: dict[str, Any]) -> None:
    save_json(CONFIG_PATH, config)


def ensure_schema() -> None:
    if not SCHEMA_PATH.exists():
        write_text(SCHEMA_PATH, DEFAULT_SCHEMA)


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=True) + "\n")


def append_log(title: str, lines: list[str]) -> None:
    log_path = LOGS_DIR / "log.md"
    existing = read_text(log_path, "# Operation Log\n\n")
    block = [f"## [{today()}] {title}"] + [f"- {line}" for line in lines] + [""]
    write_text(log_path, existing + "\n".join(block))


def record_diagnostic(kind: str, message: str, context: dict[str, Any]) -> None:
    append_jsonl(
        DIAGNOSTICS_PATH,
        {
            "timestamp": now_iso(),
            "kind": kind,
            "message": message,
            "context": context,
        },
    )


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        return {}, text
    parts = text.split("\n")
    fm: dict[str, Any] = {}
    i = 1
    current_list_key: str | None = None
    while i < len(parts):
        line = parts[i]
        if line.strip() == "---":
            body = "\n".join(parts[i + 1 :])
            return fm, body
        if line.startswith("  - ") and current_list_key:
            fm.setdefault(current_list_key, []).append(line[4:].strip())
            i += 1
            continue
        m = re.match(r"^([A-Za-z0-9_\-]+):\s*(.*)$", line)
        if m:
            key = m.group(1).strip()
            raw = m.group(2).strip()
            current_list_key = None
            if raw == "":
                fm[key] = []
                current_list_key = key
            elif raw.startswith("[") and raw.endswith("]"):
                inner = raw[1:-1].strip()
                fm[key] = [v.strip() for v in inner.split(",") if v.strip()] if inner else []
            elif raw.lower() in {"true", "false"}:
                fm[key] = raw.lower() == "true"
            else:
                fm[key] = raw
        i += 1
    return fm, text


def dump_frontmatter(fm: dict[str, Any]) -> str:
    lines = ["---"]
    for key, value in fm.items():
        if isinstance(value, list):
            if not value:
                lines.append(f"{key}: []")
            else:
                lines.append(f"{key}:")
                for item in value:
                    lines.append(f"  - {item}")
        elif isinstance(value, bool):
            lines.append(f"{key}: {'true' if value else 'false'}")
        else:
            lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines)


def write_markdown(path: Path, fm: dict[str, Any], body: str) -> None:
    write_text(path, f"{dump_frontmatter(fm)}\n\n{body.strip()}\n")


def read_markdown(path: Path) -> tuple[dict[str, Any], str]:
    return parse_frontmatter(read_text(path, ""))


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def load_sources_state() -> dict[str, Any]:
    if not SOURCES_STATE_PATH.exists():
        base = {"sources": []}
        save_json(SOURCES_STATE_PATH, base)
        return base
    return load_json(SOURCES_STATE_PATH, {"sources": []})


def save_sources_state(state: dict[str, Any]) -> None:
    save_json(SOURCES_STATE_PATH, state)


def get_source_by_id(source_id: str) -> dict[str, Any] | None:
    state = load_sources_state()
    for src in state.get("sources", []):
        if src.get("id") == source_id:
            return src
    return None


def infer_source_type(target: str) -> str:
    if target.startswith("http://") or target.startswith("https://"):
        if "github.com" in target:
            return "github"
        return "docs"
    p = Path(target)
    if p.exists() and p.is_dir():
        return "directory"
    return "file"


def add_source(name: str, target: str, source_type: str | None, guide: bool) -> dict[str, Any]:
    state = load_sources_state()
    chosen_type = source_type or infer_source_type(target)
    source_id = f"{slugify(name)}-{hashlib.sha1((name + target).encode('utf-8')).hexdigest()[:8]}"
    src = {
        "id": source_id,
        "name": name,
        "target": target,
        "type": chosen_type,
        "createdAt": now_iso(),
        "updatedAt": now_iso(),
        "lastLoadedAt": None,
        "status": "active",
    }
    state["sources"] = [s for s in state.get("sources", []) if s.get("id") != source_id] + [src]
    save_sources_state(state)
    append_log(f"source add | {name}", [f"Registered source `{source_id}` ({chosen_type}) at `{target}`."])
    if guide:
        ensure_source_guide(source_id)
        ensure_source_session(source_id)
    return src


def source_paths_for_reload(source: dict[str, Any]) -> list[Path]:
    target = source["target"]
    source_type = source["type"]
    if source_type == "file":
        p = Path(target)
        return [p] if p.exists() else []
    if source_type == "directory":
        p = Path(target)
        if not p.exists():
            return []
        return [x for x in p.rglob("*") if x.is_file()]
    return []


def copy_to_inbox(paths: list[Path], source_id: str) -> list[Path]:
    imported: list[Path] = []
    dst_root = RAW_DIR / "inbox" / source_id
    dst_root.mkdir(parents=True, exist_ok=True)
    for p in paths:
        try:
            if p.suffix.lower() not in SUPPORTED_SOURCE_EXTS:
                record_diagnostic("parser-compatibility", "Skipped unsupported extension", {"path": str(p)})
                continue
            dst = dst_root / p.name
            shutil.copy2(p, dst)
            imported.append(dst)
        except Exception as e:
            record_diagnostic("source-reload", str(e), {"path": str(p), "sourceId": source_id})
    return imported


def reload_source(source_id: str, guide: bool) -> list[Path]:
    state = load_sources_state()
    source = get_source_by_id(source_id)
    if not source:
        raise ValueError(f"Unknown source id: {source_id}")
    imported: list[Path] = []
    if source["type"] in {"file", "directory"}:
        imported = copy_to_inbox(source_paths_for_reload(source), source_id)
    else:
        stub = RAW_DIR / "inbox" / source_id / f"{slugify(source['name'])}.md"
        stub.parent.mkdir(parents=True, exist_ok=True)
        write_text(stub, f"# Remote source placeholder\n\n- id: {source_id}\n- target: {source['target']}\n- note: remote sources require external fetch tooling.\n")
        imported = [stub]
    for src in state.get("sources", []):
        if src.get("id") == source_id:
            src["lastLoadedAt"] = now_iso()
            src["updatedAt"] = now_iso()
    save_sources_state(state)
    append_log(f"source reload | {source_id}", [f"Imported {len(imported)} file(s) into `raw/inbox/{source_id}`."])
    if guide:
        ensure_source_guide(source_id)
        ensure_source_session(source_id)
    return imported


def delete_source(source_id: str) -> bool:
    state = load_sources_state()
    before = len(state.get("sources", []))
    state["sources"] = [s for s in state.get("sources", []) if s.get("id") != source_id]
    save_sources_state(state)
    if len(state["sources"]) < before:
        append_log(f"source delete | {source_id}", ["Removed source from registry."])
        return True
    return False


def read_source_text(path: Path) -> str:
    return read_text(path, "")


def split_sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    return [s.strip() for s in SENTENCE_RE.split(text) if len(s.strip()) > 25]


def extract_claims(text: str, max_claims: int = 8) -> list[dict[str, Any]]:
    sentences = split_sentences(text)
    ranked = sorted(sentences, key=lambda s: len(s), reverse=True)[: max_claims * 2]
    claims = []
    for i, s in enumerate(ranked[:max_claims], start=1):
        polarity = "negative" if re.search(r"\b(not|never|no|cannot|can't|won't)\b", s.lower()) else "positive"
        subject_tokens = WORD_RE.findall(s)[:6]
        subject = " ".join(subject_tokens).lower()
        claims.append({"id": f"c{i:03d}", "text": s, "subject": subject, "polarity": polarity})
    return claims


def semantic_tags(text: str, config: dict[str, Any]) -> list[str]:
    lowered = text.lower()
    matches: list[str] = []
    rules = config.get("semanticTagRules", {})
    for tag, keywords in rules.items():
        for kw in keywords:
            if kw.lower() in lowered:
                matches.append(tag)
                break
    return sorted(set(matches))


def build_summary(text: str, max_sentences: int = 4) -> str:
    sents = split_sentences(text)
    return " ".join(sents[:max_sentences]) if sents else "No extractable summary."


def source_page_path_for_file(path: Path) -> Path:
    return WIKI_SOURCES_DIR / f"{slugify(path.stem)}.md"


def move_to_processed(path: Path) -> None:
    inbox_root = RAW_DIR / "inbox"
    try:
        rel_path = path.relative_to(inbox_root)
    except Exception:
        return
    dst = RAW_DIR / "processed" / rel_path
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(path), str(dst))


def collect_input_files(target: str) -> list[Path]:
    src = get_source_by_id(target)
    if src:
        source_root = RAW_DIR / "inbox" / src["id"]
        if source_root.exists():
            return [p for p in source_root.rglob("*") if p.is_file()]
        return []
    p = Path(target)
    if p.exists() and p.is_file():
        return [p]
    if p.exists() and p.is_dir():
        return [x for x in p.rglob("*") if x.is_file()]
    return []


def ensure_source_guide(source_id: str) -> Path:
    src = get_source_by_id(source_id)
    name = src["name"] if src else source_id
    path = SOURCE_GUIDES_DIR / f"{source_id}.md"
    if not path.exists():
        content = textwrap.dedent(
            f"""\
            # Source Guide: {name}

            - Source ID: `{source_id}`
            - Status: draft

            ## Reading strategy
            1. Extract key claims with provenance.
            2. Highlight contradictions against existing source pages.
            3. Propose concept/entity updates for `wiki/candidates/`.

            ## Integration checklist
            - [ ] Source summary created
            - [ ] Claims extracted
            - [ ] Contradictions checked
            - [ ] Approval bundle staged
            """
        )
        write_text(path, content)
    return path


def ensure_source_session(source_id: str) -> Path:
    path = SOURCE_SESSIONS_DIR / f"{source_id}.md"
    if not path.exists():
        content = textwrap.dedent(
            f"""\
            # Source Session: {source_id}

            - session_id: `{source_id}`
            - created_at: `{today()}`
            - status: active

            ## Steps
            - Registered source
            - Reloaded into inbox
            - Waiting for guided ingest / compile approval
            """
        )
        write_text(path, content)
    return path


def source_review(source_id: str) -> Path:
    src = get_source_by_id(source_id)
    if not src:
        raise ValueError(f"Unknown source id: {source_id}")
    brief_path = SOURCE_BRIEFS_DIR / f"{source_id}.md"
    ingest_events = [row for row in load_jsonl(LOGS_DIR / "ingest-history.jsonl") if row.get("sourceId") == source_id]
    body = [
        f"# Source Brief: {src['name']}",
        "",
        f"- id: `{source_id}`",
        f"- type: `{src['type']}`",
        f"- target: `{src['target']}`",
        f"- last_loaded: `{src.get('lastLoadedAt')}`",
        "",
        "## Ingest history",
    ]
    if ingest_events:
        for ev in ingest_events[-20:]:
            body.append(f"- {ev.get('timestamp')} | {ev.get('event')} | files={ev.get('fileCount', 0)}")
    else:
        body.append("- No ingest events yet.")
    write_text(brief_path, "\n".join(body) + "\n")
    append_log(f"source review | {source_id}", [f"Wrote source brief `{rel(brief_path)}`."])
    return brief_path


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def ensure_page(
    page_path: Path,
    page_type: str,
    title: str,
    source_refs: list[str],
    tags: list[str],
    confidence: str,
    body: str,
) -> None:
    fm = {
        "id": f"{page_type}-{slugify(title)}",
        "type": page_type,
        "status": "active",
        "updated_at": today(),
        "source_refs": sorted(set(source_refs)),
        "tags": sorted(set(tags)),
        "confidence": confidence,
    }
    write_markdown(page_path, fm, body)


def ingest(target: str, guide: bool, provider_override: str | None = None) -> dict[str, Any]:
    config = load_config()
    source_files = collect_input_files(target)
    if not source_files:
        raise ValueError(f"No input files found for: {target}")

    processed = 0
    skipped = 0
    created_pages: list[Path] = []
    source_id = target if get_source_by_id(target) else None
    for i, fp in enumerate(source_files, start=1):
        if fp.suffix.lower() not in SUPPORTED_SOURCE_EXTS:
            skipped += 1
            record_diagnostic("parser-compatibility", "Unsupported extension during ingest", {"path": str(fp)})
            continue
        text = read_source_text(fp)
        if not text.strip():
            skipped += 1
            record_diagnostic("ingest", "Empty source content", {"path": str(fp)})
            continue

        summary = build_summary(text)
        claims = extract_claims(text)
        tags = semantic_tags(summary + "\n" + text[:2000], config)
        page_path = source_page_path_for_file(fp)
        claims_lines = "\n".join([f"- [claim:{c['id']}] {c['text']}" for c in claims]) or "- None"
        related = "\n".join([f"- [[{slugify(fp.stem)}]]"]) if claims else "- None"
        body = textwrap.dedent(
            f"""\
            # {fp.stem}

            ## Summary
            {summary}

            ## Claims
            {claims_lines}

            ## Provenance
            - source_file: `{fp}`
            - ingested_at: `{now_iso()}`
            - provider: `{provider_override or config.get('model', {}).get('provider', 'heuristic')}`

            ## Related pages
            {related}
            """
        )
        ensure_page(
            page_path=page_path,
            page_type="source",
            title=fp.stem,
            source_refs=[f"source://{rel(fp)}"],
            tags=tags + ["ingest", "claim"],
            confidence="high",
            body=body,
        )

        brief_path = SOURCE_BRIEFS_DIR / f"{slugify(fp.stem)}-brief.md"
        write_text(
            brief_path,
            textwrap.dedent(
                f"""\
                # Source Brief: {fp.stem}

                - source_page: [[sources/{slugify(fp.stem)}]]
                - imported_from: `{fp}`
                - claims: {len(claims)}
                - tags: {", ".join(tags) if tags else "none"}

                ## Summary
                {summary}
                """
            ),
        )

        append_jsonl(
            LOGS_DIR / "ingest-history.jsonl",
            {
                "timestamp": now_iso(),
                "event": "ingest",
                "sourceId": source_id,
                "sourceFile": str(fp),
                "sourcePage": rel(page_path),
                "fileCount": 1,
                "claims": len(claims),
                "tags": tags,
            },
        )
        created_pages.append(page_path)
        processed += 1
        if i % 25 == 0:
            print(f"[progress] ingested {i}/{len(source_files)} files")
        move_to_processed(fp)

    rebuild_index()
    build_dashboards(config)
    append_log(
        f"ingest | {target}",
        [
            f"Processed files: {processed}",
            f"Skipped files: {skipped}",
            f"Created/updated source pages: {len(created_pages)}",
            "Moved ingested inputs from raw/inbox to raw/processed when applicable.",
        ],
    )
    if guide and source_id:
        ensure_source_guide(source_id)
        ensure_source_session(source_id)
    return {"processed": processed, "skipped": skipped, "pages": [rel(p) for p in created_pages]}


def list_markdown_pages() -> list[Path]:
    return [p for p in WIKI_DIR.rglob("*.md") if p.is_file()]


def page_title_from_path(path: Path) -> str:
    return path.stem.replace("-", " ").strip().title()


def rebuild_index() -> None:
    sections: dict[str, list[Path]] = {
        "Dashboards": sorted(WIKI_DASHBOARDS_DIR.glob("*.md")),
        "Topics": sorted(WIKI_TOPICS_DIR.glob("*.md")),
        "Concepts": sorted(WIKI_CONCEPTS_DIR.glob("*.md")),
        "Entities": sorted(WIKI_ENTITIES_DIR.glob("*.md")),
        "Candidates": sorted(WIKI_CANDIDATES_DIR.glob("*.md")),
        "Insights": sorted(WIKI_INSIGHTS_DIR.glob("*.md")),
        "Sources": sorted(WIKI_SOURCES_DIR.glob("*.md")),
        "Outputs": sorted([p for p in WIKI_OUTPUTS_DIR.glob("*.md") if p.is_file()]),
    }
    lines = ["# Knowledge Index", ""]
    for sec, files in sections.items():
        lines.append(f"## {sec}")
        if files:
            for f in files:
                rel_target = rel(f)
                lines.append(f"- [[{rel_target[:-3]}]]")
        else:
            lines.append("- (empty)")
        lines.append("")
    write_text(ROOT / "index.md", "\n".join(lines).rstrip() + "\n")


def parse_claims_from_source_pages() -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    for p in sorted(WIKI_SOURCES_DIR.glob("*.md")):
        fm, body = read_markdown(p)
        for line in body.splitlines():
            m = CLAIM_RE.search(line.strip())
            if not m:
                continue
            claim_id = m.group(1).strip()
            text = m.group(2).strip()
            polarity = "negative" if re.search(r"\b(not|never|no|cannot|can't|won't)\b", text.lower()) else "positive"
            subject = " ".join(WORD_RE.findall(text.lower())[:6])
            claims.append(
                {
                    "claim_id": claim_id,
                    "text": text,
                    "subject": subject,
                    "polarity": polarity,
                    "source_page": rel(p),
                    "source_refs": fm.get("source_refs", []),
                }
            )
    return claims


def extract_entities_from_claim(text: str) -> list[str]:
    ents = []
    for token in re.findall(r"\b[A-Z][a-zA-Z0-9\-]{2,}\b", text):
        if token.lower() in STOPWORDS:
            continue
        ents.append(token)
    return sorted(set(ents))[:8]


def extract_concepts_from_claim(text: str, config: dict[str, Any]) -> list[str]:
    tags = semantic_tags(text, config)
    words = [w.lower() for w in WORD_RE.findall(text) if len(w) > 5 and w.lower() not in STOPWORDS]
    top_words = [w for w, _ in Counter(words).most_common(4)]
    return sorted(set(tags + top_words))[:8]


def compose_candidate_page(
    item_name: str,
    item_type: str,
    evidence: list[dict[str, Any]],
    config: dict[str, Any],
) -> str:
    all_text = "\n".join(e["text"] for e in evidence)
    tags = semantic_tags(all_text, config)
    source_refs = sorted({e["source_page"] for e in evidence})
    confidence = "high" if len(evidence) >= 4 else "medium" if len(evidence) >= 2 else "low"
    fm = {
        "id": f"{item_type}-{slugify(item_name)}",
        "type": item_type,
        "status": "draft",
        "updated_at": today(),
        "source_refs": source_refs,
        "tags": tags,
        "confidence": confidence,
    }
    evidence_lines = []
    for ev in evidence[:20]:
        evidence_lines.append(f"- [{ev['claim_id']}] {ev['text']} (from [[{ev['source_page'][:-3]}]])")
    body = textwrap.dedent(
        f"""\
        # {item_name}

        ## Candidate summary
        Auto-compiled candidate from source claims. Review before promotion.

        ## Evidence
        {chr(10).join(evidence_lines) if evidence_lines else "- None"}

        ## Notes
        - This page is generated in `wiki/candidates/`.
        - Promotion to canonical pages should happen through approval bundles.
        """
    )
    return f"{dump_frontmatter(fm)}\n\n{body.strip()}\n"


def compile_candidates(approve: bool, source_id: str | None) -> dict[str, Any]:
    config = load_config()
    claims = parse_claims_from_source_pages()
    if source_id:
        claims = [c for c in claims if source_id in c.get("source_page", "") or source_id in " ".join(c.get("source_refs", []))]
    entity_map: dict[str, dict[str, Any]] = {}
    concept_map: dict[str, dict[str, Any]] = {}
    for c in claims:
        for ent in extract_entities_from_claim(c["text"]):
            key = slugify(ent)
            bucket = entity_map.setdefault(key, {"name": ent, "evidence": []})
            bucket["evidence"].append(c)
        for concept in extract_concepts_from_claim(c["text"], config):
            key = slugify(concept)
            bucket = concept_map.setdefault(key, {"name": concept, "evidence": []})
            bucket["evidence"].append(c)

    proposed_files: list[Path] = []
    for key, payload in entity_map.items():
        name = payload["name"]
        evidence = payload["evidence"]
        path = WIKI_CANDIDATES_DIR / f"entity-{key}.md"
        write_text(path, compose_candidate_page(name, "entity", evidence, config))
        proposed_files.append(path)
    for key, payload in concept_map.items():
        name = payload["name"]
        evidence = payload["evidence"]
        path = WIKI_CANDIDATES_DIR / f"concept-{key}.md"
        write_text(path, compose_candidate_page(name, "concept", evidence, config))
        proposed_files.append(path)
    proposed_files = sorted(set(proposed_files))

    existing_candidates = [p for p in WIKI_CANDIDATES_DIR.glob("*.md") if p.name.startswith("concept-") or p.name.startswith("entity-")]
    keep = {p.resolve() for p in proposed_files}
    pruned = 0
    for old in existing_candidates:
        if old.resolve() not in keep:
            old.unlink(missing_ok=True)
            pruned += 1

    bundle_id = None
    if approve:
        bundle_id = stage_approval_bundle(proposed_files, config)
        append_log(
            f"compile --approve | {bundle_id}",
            [
                f"Staged {len(proposed_files)} proposed pages into approval bundle.",
                f"Pruned stale candidate pages: {pruned}",
                "New concepts/entities landed in wiki/candidates first.",
                "No canonical pages were mutated silently.",
            ],
        )
    else:
        append_log(
            "compile",
            [
                f"Compiled {len(proposed_files)} candidate page(s) into wiki/candidates.",
                f"Pruned stale candidate pages: {pruned}",
                "Run `apex-wiki.py compile --approve` to stage an approval bundle.",
            ],
        )
    rebuild_index()
    return {"bundleId": bundle_id, "proposedCount": len(proposed_files)}


def stage_approval_bundle(files: list[Path], config: dict[str, Any]) -> str:
    ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    bundle_id = f"bundle-{ts}-{hashlib.sha1(now_iso().encode('utf-8')).hexdigest()[:6]}"
    bundle_dir = APPROVAL_BUNDLES_DIR / bundle_id
    (bundle_dir / "proposed").mkdir(parents=True, exist_ok=True)
    manifest = {
        "bundleId": bundle_id,
        "createdAt": now_iso(),
        "guidedSessionMode": config.get("profile", {}).get("guidedSessionMode", "canonical"),
        "status": "pending_approval",
        "files": [],
    }
    for f in files:
        dst = bundle_dir / "proposed" / f.name
        shutil.copy2(f, dst)
        manifest["files"].append({"candidatePath": rel(f), "bundlePath": rel(dst)})
    save_json(bundle_dir / "manifest.json", manifest)
    return bundle_id


def list_bundles() -> list[dict[str, Any]]:
    bundles = []
    for m in sorted(APPROVAL_BUNDLES_DIR.glob("*/manifest.json")):
        data = load_json(m, {})
        if data:
            bundles.append(data)
    return bundles


def apply_bundle(bundle_id: str, target: str | None = None) -> dict[str, Any]:
    manifest_path = APPROVAL_BUNDLES_DIR / bundle_id / "manifest.json"
    if not manifest_path.exists():
        raise ValueError(f"Bundle not found: {bundle_id}")
    manifest = load_json(manifest_path, {})
    config = load_config()
    mode = target or config.get("profile", {}).get("guidedSessionMode", "canonical")
    promoted = 0
    for item in manifest.get("files", []):
        cand = ROOT / item["candidatePath"].replace("/", os.sep)
        if not cand.exists():
            continue
        fm, body = read_markdown(cand)
        page_type = fm.get("type", "concept")
        if mode == "insights":
            dst = WIKI_INSIGHTS_DIR / cand.name
        else:
            if page_type == "entity":
                dst = WIKI_ENTITIES_DIR / cand.name
            elif page_type == "concept":
                dst = WIKI_CONCEPTS_DIR / cand.name
            else:
                dst = WIKI_TOPICS_DIR / cand.name
        write_markdown(dst, {**fm, "status": "active", "updated_at": today()}, body)
        promoted += 1
    manifest["status"] = "approved"
    manifest["approvedAt"] = now_iso()
    manifest["appliedTarget"] = mode
    save_json(manifest_path, manifest)
    append_log(f"bundle apply | {bundle_id}", [f"Promoted {promoted} page(s) using mode `{mode}`."])
    rebuild_index()
    return {"promoted": promoted, "mode": mode}


def collect_pages_for_graph() -> dict[str, dict[str, Any]]:
    pages: dict[str, dict[str, Any]] = {}
    for p in list_markdown_pages():
        fm, body = read_markdown(p)
        page_id = rel(p)
        links = LINK_RE.findall(body)
        pages[page_id] = {
            "path": p,
            "frontmatter": fm,
            "body": body,
            "links": links,
            "title": p.stem,
        }
    return pages


def link_target_candidates(pages: dict[str, dict[str, Any]]) -> dict[str, str]:
    lookup = {}
    for pid, payload in pages.items():
        stem = payload["path"].stem.lower()
        lookup[stem] = pid
        lookup[payload["title"].lower()] = pid
        lookup[pid[:-3].lower()] = pid
    return lookup


def freshness_days(updated_at: str | None) -> int:
    if not updated_at:
        return 9999
    try:
        d = dt.datetime.strptime(updated_at[:10], "%Y-%m-%d").date()
        return max(0, (dt.date.today() - d).days)
    except Exception:
        return 9999


def build_graph_data(include_linked: bool = False) -> dict[str, Any]:
    pages = collect_pages_for_graph()
    lookup = link_target_candidates(pages)

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    for pid, payload in pages.items():
        fm = payload["frontmatter"]
        node = {
            "id": pid,
            "label": payload["title"],
            "type": fm.get("type", "note"),
            "confidence": fm.get("confidence", "medium"),
            "freshness_days": freshness_days(fm.get("updated_at")),
            "tags": fm.get("tags", []),
            "community": None,
        }
        nodes.append(node)

        line_claim = None
        source_refs = fm.get("source_refs", [])
        for line_no, line in enumerate(payload["body"].splitlines(), start=1):
            claim_m = CLAIM_RE.search(line)
            if claim_m:
                line_claim = claim_m.group(1)
            for link in LINK_RE.findall(line):
                key = slugify(link).lower()
                target = lookup.get(key) or lookup.get(link.lower()) or lookup.get(link.replace("/", "").lower())
                provenance = {
                    "source_page": pid,
                    "source_refs": source_refs,
                    "claim_id": line_claim or f"line-{line_no}",
                    "claim_text": line.strip()[:400],
                }
                if target:
                    edges.append(
                        {
                            "source": pid,
                            "target": target,
                            "kind": "extracted",
                            "provenance": provenance,
                        }
                    )
                else:
                    edges.append(
                        {
                            "source": pid,
                            "target": link,
                            "kind": "ambiguous",
                            "provenance": provenance,
                        }
                    )

    tag_to_nodes: dict[str, list[str]] = defaultdict(list)
    for n in nodes:
        for t in n.get("tags", []):
            tag_to_nodes[t].append(n["id"])
    for tag, node_ids in tag_to_nodes.items():
        if len(node_ids) < 2:
            continue
        subset = node_ids[:12]
        for i in range(len(subset) - 1):
            s = subset[i]
            t = subset[i + 1]
            edges.append(
                {
                    "source": s,
                    "target": t,
                    "kind": "inferred",
                    "provenance": {
                        "source_page": s,
                        "source_refs": pages[s]["frontmatter"].get("source_refs", []),
                        "claim_id": f"inferred-{tag}",
                        "claim_text": f"inferred by shared semantic tag `{tag}`",
                    },
                }
            )

    undirected: dict[str, set[str]] = defaultdict(set)
    for e in edges:
        if e["target"] in pages:
            undirected[e["source"]].add(e["target"])
            undirected[e["target"]].add(e["source"])

    communities: list[list[str]] = []
    seen: set[str] = set()
    for n in pages.keys():
        if n in seen:
            continue
        comp: list[str] = []
        q = deque([n])
        seen.add(n)
        while q:
            cur = q.popleft()
            comp.append(cur)
            for nei in undirected.get(cur, set()):
                if nei not in seen:
                    seen.add(nei)
                    q.append(nei)
        communities.append(comp)

    node_to_community: dict[str, str] = {}
    for i, comp in enumerate(sorted(communities, key=len, reverse=True), start=1):
        cid = f"community-{i}"
        for n in comp:
            node_to_community[n] = cid

    degree: Counter[str] = Counter()
    for e in edges:
        if e["target"] in pages:
            degree[e["source"]] += 1
            degree[e["target"]] += 1
    for n in nodes:
        n["community"] = node_to_community.get(n["id"], "community-unknown")
        n["degree"] = degree.get(n["id"], 0)

    bridge_scores: dict[str, int] = {}
    for n in pages.keys():
        neigh = undirected.get(n, set())
        comms = {node_to_community.get(x) for x in neigh}
        bridge_scores[n] = len([c for c in comms if c])

    god_nodes = [n for n in sorted(nodes, key=lambda x: x.get("degree", 0), reverse=True)[:10]]
    bridge_nodes = [n for n in sorted(nodes, key=lambda x: bridge_scores.get(x["id"], 0), reverse=True)[:10]]
    contradictions = detect_contradictions(parse_claims_from_source_pages())

    graph_data = {
        "generatedAt": now_iso(),
        "nodes": nodes,
        "edges": edges,
        "metrics": {
            "nodeCount": len(nodes),
            "edgeCount": len(edges),
            "communities": len(communities),
            "orphanNodes": len([n for n in nodes if n.get("degree", 0) == 0]),
            "godNodes": [n["id"] for n in god_nodes],
            "bridgeNodes": [n["id"] for n in bridge_nodes],
        },
        "communities": communities,
        "bridgeScores": bridge_scores,
        "contradictions": contradictions,
    }

    if include_linked:
        cfg = load_config()
        linked = [Path(p).resolve() for p in cfg.get("linkedVaults", [])]
        local_index_id = "index.md"
        for linked_path in linked:
            graph_path = linked_path / "exports" / "graph" / "knowledge-graph.json"
            if not graph_path.exists():
                continue
            linked_graph = load_json(graph_path, {})
            linked_nodes = linked_graph.get("nodes", [])
            linked_edges = linked_graph.get("edges", [])
            prefix = f"linked::{slugify(linked_path.name)}::"
            for n in linked_nodes:
                graph_data["nodes"].append(
                    {
                        **n,
                        "id": f"{prefix}{n.get('id')}",
                        "vault": str(linked_path),
                        "community": n.get("community", "linked-community"),
                    }
                )
            for e in linked_edges:
                graph_data["edges"].append(
                    {
                        **e,
                        "source": f"{prefix}{e.get('source')}",
                        "target": f"{prefix}{e.get('target')}",
                    }
                )
            linked_index = f"{prefix}index.md"
            if any(n.get("id") == linked_index for n in graph_data["nodes"]) and any(n.get("id") == local_index_id for n in graph_data["nodes"]):
                graph_data["edges"].append(
                    {
                        "source": local_index_id,
                        "target": linked_index,
                        "kind": "inferred",
                        "provenance": {
                            "source_page": local_index_id,
                            "source_refs": [],
                            "claim_id": "linked-vault",
                            "claim_text": f"linked vault bridge to {linked_path}",
                        },
                    }
                )

    node_ids = {n["id"] for n in graph_data["nodes"]}
    degree_all: Counter[str] = Counter()
    for e in graph_data["edges"]:
        if e.get("source") in node_ids and e.get("target") in node_ids:
            degree_all[e["source"]] += 1
            degree_all[e["target"]] += 1
    for n in graph_data["nodes"]:
        n["degree"] = degree_all.get(n["id"], n.get("degree", 0))
    graph_data["metrics"] = {
        **graph_data.get("metrics", {}),
        "nodeCount": len(graph_data["nodes"]),
        "edgeCount": len(graph_data["edges"]),
        "orphanNodes": len([n for n in graph_data["nodes"] if degree_all.get(n["id"], 0) == 0]),
        "includeLinked": include_linked,
    }
    return graph_data


def detect_contradictions(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_subject: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for c in claims:
        subj = c.get("subject", "").strip()
        if subj:
            by_subject[subj].append(c)

    conflicts: list[dict[str, Any]] = []
    for subject, items in by_subject.items():
        pos = [x for x in items if x.get("polarity") == "positive"]
        neg = [x for x in items if x.get("polarity") == "negative"]
        if pos and neg:
            conflicts.append(
                {
                    "subject": subject,
                    "positive": pos[:3],
                    "negative": neg[:3],
                    "kind": "polarity",
                }
            )
        numbers = defaultdict(list)
        for it in items:
            nums = re.findall(r"\b\d+(?:\.\d+)?\b", it["text"])
            for n in nums:
                numbers[n].append(it)
        if len(numbers.keys()) >= 2:
            vals = sorted(numbers.keys())
            conflicts.append(
                {
                    "subject": subject,
                    "kind": "numeric",
                    "values": vals[:5],
                    "examples": [v[0] for v in numbers.values() if v],
                }
            )
    return conflicts


def export_graph_json(graph: dict[str, Any]) -> Path:
    path = EXPORT_GRAPH_DIR / "knowledge-graph.json"
    save_json(path, graph)
    save_json(EXPORT_GRAPH_DIR / "graph-metrics.json", graph.get("metrics", {}))
    return path


def export_graphml(graph: dict[str, Any]) -> Path:
    path = EXPORT_GRAPH_DIR / "knowledge-graph.graphml"
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<graphml xmlns="http://graphml.graphdrawing.org/xmlns">',
        '  <graph id="G" edgedefault="undirected">',
    ]
    for n in graph["nodes"]:
        lines.append(f'    <node id="{n["id"]}"><data key="label">{n["label"]}</data></node>')
    for i, e in enumerate(graph["edges"], start=1):
        if e["target"] in {n["id"] for n in graph["nodes"]}:
            lines.append(f'    <edge id="e{i}" source="{e["source"]}" target="{e["target"]}"/>')
    lines += ["  </graph>", "</graphml>"]
    write_text(path, "\n".join(lines) + "\n")
    return path


def export_gexf(graph: dict[str, Any]) -> Path:
    path = EXPORT_GRAPH_DIR / "knowledge-graph.gexf"
    node_ids = {n["id"] for n in graph["nodes"]}
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<gexf xmlns="http://www.gexf.net/1.3" version="1.3">',
        '  <graph mode="static" defaultedgetype="undirected">',
        "    <nodes>",
    ]
    for n in graph["nodes"]:
        lines.append(f'      <node id="{n["id"]}" label="{n["label"]}"/>')
    lines += ["    </nodes>", "    <edges>"]
    edge_index = 0
    for e in graph["edges"]:
        if e["target"] not in node_ids:
            continue
        edge_index += 1
        lines.append(f'      <edge id="{edge_index}" source="{e["source"]}" target="{e["target"]}" label="{e["kind"]}"/>')
    lines += ["    </edges>", "  </graph>", "</gexf>"]
    write_text(path, "\n".join(lines) + "\n")
    return path


def export_cypher(graph: dict[str, Any], vault_id: str) -> Path:
    path = EXPORT_GRAPH_DIR / "knowledge-graph.cypher"
    safe_vault = slugify(vault_id)
    lines = [f"// vaultId: {safe_vault}", "BEGIN"]
    for n in graph["nodes"]:
        nid = n["id"].replace("'", "\\'")
        label = slugify(n.get("type", "note")).capitalize()
        node_label = str(n.get("label", "")).replace("'", "\\'")
        community = str(n.get("community", "")).replace("'", "\\'")
        confidence = str(n.get("confidence", "medium")).replace("'", "\\'")
        lines.append(
            f"MERGE (n:{label} {{vaultId:'{safe_vault}', nodeId:'{nid}'}}) "
            f"SET n.label='{node_label}', n.community='{community}', "
            f"n.confidence='{confidence}', n.freshnessDays={int(n.get('freshness_days', 0))};"
        )
    node_ids = {n["id"] for n in graph["nodes"]}
    for e in graph["edges"]:
        if e["target"] not in node_ids:
            continue
        s = e["source"].replace("'", "\\'")
        t = e["target"].replace("'", "\\'")
        kind = e.get("kind", "related").upper()
        lines.append(
            f"MATCH (a {{vaultId:'{safe_vault}', nodeId:'{s}'}}), (b {{vaultId:'{safe_vault}', nodeId:'{t}'}}) "
            f"MERGE (a)-[r:{kind} {{vaultId:'{safe_vault}'}}]->(b);"
        )
    lines.append("COMMIT")
    write_text(path, "\n".join(lines) + "\n")
    return path


def export_svg(graph: dict[str, Any]) -> Path:
    path = EXPORT_GRAPH_DIR / "knowledge-graph.svg"
    nodes = graph["nodes"][:60]
    width = 1400
    height = 1000
    center_x = width / 2
    center_y = height / 2
    radius = min(width, height) * 0.38
    positions: dict[str, tuple[float, float]] = {}
    for i, n in enumerate(nodes):
        angle = 2 * math.pi * (i / max(1, len(nodes)))
        positions[n["id"]] = (center_x + radius * math.cos(angle), center_y + radius * math.sin(angle))
    node_ids = {n["id"] for n in nodes}
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">',
        '<rect width="100%" height="100%" fill="#0f172a"/>',
    ]
    for e in graph["edges"]:
        if e["source"] in node_ids and e["target"] in node_ids:
            x1, y1 = positions[e["source"]]
            x2, y2 = positions[e["target"]]
            color = "#64748b" if e.get("kind") == "extracted" else "#f59e0b" if e.get("kind") == "inferred" else "#ef4444"
            lines.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{color}" stroke-opacity="0.45"/>')
    for n in nodes:
        x, y = positions[n["id"]]
        lines.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="8" fill="#38bdf8"/>')
        label = n["label"][:28]
        lines.append(f'<text x="{x + 10:.1f}" y="{y - 10:.1f}" fill="#e2e8f0" font-size="12">{label}</text>')
    lines.append("</svg>")
    write_text(path, "\n".join(lines) + "\n")
    return path


def export_html(graph: dict[str, Any]) -> Path:
    path = EXPORT_GRAPH_DIR / "knowledge-graph.html"
    god_nodes = graph.get("metrics", {}).get("godNodes", [])
    contradictions = graph.get("contradictions", [])
    content = textwrap.dedent(
        f"""\
        <!doctype html>
        <html>
        <head>
          <meta charset="utf-8"/>
          <title>Knowledge Graph Report</title>
          <style>
            body {{ font-family: Arial, sans-serif; margin: 2rem; background: #0b1020; color: #e5e7eb; }}
            h1, h2 {{ color: #93c5fd; }}
            code {{ color: #fca5a5; }}
          </style>
        </head>
        <body>
          <h1>Knowledge Graph Report</h1>
          <p>Generated at: {graph.get('generatedAt')}</p>
          <h2>Metrics</h2>
          <pre>{json.dumps(graph.get("metrics", {}), indent=2)}</pre>
          <h2>God nodes</h2>
          <ul>
            {"".join([f"<li><code>{g}</code></li>" for g in god_nodes])}
          </ul>
          <h2>Contradictions</h2>
          <pre>{json.dumps(contradictions[:30], indent=2)}</pre>
        </body>
        </html>
        """
    )
    write_text(path, content)
    return path


def push_neo4j(graph: dict[str, Any], bolt_url: str, user: str, password: str, vault_id: str) -> str:
    try:
        from neo4j import GraphDatabase  # type: ignore
    except Exception:
        raise RuntimeError("Neo4j push requires `neo4j` package. Install with `pip install neo4j`.")
    driver = GraphDatabase.driver(bolt_url, auth=(user, password))
    safe_vault = slugify(vault_id)
    with driver.session() as session:
        for n in graph["nodes"]:
            session.run(
                "MERGE (x:VaultNode {vaultId:$vaultId, nodeId:$nodeId}) "
                "SET x.label=$label, x.type=$type, x.community=$community, x.confidence=$confidence, x.freshnessDays=$freshnessDays",
                vaultId=safe_vault,
                nodeId=n["id"],
                label=n["label"],
                type=n.get("type", "note"),
                community=n.get("community"),
                confidence=n.get("confidence"),
                freshnessDays=int(n.get("freshness_days", 0)),
            )
        node_ids = {n["id"] for n in graph["nodes"]}
        for e in graph["edges"]:
            if e["target"] not in node_ids:
                continue
            rel_type = slugify(e.get("kind", "related")).upper()
            session.run(
                f"MATCH (a:VaultNode {{vaultId:$vaultId, nodeId:$source}}), (b:VaultNode {{vaultId:$vaultId, nodeId:$target}}) "
                f"MERGE (a)-[r:{rel_type} {{vaultId:$vaultId}}]->(b)",
                vaultId=safe_vault,
                source=e["source"],
                target=e["target"],
            )
    driver.close()
    return "ok"


def generate_graph_report(graph: dict[str, Any]) -> Path:
    tiny_threshold = 2
    comm_sizes = sorted([len(c) for c in graph.get("communities", [])], reverse=True)
    tiny_count = len([x for x in comm_sizes if x <= tiny_threshold])
    major = [x for x in comm_sizes if x > tiny_threshold]

    bridge_nodes = graph.get("metrics", {}).get("bridgeNodes", [])[:8]
    god_nodes = graph.get("metrics", {}).get("godNodes", [])[:8]
    contradictions = graph.get("contradictions", [])[:20]

    surprises = []
    for b in bridge_nodes[:5]:
        surprises.append(f"- `[[{b[:-3]}]]` bridges multiple communities and may connect previously separate themes.")

    lines = [
        "# Research Map",
        "",
        "## God nodes",
        *([f"- [[{g[:-3]}]]" for g in god_nodes] or ["- None"]),
        "",
        "## Bridge nodes",
        *([f"- [[{b[:-3]}]]" for b in bridge_nodes] or ["- None"]),
        "",
        "## Surprising connections",
        *(surprises or ["- No bridge surprises detected yet."]),
        "",
        "## Community rollup",
        f"- Major communities: {major if major else [0]}",
        f"- Tiny fragmented communities rolled up: {tiny_count}",
        "",
        "## Contradictions",
    ]
    if contradictions:
        for c in contradictions:
            lines.append(f"- Subject `{c.get('subject', 'unknown')}` has conflict type `{c.get('kind')}`.")
    else:
        lines.append("- No contradictions detected.")
    report_path = WIKI_DASHBOARDS_DIR / "Research Map.md"
    write_text(report_path, "\n".join(lines) + "\n")
    return report_path


def build_graph_exports(
    export_html_flag: bool,
    export_svg_flag: bool,
    export_graphml_flag: bool,
    export_cypher_flag: bool,
    include_linked: bool,
    vault_id: str,
    neo4j_url: str | None,
    neo4j_user: str | None,
    neo4j_password: str | None,
) -> dict[str, Any]:
    graph = build_graph_data(include_linked=include_linked)
    outputs = {"json": str(export_graph_json(graph)), "gexf": str(export_gexf(graph))}
    if export_graphml_flag:
        outputs["graphml"] = str(export_graphml(graph))
    if export_cypher_flag:
        outputs["cypher"] = str(export_cypher(graph, vault_id))
    if export_svg_flag:
        outputs["svg"] = str(export_svg(graph))
    if export_html_flag:
        outputs["html"] = str(export_html(graph))
    report_path = generate_graph_report(graph)
    outputs["report"] = str(report_path)
    if neo4j_url and neo4j_user and neo4j_password:
        outputs["neo4j"] = push_neo4j(graph, neo4j_url, neo4j_user, neo4j_password, vault_id)
    append_log(
        "graph build",
        [
            f"Nodes: {graph['metrics']['nodeCount']}",
            f"Edges: {graph['metrics']['edgeCount']}",
            f"Communities: {graph['metrics'].get('communities', 0)}",
            f"Orphans: {graph['metrics']['orphanNodes']}",
            f"Include linked: {include_linked}",
        ],
    )
    return outputs


def lint(conflicts_only: bool) -> dict[str, Any]:
    graph = build_graph_data()
    pages = collect_pages_for_graph()
    node_ids = {n["id"] for n in graph["nodes"]}
    inbound = Counter()
    outbound = Counter()
    for e in graph["edges"]:
        if e["target"] in node_ids:
            outbound[e["source"]] += 1
            inbound[e["target"]] += 1
    orphans = [nid for nid in node_ids if inbound[nid] == 0 and outbound[nid] == 0]

    stale = []
    for n in graph["nodes"]:
        if n["freshness_days"] > 45:
            stale.append(n)
    contradictions = graph.get("contradictions", [])

    taxonomy = read_text(SYSTEM_DIR / "taxonomy.yml", "")
    allowed_tags = set(re.findall(r"-\s+([a-zA-Z0-9\-]+)", taxonomy))
    drift = []
    for pid, p in pages.items():
        tags = p["frontmatter"].get("tags", [])
        for t in tags:
            if t not in allowed_tags:
                drift.append({"page": pid, "tag": t})

    focused_lines = ["# Contradiction Audit", ""]
    if contradictions:
        for c in contradictions:
            focused_lines.append(f"- Subject `{c.get('subject', 'unknown')}` has `{c.get('kind')}` conflict.")
    else:
        focused_lines.append("- No contradictions detected.")
    write_text(WIKI_DASHBOARDS_DIR / "Contradictions.md", "\n".join(focused_lines) + "\n")

    if not conflicts_only:
        lines = [
            "# Graph Health",
            "",
            f"- Nodes: {graph['metrics']['nodeCount']}",
            f"- Edges: {graph['metrics']['edgeCount']}",
            f"- Orphan pages: {len(orphans)}",
            f"- Stale nodes (>45 days): {len(stale)}",
            f"- Contradictions: {len(contradictions)}",
            f"- Taxonomy drift items: {len(drift)}",
            "",
            "## Orphans",
            *([f"- [[{o[:-3]}]]" for o in orphans] or ["- None"]),
            "",
            "## Stale hubs",
            *([f"- [[{s['id'][:-3]}]] freshness={s['freshness_days']} degree={s['degree']}" for s in sorted(stale, key=lambda x: x.get("degree", 0), reverse=True)[:20]] or ["- None"]),
            "",
            "## Contradiction summary",
            *([f"- `{c.get('subject')}` ({c.get('kind')})" for c in contradictions[:20]] or ["- None"]),
            "",
            "## Taxonomy drift",
            *([f"- [[{d['page'][:-3]}]] tag={d['tag']}" for d in drift[:20]] or ["- None"]),
        ]
        write_text(WIKI_DASHBOARDS_DIR / "Graph Health.md", "\n".join(lines) + "\n")
        append_log(
            "lint",
            [
                f"orphans={len(orphans)}",
                f"stale={len(stale)}",
                f"contradictions={len(contradictions)}",
                f"taxonomy_drift={len(drift)}",
            ],
        )
    else:
        append_log("lint --conflicts", [f"contradictions={len(contradictions)}"])

    return {"orphans": len(orphans), "stale": len(stale), "contradictions": len(contradictions), "taxonomyDrift": len(drift)}


def token_set(text: str) -> set[str]:
    return set(w.lower() for w in WORD_RE.findall(text) if len(w) > 2)


def render_query_output(fmt: str, question: str, summary_lines: list[str], citations: list[str], slug: str) -> tuple[str, list[Path]]:
    assets: list[Path] = []
    summary = "\n".join(summary_lines) if summary_lines else "- No relevant pages found."
    cits = "\n".join([f"- [[{c[:-3]}]]" for c in citations]) if citations else "- None"
    if fmt == "report":
        body = textwrap.dedent(
            f"""\
            # Report: {question}

            ## Executive summary
            {summary}

            ## Evidence
            {cits}

            ## Recommended next actions
            - Run `apex-wiki.py compile --approve` if new concepts emerged.
            - Run `apex-wiki.py lint --conflicts` for contradiction-focused review.
            """
        )
        return body.strip() + "\n", assets
    if fmt == "slides":
        body = textwrap.dedent(
            f"""\
            ---
            marp: true
            theme: default
            ---

            # {question}

            ---

            ## Key points
            {summary}

            ---

            ## Citations
            {cits}
            """
        )
        return body.strip() + "\n", assets
    if fmt == "chart":
        csv_path = OUTPUT_ASSETS_DIR / f"{slug}-chart.csv"
        write_text(csv_path, "metric,value\ncitations,{0}\nsummary_lines,{1}\n".format(len(citations), len(summary_lines)))
        assets.append(csv_path)
        body = textwrap.dedent(
            f"""\
            # Chart: {question}

            ```mermaid
            xychart-beta
              title "Query result metrics"
              x-axis ["citations","summary_lines"]
              y-axis "count" 0 --> 20
              bar [{len(citations)}, {len(summary_lines)}]
            ```

            Data: `[[{rel(csv_path)[:-3]}]]`

            ## Notes
            {summary}
            """
        )
        return body.strip() + "\n", assets
    if fmt == "image":
        svg_path = OUTPUT_ASSETS_DIR / f"{slug}-answer.svg"
        svg = textwrap.dedent(
            f"""\
            <svg xmlns="http://www.w3.org/2000/svg" width="1200" height="800">
              <rect width="100%" height="100%" fill="#111827"/>
              <text x="40" y="70" font-size="34" fill="#bfdbfe">Answer Snapshot</text>
              <text x="40" y="130" font-size="20" fill="#e5e7eb">{question[:120]}</text>
              <text x="40" y="190" font-size="16" fill="#cbd5e1">Citations: {len(citations)}</text>
            </svg>
            """
        )
        write_text(svg_path, svg)
        assets.append(svg_path)
        body = textwrap.dedent(
            f"""\
            # Image Output: {question}

            ![[{rel(svg_path)}]]

            ## Notes
            {summary}

            ## Citations
            {cits}
            """
        )
        return body.strip() + "\n", assets
    body = textwrap.dedent(
        f"""\
        # {question}

        ## Answer
        {summary}

        ## Citations
        {cits}
        """
    )
    return body.strip() + "\n", assets


def heuristic_answer(question: str, pages: list[tuple[Path, dict[str, Any], str]]) -> tuple[list[str], list[str]]:
    q = token_set(question)
    scored = []
    for p, fm, body in pages:
        tokens = token_set(body + " " + " ".join(fm.get("tags", [])))
        score = len(q & tokens)
        if score:
            scored.append((score, p, body))
    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:6]
    summary_lines = []
    citations = []
    for score, p, body in top:
        sent = split_sentences(body)
        line = sent[0] if sent else body.strip().splitlines()[0] if body.strip() else "No summary line."
        summary_lines.append(f"- ({score}) {line[:220]}")
        citations.append(rel(p))
    return summary_lines, citations


def call_model(config: dict[str, Any], question: str, context: str) -> str:
    provider = config.get("model", {}).get("provider", "heuristic")
    model = config.get("model", {}).get("model", "heuristic-v1")
    if provider == "heuristic":
        return ""
    if provider == "custom":
        cmd = config.get("providers", {}).get("custom", {}).get("command", "").strip()
        if not cmd:
            raise RuntimeError("custom provider enabled but command is missing")
        raise RuntimeError("Custom adapter command execution is not implemented in this minimal build.")

    if provider == "anthropic":
        pconf = config.get("providers", {}).get("anthropic", {})
        key = os.getenv(pconf.get("apiKeyEnv", "ANTHROPIC_API_KEY"), "")
        if not key:
            raise RuntimeError("Anthropic API key not set")
        payload = {
            "model": model,
            "max_tokens": 1200,
            "messages": [{"role": "user", "content": f"Question: {question}\n\nContext:\n{context}"}],
        }
        req = urllib.request.Request(
            pconf.get("baseUrl", "https://api.anthropic.com/v1/messages"),
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                parts = body.get("content", [])
                texts = [p.get("text", "") for p in parts if isinstance(p, dict)]
                return "\n".join(texts).strip()
        except urllib.error.URLError as e:
            raise RuntimeError(f"Anthropic call failed: {e}")

    pconf = config.get("providers", {}).get(provider, {})
    base_url = pconf.get("baseUrl", "")
    if not base_url:
        raise RuntimeError(f"Provider `{provider}` missing baseUrl")
    key_env = pconf.get("apiKeyEnv", "")
    key = os.getenv(key_env, "") if key_env else ""
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": f"Question: {question}\n\nContext:\n{context}"}],
        "temperature": 0.2,
    }
    headers = {"content-type": "application/json"}
    if key:
        headers["authorization"] = f"Bearer {key}"
    req = urllib.request.Request(base_url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            choices = body.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "").strip()
            return ""
    except urllib.error.URLError as e:
        raise RuntimeError(f"{provider} call failed: {e}")


def query(question: str, fmt: str, save: bool) -> dict[str, Any]:
    config = load_config()
    pages = []
    for p in list_markdown_pages():
        fm, body = read_markdown(p)
        pages.append((p, fm, body))
    summary_lines, citations = heuristic_answer(question, pages)
    context = "\n".join([f"{c}: {line}" for c, line in zip(citations, summary_lines)])
    model_answer = ""
    if config.get("model", {}).get("provider", "heuristic") != "heuristic":
        try:
            model_answer = call_model(config, question, context)
        except Exception as e:
            record_diagnostic("model-provider", str(e), {"provider": config.get("model", {}).get("provider")})
    if model_answer:
        summary_lines = [f"- {line}" for line in split_sentences(model_answer)[:8]] or summary_lines
    slug = slugify(question)[:80]
    body, assets = render_query_output(fmt, question, summary_lines, citations, slug)
    output_path = WIKI_OUTPUTS_DIR / f"{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}-{slug}.md"
    if save:
        fm = {
            "id": f"output-{slug}",
            "type": "output",
            "status": "active",
            "updated_at": today(),
            "source_refs": citations,
            "tags": semantic_tags(question + "\n" + "\n".join(summary_lines), config) + ["query"],
            "confidence": "medium" if citations else "low",
        }
        write_markdown(output_path, fm, body)
        rebuild_index()
        append_log(
            f"query | {question[:80]}",
            [f"Saved output to `{rel(output_path)}` format={fmt}", f"Citations={len(citations)}"],
        )
    return {"saved": save, "outputPath": rel(output_path) if save else None, "citations": len(citations), "assets": [rel(a) for a in assets], "body": body}


def dataview_block(query: str) -> str:
    return f"\n```dataview\n{query}\n```\n"


def build_dashboards(config: dict[str, Any] | None = None) -> list[Path]:
    config = config or load_config()
    dataview_enabled = bool(config.get("profile", {}).get("dataviewBlocks", False))
    state = load_sources_state()
    ingests = load_jsonl(LOGS_DIR / "ingest-history.jsonl")
    graph_metrics = load_json(EXPORT_GRAPH_DIR / "graph-metrics.json", {})
    contradictions = detect_contradictions(parse_claims_from_source_pages())

    paths: list[Path] = []
    recent_sources = WIKI_DASHBOARDS_DIR / "Recent Sources.md"
    lines = ["# Recent Sources", ""]
    for src in sorted(state.get("sources", []), key=lambda s: s.get("updatedAt", ""), reverse=True)[:30]:
        lines.append(f"- `{src['id']}` | {src['type']} | last_loaded={src.get('lastLoadedAt')}")
    if dataview_enabled:
        lines.append(dataview_block("TABLE type, updated_at FROM \"wiki/sources\" SORT updated_at DESC LIMIT 20"))
    write_text(recent_sources, "\n".join(lines) + "\n")
    paths.append(recent_sources)

    reading_log = WIKI_DASHBOARDS_DIR / "Reading Log.md"
    lines = ["# Reading Log", ""]
    for ev in ingests[-100:]:
        lines.append(f"- {ev.get('timestamp')} | {ev.get('sourceFile')} -> [[{ev.get('sourcePage','')[:-3]}]]")
    write_text(reading_log, "\n".join(lines) + "\n")
    paths.append(reading_log)

    timeline = WIKI_DASHBOARDS_DIR / "Timeline.md"
    lines = ["# Timeline", ""]
    for line in read_text(LOGS_DIR / "log.md").splitlines()[-240:]:
        if line.startswith("## ["):
            lines.append(f"- {line[3:]}")
    write_text(timeline, "\n".join(lines) + "\n")
    paths.append(timeline)

    sessions = WIKI_DASHBOARDS_DIR / "Source Sessions.md"
    lines = ["# Source Sessions", ""]
    for p in sorted(SOURCE_SESSIONS_DIR.glob("*.md")):
        lines.append(f"- [[{rel(p)[:-3]}]]")
    write_text(sessions, "\n".join(lines) + "\n")
    paths.append(sessions)

    guides = WIKI_DASHBOARDS_DIR / "Source Guides.md"
    lines = ["# Source Guides", ""]
    for p in sorted(SOURCE_GUIDES_DIR.glob("*.md")):
        lines.append(f"- [[{rel(p)[:-3]}]]")
    write_text(guides, "\n".join(lines) + "\n")
    paths.append(guides)

    contradictions_page = WIKI_DASHBOARDS_DIR / "Contradictions.md"
    lines = ["# Contradictions", ""]
    if contradictions:
        for c in contradictions[:40]:
            lines.append(f"- Subject `{c.get('subject', 'unknown')}` has conflict type `{c.get('kind')}`.")
    else:
        lines.append("- None detected.")
    write_text(contradictions_page, "\n".join(lines) + "\n")
    paths.append(contradictions_page)

    open_questions = WIKI_DASHBOARDS_DIR / "Open Questions.md"
    lines = [
        "# Open Questions",
        "",
        "- Which orphan pages should be linked into core themes?",
        "- Which high-degree hubs have stale updates?",
        "- Which contradictions require manual adjudication?",
        "",
        "## Metrics snapshot",
        f"- nodeCount: {graph_metrics.get('nodeCount', 0)}",
        f"- edgeCount: {graph_metrics.get('edgeCount', 0)}",
        f"- orphanNodes: {graph_metrics.get('orphanNodes', 0)}",
    ]
    if dataview_enabled:
        lines.append(dataview_block("LIST FROM \"wiki\" WHERE status = \"draft\""))
    write_text(open_questions, "\n".join(lines) + "\n")
    paths.append(open_questions)

    rebuild_index()
    return paths


def initialize_vault_root(vault_root: Path, project_name: str) -> dict[str, Any]:
    vault_root.mkdir(parents=True, exist_ok=True)
    for p in [
        vault_root / "raw" / "inbox",
        vault_root / "raw" / "processed",
        vault_root / "raw" / "assets",
        vault_root / "wiki" / "entities",
        vault_root / "wiki" / "concepts",
        vault_root / "wiki" / "topics",
        vault_root / "wiki" / "sources",
        vault_root / "wiki" / "outputs" / "source-briefs",
        vault_root / "wiki" / "outputs" / "source-sessions",
        vault_root / "wiki" / "outputs" / "source-guides",
        vault_root / "wiki" / "outputs" / "assets",
        vault_root / "wiki" / "dashboards",
        vault_root / "wiki" / "candidates",
        vault_root / "wiki" / "insights",
        vault_root / "system" / "agent-integrations",
        vault_root / "system" / "templates",
        vault_root / "state" / "approval-bundles",
        vault_root / "logs",
        vault_root / "exports" / "graph",
        vault_root / "scripts",
    ]:
        p.mkdir(parents=True, exist_ok=True)

    config = merge_dict(
        DEFAULT_CONFIG,
        {
            "vaultId": slugify(project_name),
            "linkedVaults": [],
            "graph": {"includeLinkedDefault": False},
        },
    )
    save_json(vault_root / "apex-wiki.config.json", config)
    write_text(vault_root / "apex-wiki.schema.md", DEFAULT_SCHEMA)
    write_text(vault_root / "index.md", "# Knowledge Index\n\n## Dashboards\n- (empty)\n")
    write_text(vault_root / "logs" / "log.md", f"# Operation Log\n\n## [{today()}] bootstrap | Initialized vault\n- Project: {project_name}\n")
    save_json(vault_root / "state" / "sources.json", {"sources": []})
    write_text(vault_root / "README.md", f"# APEX-wiki Vault: {project_name}\n\nOpen this folder directly as an Obsidian vault.\n")
    write_text(vault_root / ".gitignore", "__pycache__/\n*.pyc\nraw/inbox/\nraw/processed/\nexports/graph/*.svg\nexports/graph/*.html\n")

    # Copy runtime script and helpers so each vault is independently runnable.
    shutil.copy2(ROOT / "scripts" / "apex-wiki.py", vault_root / "scripts" / "apex-wiki.py")
    for helper in ["run_pipeline.ps1", "publish-github.ps1", "publish-github-token.ps1"]:
        src = ROOT / "scripts" / helper
        if src.exists():
            shutil.copy2(src, vault_root / "scripts" / helper)
    if (SYSTEM_DIR / "taxonomy.yml").exists():
        shutil.copy2(SYSTEM_DIR / "taxonomy.yml", vault_root / "system" / "taxonomy.yml")
    for template in (SYSTEM_DIR / "templates").glob("*.md"):
        shutil.copy2(template, vault_root / "system" / "templates" / template.name)
    return config


def create_project_vault(project_name: str, base_dir: str | None = None) -> Path:
    base = Path(base_dir) if base_dir else (ROOT.parent / "APEX-vaults")
    vault_root = (base / slugify(project_name)).resolve()
    if vault_root.exists():
        raise ValueError(f"Vault already exists: {vault_root}")
    initialize_vault_root(vault_root, project_name)
    return vault_root


def vault_links() -> list[dict[str, Any]]:
    config = load_config()
    links = []
    for raw in config.get("linkedVaults", []):
        p = Path(raw).resolve()
        links.append({"path": str(p), "exists": p.exists(), "graph": str(p / "exports" / "graph" / "knowledge-graph.json")})
    return links


def vault_link(path_str: str) -> dict[str, Any]:
    target = Path(path_str).resolve()
    cfg = load_config()
    links = [str(Path(p).resolve()) for p in cfg.get("linkedVaults", [])]
    if str(target) not in links:
        links.append(str(target))
    cfg["linkedVaults"] = sorted(set(links))
    save_config(cfg)
    return {"linkedVaults": cfg["linkedVaults"]}


def vault_unlink(path_str: str) -> dict[str, Any]:
    target = str(Path(path_str).resolve())
    cfg = load_config()
    links = [str(Path(p).resolve()) for p in cfg.get("linkedVaults", [])]
    cfg["linkedVaults"] = [p for p in links if p != target]
    save_config(cfg)
    return {"linkedVaults": cfg["linkedVaults"]}


AGENTS = [
    "codex",
    "claude-code",
    "cursor",
    "goose",
    "pi",
    "gemini-cli",
    "opencode",
    "aider",
    "github-copilot-cli",
]


def install_agent_rules(graph_first: bool, only_agents: list[str] | None = None) -> list[Path]:
    selected = set(only_agents) if only_agents else set(AGENTS)
    out: list[Path] = []
    for agent in AGENTS:
        if agent not in selected:
            continue
        path = SYSTEM_DIR / "agent-integrations" / f"{agent}.md"
        content = [
            f"# {agent} integration rules",
            "",
            "1. Read `system/AGENTS.md` and `apex-wiki.schema.md` before editing.",
            "2. Use `index.md` and `wiki/dashboards/` to route retrieval.",
            "3. Save useful answers into `wiki/outputs/` (save-first behavior).",
            "4. New concepts/entities compile into `wiki/candidates/`.",
            "5. Canonical promotion should happen via approval bundles.",
        ]
        if graph_first:
            content.append("6. Graph-first mode: inspect `exports/graph/knowledge-graph.json` before broad search.")
        write_text(path, "\n".join(content) + "\n")
        out.append(path)
    append_log("agent integrations", [f"Installed rule files for {len(out)} agent(s). graph_first={graph_first}"])
    return out


def ensure_mcp_notes() -> None:
    claude_desktop = SYSTEM_DIR / "agent-integrations" / "claude-desktop-mcp.jsonc"
    copilot_cli = SYSTEM_DIR / "agent-integrations" / "copilot-cli-mcp.jsonc"
    mcp_list = SYSTEM_DIR / "agent-integrations" / "mcp-servers.jsonc"
    payload = {
        "mcpServers": {
            "APEX-wiki": {
                "command": "python",
                "args": ["scripts/apex-wiki.py", "mcp"],
                "cwd": str(ROOT.resolve()),
            }
        }
    }
    content = json.dumps(payload, indent=2, ensure_ascii=True) + "\n"
    write_text(claude_desktop, content)
    write_text(copilot_cli, content)
    write_text(mcp_list, content)


TOOLS = [
    {
        "name": "vault_summary",
        "description": "Get metrics and summary statistics for the current vault (nodes, edges, communities, orphan count).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "source_add",
        "description": "Register a new source in the APEX-wiki sources registry.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "The user-friendly name of the source."},
                "target": {"type": "string", "description": "Target file path, directory path, or URL."},
                "source_type": {"type": "string", "enum": ["file", "directory", "github", "docs"], "description": "Type of the source (optional)."},
                "guide": {"type": "boolean", "description": "Whether to automatically create reading guides and sessions.", "default": False},
            },
            "required": ["name", "target"],
        },
    },
    {
        "name": "source_list",
        "description": "List all registered sources in the vault registry.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "source_reload",
        "description": "Reload and import files from a registered source into the raw inbox.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source_id": {"type": "string", "description": "The unique ID of the registered source."},
                "guide": {"type": "boolean", "description": "Whether to ensure reading guides and sessions exist.", "default": False},
            },
            "required": ["source_id"],
        },
    },
    {
        "name": "source_review",
        "description": "Generate a brief summary report (brief) for a source.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source_id": {"type": "string", "description": "The source ID to review."}
            },
            "required": ["source_id"],
        },
    },
    {
        "name": "source_delete",
        "description": "Delete a registered source from the registry.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source_id": {"type": "string", "description": "The source ID to delete."}
            },
            "required": ["source_id"],
        },
    },
    {
        "name": "ingest",
        "description": "Ingest files in the source inbox or a specific directory/file path into the wiki. Extracts claims and tags.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Registered source ID, file path, or directory path to ingest."},
                "guide": {"type": "boolean", "description": "Whether to ensure guide and session exist.", "default": False},
                "provider": {"type": "string", "description": "Optional model provider override."},
            },
            "required": ["target"],
        },
    },
    {
        "name": "compile_candidates",
        "description": "Compile ingested source claims into candidate concepts and entities in wiki/candidates/.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "approve": {"type": "boolean", "description": "If true, automatically stages the candidates into an approval bundle.", "default": False},
                "source_id": {"type": "string", "description": "Filter by source ID (optional)."},
            },
        },
    },
    {
        "name": "bundle_list",
        "description": "List staged approval bundles.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "bundle_apply",
        "description": "Promote candidates in an approval bundle to active pages in the vault.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "bundle_id": {"type": "string", "description": "The unique ID of the bundle."},
                "target": {"type": "string", "enum": ["canonical", "insights"], "description": "Compilation target mode (optional)."},
            },
            "required": ["bundle_id"],
        },
    },
    {
        "name": "lint_vault",
        "description": "Lint the vault for orphans, stale hubs, contradictions, and taxonomy drift.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "conflicts_only": {"type": "boolean", "description": "Only return contradiction info if true.", "default": False}
            },
        },
    },
    {
        "name": "graph_build",
        "description": "Rebuild, analyze, and export the knowledge graph (JSON, GEXF, GraphML, Cypher, SVG, HTML).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "include_linked": {"type": "boolean", "description": "Include linked vaults in graph construction.", "default": False}
            },
        },
    },
    {
        "name": "query_vault",
        "description": "Query the vault using semantic/heuristic search and generate outputs in selected formats.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "The natural language question to ask."},
                "format": {"type": "string", "enum": ["markdown", "report", "slides", "chart", "image"], "description": "Output format style.", "default": "markdown"},
                "no_save": {"type": "boolean", "description": "Do not save the query output to WIKI_OUTPUTS_DIR.", "default": False},
            },
            "required": ["question"],
        },
    },
    {
        "name": "dashboards_build",
        "description": "Rebuild and update all wiki dashboards.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "vault_create",
        "description": "Create a new isolated APEX-wiki vault.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "The name of the new project vault."},
                "base_dir": {"type": "string", "description": "Base directory for the new vault (optional)."},
            },
            "required": ["name"],
        },
    },
    {
        "name": "vault_link",
        "description": "Link another vault for multi-vault graph compilation.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute path to the sibling vault."}
            },
            "required": ["path"],
        },
    },
    {
        "name": "vault_unlink",
        "description": "Unlink a linked vault.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute path to the linked vault."}
            },
            "required": ["path"],
        },
    },
    {
        "name": "vault_links",
        "description": "List all linked vaults.",
        "inputSchema": {"type": "object", "properties": {}},
    }
]


def run_tool_safe(func, *args, **kwargs) -> Any:
    old_stdout = sys.stdout
    sys.stdout = sys.stderr
    try:
        return func(*args, **kwargs)
    finally:
        sys.stdout = old_stdout


def execute_mcp_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name == "vault_summary":
        graph = run_tool_safe(build_graph_data)
        metrics = graph.get("metrics", {})
        return {"content": [{"type": "text", "text": json.dumps(metrics, indent=2)}]}
    elif name == "source_add":
        n = arguments.get("name")
        target = arguments.get("target")
        source_type = arguments.get("source_type")
        guide = arguments.get("guide", False)
        if not n or not target:
            raise ValueError("Arguments 'name' and 'target' are required.")
        res = run_tool_safe(add_source, n, target, source_type, guide)
        return {"content": [{"type": "text", "text": json.dumps(res, indent=2)}]}
    elif name == "source_list":
        sources = run_tool_safe(load_sources_state).get("sources", [])
        return {"content": [{"type": "text", "text": json.dumps(sources, indent=2)}]}
    elif name == "source_reload":
        source_id = arguments.get("source_id")
        guide = arguments.get("guide", False)
        if not source_id:
            raise ValueError("Argument 'source_id' is required.")
        imported = run_tool_safe(reload_source, source_id, guide)
        return {"content": [{"type": "text", "text": f"Successfully reloaded source '{source_id}'. Imported {len(imported)} files."}]}
    elif name == "source_review":
        source_id = arguments.get("source_id")
        if not source_id:
            raise ValueError("Argument 'source_id' is required.")
        brief_path = run_tool_safe(source_review, source_id)
        return {"content": [{"type": "text", "text": f"Wrote source brief to {rel(brief_path)}"}]}
    elif name == "source_delete":
        source_id = arguments.get("source_id")
        if not source_id:
            raise ValueError("Argument 'source_id' is required.")
        ok = run_tool_safe(delete_source, source_id)
        return {"content": [{"type": "text", "text": f"Deleted source '{source_id}': {ok}"}]}
    elif name == "ingest":
        target = arguments.get("target")
        guide = arguments.get("guide", False)
        provider = arguments.get("provider")
        if not target:
            raise ValueError("Argument 'target' is required.")
        res = run_tool_safe(ingest, target, guide, provider)
        return {"content": [{"type": "text", "text": json.dumps(res, indent=2)}]}
    elif name == "compile_candidates":
        approve = arguments.get("approve", False)
        source_id = arguments.get("source_id")
        res = run_tool_safe(compile_candidates, approve, source_id)
        return {"content": [{"type": "text", "text": json.dumps(res, indent=2)}]}
    elif name == "bundle_list":
        bundles = run_tool_safe(list_bundles)
        return {"content": [{"type": "text", "text": json.dumps(bundles, indent=2)}]}
    elif name == "bundle_apply":
        bundle_id = arguments.get("bundle_id")
        target = arguments.get("target")
        if not bundle_id:
            raise ValueError("Argument 'bundle_id' is required.")
        res = run_tool_safe(apply_bundle, bundle_id, target)
        return {"content": [{"type": "text", "text": json.dumps(res, indent=2)}]}
    elif name == "lint_vault":
        conflicts_only = arguments.get("conflicts_only", False)
        res = run_tool_safe(lint, conflicts_only)
        return {"content": [{"type": "text", "text": json.dumps(res, indent=2)}]}
    elif name == "graph_build":
        include_linked = arguments.get("include_linked", False)
        cfg = run_tool_safe(load_config)
        vault_id = cfg.get("vaultId", "llm-wiki")
        out = run_tool_safe(
            build_graph_exports,
            True, True, True, True,
            include_linked,
            vault_id,
            None, None, None
        )
        return {"content": [{"type": "text", "text": json.dumps(out, indent=2)}]}
    elif name == "query_vault":
        question = arguments.get("question")
        fmt = arguments.get("format", "markdown")
        no_save = arguments.get("no_save", False)
        if not question:
            raise ValueError("Argument 'question' is required.")
        res = run_tool_safe(query, question, fmt, not no_save)
        return {"content": [{"type": "text", "text": json.dumps(res, indent=2)}]}
    elif name == "dashboards_build":
        cfg = run_tool_safe(load_config)
        paths = run_tool_safe(build_dashboards, cfg)
        return {"content": [{"type": "text", "text": "Successfully updated dashboards:\n" + "\n".join(f"- {rel(p)}" for p in paths)}]}
    elif name == "vault_create":
        n = arguments.get("name")
        base_dir = arguments.get("base_dir")
        if not n:
            raise ValueError("Argument 'name' is required.")
        path = run_tool_safe(create_project_vault, n, base_dir)
        return {"content": [{"type": "text", "text": f"Created new vault at '{path}'"}]}
    elif name == "vault_link":
        path = arguments.get("path")
        if not path:
            raise ValueError("Argument 'path' is required.")
        res = run_tool_safe(vault_link, path)
        return {"content": [{"type": "text", "text": json.dumps(res, indent=2)}]}
    elif name == "vault_unlink":
        path = arguments.get("path")
        if not path:
            raise ValueError("Argument 'path' is required.")
        res = run_tool_safe(vault_unlink, path)
        return {"content": [{"type": "text", "text": json.dumps(res, indent=2)}]}
    elif name == "vault_links":
        res = run_tool_safe(vault_links)
        return {"content": [{"type": "text", "text": json.dumps(res, indent=2)}]}
    else:
        raise ValueError(f"Unknown tool name: {name}")


def handle_resources_list() -> dict[str, Any]:
    resources = []
    index_path = ROOT / "index.md"
    if index_path.exists():
        resources.append({
            "uri": "apex-wiki://index.md",
            "name": "index.md",
            "mimeType": "text/markdown",
            "description": "APEX-wiki main index page"
        })
    for p in sorted(WIKI_DIR.rglob("*.md")):
        if p.is_file():
            rel_path = rel(p)
            resources.append({
                "uri": f"apex-wiki://{rel_path}",
                "name": p.name,
                "mimeType": "text/markdown",
                "description": f"APEX-wiki page: {p.stem} ({p.parent.name})"
            })
    return {"resources": resources}


def handle_resources_read(uri: str) -> dict[str, Any]:
    if not uri.startswith("apex-wiki://"):
        raise ValueError(f"Invalid URI scheme: {uri}")
    rel_path_str = uri[len("apex-wiki://"):]
    if ".." in rel_path_str or rel_path_str.startswith("/") or rel_path_str.startswith("\\"):
        raise ValueError(f"Invalid resource path: {rel_path_str}")
    target_path = (ROOT / rel_path_str).resolve()
    if not str(target_path).startswith(str(ROOT.resolve())):
        raise ValueError(f"Access denied to resource: {rel_path_str}")
    if not target_path.exists():
        raise FileNotFoundError(f"Resource not found: {rel_path_str}")
    text = target_path.read_text(encoding="utf-8", errors="ignore")
    return {
        "contents": [
            {
                "uri": uri,
                "mimeType": "text/markdown",
                "text": text
            }
        ]
    }


def make_error(id_val: Any, code: int, message: str, data: Any = None) -> str:
    err = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return json.dumps({
        "jsonrpc": "2.0",
        "id": id_val,
        "error": err
    }, ensure_ascii=True)


def make_result(id_val: Any, result: Any) -> str:
    return json.dumps({
        "jsonrpc": "2.0",
        "id": id_val,
        "result": result
    }, ensure_ascii=True)


def run_mcp_stdio() -> None:
    ensure_dirs()
    ensure_schema()
    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break
            line = line.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
            except Exception as e:
                sys.stdout.write(make_error(None, -32700, f"Parse error: {e}") + "\n")
                sys.stdout.flush()
                continue

            if not isinstance(req, dict) or "method" not in req:
                sys.stdout.write(make_error(req.get("id") if isinstance(req, dict) else None, -32600, "Invalid Request") + "\n")
                sys.stdout.flush()
                continue

            req_id = req.get("id")
            method = req.get("method")
            params = req.get("params", {})
            is_notification = (req_id is None)

            if method == "initialize":
                resp_result = {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {},
                        "resources": {}
                    },
                    "serverInfo": {
                        "name": "apex-wiki-mcp",
                        "version": "1.1.0"
                    }
                }
                sys.stdout.write(make_result(req_id, resp_result) + "\n")
                sys.stdout.flush()
            elif method == "notifications/initialized":
                pass
            elif method == "tools/list":
                sys.stdout.write(make_result(req_id, {"tools": TOOLS}) + "\n")
                sys.stdout.flush()
            elif method == "tools/call":
                tool_name = params.get("name")
                arguments = params.get("arguments", {})
                try:
                    result = execute_mcp_tool(tool_name, arguments)
                    sys.stdout.write(make_result(req_id, result) + "\n")
                except Exception as e:
                    err_result = {
                        "content": [
                            {
                                "type": "text",
                                "text": f"Error executing tool '{tool_name}': {e}"
                            }
                        ],
                        "isError": True
                    }
                    sys.stdout.write(make_result(req_id, err_result) + "\n")
                sys.stdout.flush()
            elif method == "resources/list":
                try:
                    res = handle_resources_list()
                    sys.stdout.write(make_result(req_id, res) + "\n")
                except Exception as e:
                    sys.stdout.write(make_error(req_id, -32603, f"Internal error listing resources: {e}") + "\n")
                sys.stdout.flush()
            elif method == "resources/read":
                uri = params.get("uri")
                try:
                    res = handle_resources_read(uri)
                    sys.stdout.write(make_result(req_id, res) + "\n")
                except Exception as e:
                    sys.stdout.write(make_error(req_id, -32603, f"Internal error reading resource: {e}") + "\n")
                sys.stdout.flush()
            else:
                if not is_notification:
                    sys.stdout.write(make_error(req_id, -32601, f"Method not found: {method}") + "\n")
                    sys.stdout.flush()
        except Exception as e:
            sys.stderr.write(f"Fatal error in stdin loop: {e}\n")
            sys.stderr.flush()


def inbox_import(path: str) -> list[Path]:
    src = Path(path)
    if not src.exists():
        raise ValueError(f"Import path does not exist: {path}")
    imported: list[Path] = []
    if src.is_file():
        dst = RAW_DIR / "inbox" / src.name
        shutil.copy2(src, dst)
        imported.append(dst)
    else:
        dst_root = RAW_DIR / "inbox" / f"import-{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}"
        for f in src.rglob("*"):
            if f.is_file():
                dst = dst_root / f.name
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dst)
                imported.append(dst)
    append_log("automation inbox-import", [f"Imported {len(imported)} file(s) from `{path}` to raw/inbox."])
    return imported


def install_git_hooks() -> Path:
    hook_body = textwrap.dedent(
        """\
        #!/usr/bin/env sh
        python scripts/apex-wiki.py lint --conflicts || exit 1
        python scripts/apex-wiki.py graph || exit 1
        """
    )
    git_hooks = ROOT / ".git" / "hooks"
    if git_hooks.exists():
        hook = git_hooks / "pre-commit"
        write_text(hook, hook_body)
        try:
            os.chmod(hook, 0o755)
        except Exception:
            pass
        append_log("automation git-hooks", [f"Installed pre-commit hook at `{rel(hook)}`."])
        return hook
    fallback = SYSTEM_DIR / "agent-integrations" / "pre-commit.sample"
    write_text(fallback, hook_body)
    append_log("automation git-hooks", ["No .git directory found; wrote hook sample under system/agent-integrations."])
    return fallback


def save_schedule(interval_minutes: int) -> Path:
    path = STATE_DIR / "automation-schedule.json"
    save_json(
        path,
        {
            "intervalMinutes": interval_minutes,
            "tasks": ["inbox-import", "ingest", "compile --approve", "lint", "graph", "dashboards"],
            "updatedAt": now_iso(),
        },
    )
    append_log("automation schedule", [f"Saved recurring schedule config with interval={interval_minutes} minutes."])
    return path


def watch_loop(interval: int, once: bool) -> None:
    processed_state_path = STATE_DIR / "watch-state.json"
    state = load_json(processed_state_path, {"seen": []})
    seen = set(state.get("seen", []))
    while True:
        files = [p for p in (RAW_DIR / "inbox").rglob("*") if p.is_file()]
        new_files = [p for p in files if str(p) not in seen]
        if new_files:
            print(f"[watch] found {len(new_files)} new file(s)")
            for fp in new_files[:100]:
                try:
                    ingest(str(fp), guide=False)
                    seen.add(str(fp))
                except Exception as e:
                    record_diagnostic("watch-ingest", str(e), {"path": str(fp)})
        state["seen"] = sorted(seen)
        save_json(processed_state_path, state)
        if once:
            break
        time.sleep(max(5, interval))


def write_readme() -> None:
    content = textwrap.dedent(
        """\
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
        - `python scripts/apex-wiki.py graph --include-linked` (optional linked-vault graph merge)
        - `python scripts/apex-wiki.py query "question" --format markdown`
        - `python scripts/apex-wiki.py dashboards`
        - `python scripts/apex-wiki.py mcp`
        - `python scripts/apex-wiki.py vault create "project-name"` (creates isolated vault under sibling `APEX-vaults/`)
        - `python scripts/apex-wiki.py vault link "E:\\path\\to\\another-vault"` (optional graph-level bridge)
        - `python scripts/apex-wiki.py vault links`

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
        """
    )
    write_text(ROOT / "README.md", content)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="APEX-wiki CLI for persistent wiki + graph workflows.")
    sub = parser.add_subparsers(dest="command", required=True)

    src = sub.add_parser("source", help="Manage sources registry and guided source workflows.")
    src_sub = src.add_subparsers(dest="source_cmd", required=True)
    src_add = src_sub.add_parser("add")
    src_add.add_argument("name")
    src_add.add_argument("target")
    src_add.add_argument("--type", dest="source_type", default=None, choices=["file", "directory", "github", "docs"])
    src_add.add_argument("--guide", action="store_true")

    src_list = src_sub.add_parser("list")
    src_list.add_argument("--json", action="store_true")

    src_reload = src_sub.add_parser("reload")
    src_reload.add_argument("source_id")
    src_reload.add_argument("--guide", action="store_true")

    src_review = src_sub.add_parser("review")
    src_review.add_argument("source_id")

    src_guide = src_sub.add_parser("guide")
    src_guide.add_argument("source_id")

    src_session = src_sub.add_parser("session")
    src_session.add_argument("source_id")

    src_delete = src_sub.add_parser("delete")
    src_delete.add_argument("source_id")

    ingest_cmd = sub.add_parser("ingest", help="Ingest source id or file path into wiki/sources.")
    ingest_cmd.add_argument("target")
    ingest_cmd.add_argument("--guide", action="store_true")
    ingest_cmd.add_argument("--provider", default=None)

    compile_cmd = sub.add_parser("compile", help="Compile source claims into candidate pages.")
    compile_cmd.add_argument("--approve", action="store_true")
    compile_cmd.add_argument("--source", dest="source_id", default=None)

    bundle_cmd = sub.add_parser("bundle", help="Inspect/apply approval bundles.")
    bundle_sub = bundle_cmd.add_subparsers(dest="bundle_cmd", required=True)
    bundle_sub.add_parser("list")
    bundle_apply_cmd = bundle_sub.add_parser("apply")
    bundle_apply_cmd.add_argument("bundle_id")
    bundle_apply_cmd.add_argument("--target", choices=["canonical", "insights"], default=None)

    lint_cmd = sub.add_parser("lint")
    lint_cmd.add_argument("--conflicts", action="store_true")

    graph_cmd = sub.add_parser("graph")
    graph_cmd.add_argument("--html", action="store_true")
    graph_cmd.add_argument("--svg", action="store_true")
    graph_cmd.add_argument("--graphml", action="store_true")
    graph_cmd.add_argument("--cypher", action="store_true")
    graph_cmd.add_argument("--neo4j-url", default=None)
    graph_cmd.add_argument("--neo4j-user", default=None)
    graph_cmd.add_argument("--neo4j-password", default=None)
    graph_cmd.add_argument("--vault-id", default=None)
    graph_cmd.add_argument("--include-linked", action="store_true")

    query_cmd = sub.add_parser("query")
    query_cmd.add_argument("question")
    query_cmd.add_argument("--format", choices=["markdown", "report", "slides", "chart", "image"], default="markdown")
    query_cmd.add_argument("--no-save", action="store_true")

    sub.add_parser("dashboards")

    vault_cmd = sub.add_parser("vault", help="Create/link/list project vaults.")
    vault_sub = vault_cmd.add_subparsers(dest="vault_cmd", required=True)
    vault_create = vault_sub.add_parser("create")
    vault_create.add_argument("name")
    vault_create.add_argument("--base-dir", default=None)
    vault_link_cmd = vault_sub.add_parser("link")
    vault_link_cmd.add_argument("path")
    vault_unlink_cmd = vault_sub.add_parser("unlink")
    vault_unlink_cmd.add_argument("path")
    vault_sub.add_parser("links")

    agent_cmd = sub.add_parser("install-agent-rules")
    agent_cmd.add_argument("--graph-first", action="store_true")
    agent_cmd.add_argument("--agents", default="all", help="Comma-separated list or 'all'.")

    mcp_cmd = sub.add_parser("mcp")
    mcp_cmd.add_argument("--stdio", action="store_true", default=True)

    watch_cmd = sub.add_parser("watch")
    watch_cmd.add_argument("--interval", type=int, default=60)
    watch_cmd.add_argument("--once", action="store_true")

    automation_cmd = sub.add_parser("automation")
    auto_sub = automation_cmd.add_subparsers(dest="automation_cmd", required=True)
    auto_import = auto_sub.add_parser("inbox-import")
    auto_import.add_argument("path")
    auto_sub.add_parser("install-hooks")
    auto_schedule = auto_sub.add_parser("schedule")
    auto_schedule.add_argument("--interval-minutes", type=int, default=60)

    sub.add_parser("providers")
    sub.add_parser("bootstrap")
    return parser.parse_args()


def print_json(payload: Any) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=True))


def main() -> int:
    ensure_dirs()
    ensure_schema()
    config = load_config()
    write_readme()
    ensure_mcp_notes()

    args = parse_args()
    try:
        if args.command == "bootstrap":
            rebuild_index()
            build_dashboards(config)
            install_agent_rules(False, None)
            print_json({"ok": True, "message": "bootstrap complete"})
            return 0

        if args.command == "vault":
            if args.vault_cmd == "create":
                path = create_project_vault(args.name, args.base_dir)
                print_json({"vault": str(path), "obsidianOpenPath": str(path)})
                return 0
            if args.vault_cmd == "link":
                out = vault_link(args.path)
                print_json(out)
                return 0
            if args.vault_cmd == "unlink":
                out = vault_unlink(args.path)
                print_json(out)
                return 0
            if args.vault_cmd == "links":
                print_json({"linkedVaults": vault_links()})
                return 0

        if args.command == "source":
            if args.source_cmd == "add":
                out = add_source(args.name, args.target, args.source_type, args.guide)
                print_json(out)
                return 0
            if args.source_cmd == "list":
                sources = load_sources_state().get("sources", [])
                if args.json:
                    print_json(sources)
                else:
                    for s in sources:
                        print(f"{s['id']}\t{s['type']}\t{s['target']}")
                return 0
            if args.source_cmd == "reload":
                imported = reload_source(args.source_id, args.guide)
                print_json({"sourceId": args.source_id, "imported": [str(p) for p in imported]})
                return 0
            if args.source_cmd == "review":
                p = source_review(args.source_id)
                print_json({"review": rel(p)})
                return 0
            if args.source_cmd == "guide":
                p = ensure_source_guide(args.source_id)
                print_json({"guide": rel(p)})
                return 0
            if args.source_cmd == "session":
                p = ensure_source_session(args.source_id)
                print_json({"session": rel(p)})
                return 0
            if args.source_cmd == "delete":
                ok = delete_source(args.source_id)
                print_json({"deleted": ok})
                return 0

        if args.command == "ingest":
            out = ingest(args.target, guide=args.guide, provider_override=args.provider)
            print_json(out)
            return 0

        if args.command == "compile":
            out = compile_candidates(args.approve, args.source_id)
            print_json(out)
            return 0

        if args.command == "bundle":
            if args.bundle_cmd == "list":
                print_json(list_bundles())
                return 0
            if args.bundle_cmd == "apply":
                out = apply_bundle(args.bundle_id, args.target)
                print_json(out)
                return 0

        if args.command == "lint":
            out = lint(args.conflicts)
            print_json(out)
            return 0

        if args.command == "graph":
            vault_id = args.vault_id or config.get("vaultId", "llm-wiki")
            include_linked = bool(args.include_linked or config.get("graph", {}).get("includeLinkedDefault", False))
            export_all = not (args.html or args.svg or args.graphml or args.cypher)
            out = build_graph_exports(
                export_html_flag=args.html or export_all,
                export_svg_flag=args.svg or export_all,
                export_graphml_flag=args.graphml or export_all,
                export_cypher_flag=args.cypher or export_all,
                include_linked=include_linked,
                vault_id=vault_id,
                neo4j_url=args.neo4j_url,
                neo4j_user=args.neo4j_user,
                neo4j_password=args.neo4j_password,
            )
            print_json(out)
            return 0

        if args.command == "query":
            out = query(args.question, args.format, save=not args.no_save)
            print_json(out)
            return 0

        if args.command == "dashboards":
            out = [rel(p) for p in build_dashboards(config)]
            print_json({"dashboards": out})
            return 0

        if args.command == "install-agent-rules":
            agents = None if args.agents == "all" else [slugify(a) for a in args.agents.split(",") if a.strip()]
            out = install_agent_rules(args.graph_first, agents)
            print_json({"installed": [rel(p) for p in out]})
            return 0

        if args.command == "mcp":
            run_mcp_stdio()
            return 0

        if args.command == "watch":
            watch_loop(args.interval, args.once)
            return 0

        if args.command == "automation":
            if args.automation_cmd == "inbox-import":
                out = inbox_import(args.path)
                print_json({"imported": [rel(p) for p in out]})
                return 0
            if args.automation_cmd == "install-hooks":
                hook = install_git_hooks()
                print_json({"hook": rel(hook)})
                return 0
            if args.automation_cmd == "schedule":
                path = save_schedule(args.interval_minutes)
                print_json({"schedule": rel(path)})
                return 0

        if args.command == "providers":
            cfg = load_config()
            model = cfg.get("model", {})
            print_json(
                {
                    "activeProvider": model.get("provider"),
                    "activeModel": model.get("model"),
                    "providers": list(cfg.get("providers", {}).keys()),
                }
            )
            return 0

        print_json({"ok": False, "error": "Unhandled command"})
        return 2
    except Exception as e:
        record_diagnostic("runtime", str(e), {"command": args.command})
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())


