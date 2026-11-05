"""
utils/memory.py — 4-Layer Cognitive Agent Memory System.
Combines:
1. Short-Term Working Memory (Sliding Window in RAM)
2. Reflection Gatekeeper (Filters noise, only persists facts scoring >= 7/10)
3. Entity-Anchored Conflict Resolution (Supersedes outdated beliefs)
4. Upstash Vector Serverless DB (Always online across Render redeploys, with local fallback)
"""
from __future__ import annotations
import json
import uuid
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Optional, Any
import httpx

from config import (
    UPSTASH_VECTOR_REST_URL,
    UPSTASH_VECTOR_REST_TOKEN,
    MEMORY_SIMILARITY_THRESHOLD,
    MEMORY_GATEKEEPER_THRESHOLD,
    TIMEZONE,
)
from utils.logger import logger

LOCAL_MEMORY_FILE = Path(__file__).parent.parent / "data" / "memory.json"

# ============================================================================
# Layer 1: Working Memory Buffer (Sliding Window in RAM)
# ============================================================================

class WorkingMemoryBuffer:
    """Maintains recent conversational turns for immediate back-and-forth context."""
    def __init__(self, maxlen: int = 10):
        self._buffer: deque[dict[str, str]] = deque(maxlen=maxlen)

    def add_turn(self, role: str, content: str) -> None:
        if not content:
            return
        self._buffer.append({
            "role": role,
            "content": content.strip()[:600],
            "timestamp": datetime.now(ZoneInfo(TIMEZONE)).strftime("%H:%M"),
        })

    def get_context_string(self, max_turns: int = 6) -> str:
        if not self._buffer:
            return ""
        turns = list(self._buffer)[-max_turns:]
        lines = []
        for t in turns:
            speaker = "User" if t["role"] == "user" else "J.A.R.V.I.S."
            lines.append(f"{speaker} [{t['timestamp']}]: {t['content']}")
        return "\n".join(lines)

    def clear(self) -> None:
        self._buffer.clear()


# Global working memory instance for the single authorized user
working_memory = WorkingMemoryBuffer(maxlen=10)


# ============================================================================
# Layer 2 & 3: Upstash Vector Store & Local Fallback
# ============================================================================

def _is_upstash_configured() -> bool:
    return bool(UPSTASH_VECTOR_REST_URL and UPSTASH_VECTOR_REST_TOKEN and not UPSTASH_VECTOR_REST_URL.startswith("https://your-"))


def _load_local_memories() -> list[dict]:
    if not LOCAL_MEMORY_FILE.exists():
        return []
    try:
        data = json.loads(LOCAL_MEMORY_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.error(f"Error loading {LOCAL_MEMORY_FILE}: {e}")
        return []


def _save_local_memories(memories: list[dict]) -> None:
    try:
        LOCAL_MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        LOCAL_MEMORY_FILE.write_text(json.dumps(memories, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        logger.error(f"Error saving {LOCAL_MEMORY_FILE}: {e}")


def _upstash_headers() -> dict[str, str]:
    token = UPSTASH_VECTOR_REST_TOKEN.replace("Bearer ", "").strip()
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _clean_upstash_url(endpoint: str) -> str:
    base = UPSTASH_VECTOR_REST_URL.rstrip("/")
    if not endpoint.startswith("/"):
        endpoint = "/" + endpoint
    return f"{base}{endpoint}"


# ============================================================================
# Vector Storage CRUD Operations
# ============================================================================

def upsert_memory_vector(
    memory_id: str,
    memory_text: str,
    metadata: dict[str, Any],
) -> bool:
    """Store or update a memory vector in Upstash Vector (or local fallback)."""
    if _is_upstash_configured():
        url = _clean_upstash_url("/upsert-data")
        payload = {
            "id": memory_id,
            "data": memory_text,
            "metadata": metadata,
        }
        try:
            with httpx.Client(timeout=8.0) as client:
                resp = client.post(url, headers=_upstash_headers(), json=payload)
                if resp.status_code == 200:
                    logger.info(f"✅ Upserted memory [{memory_id}] to Upstash Vector: '{memory_text[:60]}...'")
                    return True
                else:
                    logger.warning(f"Upstash upsert HTTP {resp.status_code}: {resp.text}")
        except Exception as e:
            logger.error(f"Upstash Vector upsert failed: {e}")

    # Fallback to local persistence
    local_mems = _load_local_memories()
    # Replace if id exists
    local_mems = [m for m in local_mems if m["id"] != memory_id]
    local_mems.append({
        "id": memory_id,
        "text": memory_text,
        "metadata": metadata,
        "updated_at": datetime.now(ZoneInfo(TIMEZONE)).isoformat(),
    })
    _save_local_memories(local_mems)
    logger.info(f"Saved memory [{memory_id}] to local storage.")
    return True


def delete_memory_vectors(memory_ids: list[str]) -> bool:
    """Delete memories by ID from Upstash Vector and local store."""
    if not memory_ids:
        return True

    if _is_upstash_configured():
        url = _clean_upstash_url("/delete")
        try:
            with httpx.Client(timeout=8.0) as client:
                resp = client.post(url, headers=_upstash_headers(), json={"ids": memory_ids})
                if resp.status_code == 200:
                    logger.info(f"Deleted {len(memory_ids)} vectors from Upstash.")
        except Exception as e:
            logger.error(f"Upstash Vector delete error: {e}")

    # Also clean local store
    local_mems = _load_local_memories()
    local_mems = [m for m in local_mems if m["id"] not in memory_ids]
    _save_local_memories(local_mems)
    return True


# ============================================================================
# Layer 4: Precision Retrieval Guardrail
# ============================================================================

def recall_relevant_memories(query: str, top_k: int = 3, min_score: Optional[float] = None) -> list[dict]:
    """
    Retrieve top relevant memories using semantic similarity.
    Strictly filters by similarity score >= MEMORY_SIMILARITY_THRESHOLD.
    Excludes alert deduplication tokens and auto-purges temporally expired memories.
    Returns list of dicts: [{"id": str, "text": str, "score": float, "metadata": dict}]
    """
    threshold = min_score if min_score is not None else MEMORY_SIMILARITY_THRESHOLD
    clean_query = query.strip()
    if not clean_query:
        return []

    today_str = datetime.now(ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d")
    expired_ids = []

    # 1. Try Upstash Vector semantic query
    if _is_upstash_configured():
        url = _clean_upstash_url("/query-data")
        payload = {
            "data": clean_query,
            "topK": top_k + 5,
            "includeMetadata": True,
            "includeVectors": False,
        }
        try:
            with httpx.Client(timeout=6.0) as client:
                resp = client.post(url, headers=_upstash_headers(), json=payload)
                if resp.status_code == 200:
                    results = resp.json().get("result", [])
                    matched = []
                    for item in results:
                        item_id = str(item.get("id"))
                        meta = item.get("metadata") or {}

                        # Filter out alert deduplication tokens
                        if item_id.startswith("alt_") or meta.get("type") == "alert_dedupe":
                            continue

                        # Check temporal expiry
                        exp_at = meta.get("expires_at")
                        if exp_at and exp_at < today_str:
                            expired_ids.append(item_id)
                            continue

                        score = float(item.get("score", 0.0))
                        # Upstash cosine similarity score is between -1 and 1 (or 0 and 1)
                        if score >= threshold:
                            text = meta.get("text") or item.get("data") or ""
                            matched.append({
                                "id": item_id,
                                "text": text,
                                "score": round(score, 3),
                                "metadata": meta,
                            })

                    if expired_ids:
                        logger.info(f"Purging {len(expired_ids)} expired memories from vector store.")
                        delete_memory_vectors(expired_ids)

                    if matched:
                        logger.info(f"Recalled {len(matched[:top_k])} memories for query '{query[:40]}' (scores: {[m['score'] for m in matched[:top_k]]})")
                    return matched[:top_k]
                else:
                    logger.warning(f"Upstash query HTTP {resp.status_code}: {resp.text}")
        except Exception as e:
            logger.error(f"Upstash query error: {e}")

    # 2. Fallback to local keyword search
    local_mems = _load_local_memories()
    if not local_mems:
        return []

    query_words = set(clean_query.lower().split())
    ranked = []
    for m in local_mems:
        item_id = str(m.get("id", ""))
        meta = m.get("metadata", {})

        # Filter out alert tokens
        if item_id.startswith("alt_") or meta.get("type") == "alert_dedupe":
            continue

        # Check temporal expiry
        exp_at = meta.get("expires_at")
        if exp_at and exp_at < today_str:
            expired_ids.append(item_id)
            continue

        mem_text = m.get("text", "")
        mem_words = set(mem_text.lower().split())
        overlap = len(query_words.intersection(mem_words))
        if overlap > 0:
            ranked.append({
                "id": item_id,
                "text": mem_text,
                "score": round(overlap / max(1, len(query_words)), 2),
                "metadata": meta,
            })

    if expired_ids:
        delete_memory_vectors(expired_ids)

    ranked.sort(key=lambda x: x["score"], reverse=True)
    return ranked[:top_k]


def format_memories_for_prompt(memories: list[dict]) -> str:
    """Format recalled memories into a concise prompt injection block."""
    if not memories:
        return ""

    lines = ["\n[RECALLED LONG-TERM USER MEMORY & PREFERENCES]"]
    for m in memories:
        lines.append(f"• {m['text']}")
    lines.append("[End of Recalled Memory — Use these preferences naturally without explicitly citing them]\n")
    return "\n".join(lines)


# ============================================================================
# Layer 2 & 3: Background Reflection, Gatekeeper, & Conflict Resolution
# ============================================================================

async def reflect_and_memorize(user_message: str, assistant_reply: str) -> None:
    """
    Asynchronous reflection agent that runs after a message exchange.
    1. Evaluates with Gatekeeper (discards transient noise/queries).
    2. Extracts structured facts (preferences, constraints, habits).
    3. Resolves conflicts (supersedes outdated statements on same entity).
    4. Upserts to Vector Store.
    """
    clean_user = user_message.strip()
    if len(clean_user) < 5:
        return

    # Skip obvious commands that don't reveal personal facts
    if clean_user.startswith("/") and not clean_user.startswith(("/thesis", "/alerts")):
        return

    from ai.gemini_client import generate_json
    from ai.prompts import MEMORY_EXTRACTOR_SYSTEM, MEMORY_EXTRACTOR_PROMPT

    prompt = MEMORY_EXTRACTOR_PROMPT.format(
        user_message=clean_user,
        assistant_reply=assistant_reply[:500],
    )

    try:
        extracted = generate_json(prompt, system_instruction=MEMORY_EXTRACTOR_SYSTEM)
    except Exception as e:
        logger.debug(f"Memory extraction skipped: {e}")
        return

    if not isinstance(extracted, dict):
        return

    should_store = extracted.get("should_store", False)
    importance = int(extracted.get("importance_score", 0))
    memory_text = extracted.get("memory_text", "").strip()
    entity = extracted.get("entity", "").strip()
    category = extracted.get("category", "preference")
    is_correction = extracted.get("is_correction", False)
    raw_exp = extracted.get("expires_at")
    expires_at = None
    if isinstance(raw_exp, str) and raw_exp.strip():
        raw_exp = raw_exp.strip()
        try:
            # Validate format YYYY-MM-DD
            datetime.strptime(raw_exp, "%Y-%m-%d")
            expires_at = raw_exp
        except ValueError:
            expires_at = None

    # 1. Gatekeeper Filter: strictly reject noise, transient lookups, or low importance
    if not should_store or importance < MEMORY_GATEKEEPER_THRESHOLD or not memory_text:
        logger.debug(f"Gatekeeper discarded: '{clean_user[:40]}' (importance={importance})")
        return

    logger.info(f"Gatekeeper approved memory (score={importance}/10): '{memory_text}' [Entity: {entity}, Expires: {expires_at}]")

    # 2. Entity Conflict Resolution: check if prior memories about this entity exist
    if entity:
        existing = recall_relevant_memories(entity, top_k=3, min_score=0.82)
        conflicted_ids = []
        for old in existing:
            old_meta = old.get("metadata", {})
            old_entity = old_meta.get("entity", "").lower()
            if old_entity == entity.lower() or is_correction:
                conflicted_ids.append(old["id"])

        if conflicted_ids:
            logger.info(f"Conflict Resolution: Superseding {len(conflicted_ids)} outdated memories for entity '{entity}'.")
            delete_memory_vectors(conflicted_ids)

    # 3. Upsert New Approved Memory
    mem_id = f"mem_{uuid.uuid4().hex[:8]}"
    now_ist = datetime.now(ZoneInfo(TIMEZONE)).isoformat()
    metadata = {
        "type": "memory",
        "text": memory_text,
        "entity": entity,
        "category": category,
        "importance": importance,
        "expires_at": expires_at,
        "created_at": now_ist,
    }

    upsert_memory_vector(mem_id, memory_text, metadata)


# ============================================================================
# User Transparency & Audit Commands (/memory, /forget)
# ============================================================================

def list_all_memories() -> str:
    """Format all stored user memories into an auditable card."""
    memories = []
    expired_ids = []
    today_str = datetime.now(ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d")

    # If Upstash is configured, query range or dump
    if _is_upstash_configured():
        # Upstash range endpoint allows fetching all stored vectors
        url = _clean_upstash_url("/range")
        try:
            with httpx.Client(timeout=8.0) as client:
                resp = client.post(url, headers=_upstash_headers(), json={"cursor": "0", "limit": 100, "includeMetadata": True})
                if resp.status_code == 200:
                    vectors = resp.json().get("result", {}).get("vectors", [])
                    for v in vectors:
                        v_id = str(v.get("id", ""))
                        meta = v.get("metadata") or {}

                        # Filter out alert deduplication tokens
                        if v_id.startswith("alt_") or meta.get("type") == "alert_dedupe":
                            continue

                        # Check temporal expiry
                        exp_at = meta.get("expires_at")
                        if exp_at and exp_at < today_str:
                            expired_ids.append(v_id)
                            continue

                        memories.append({
                            "id": v_id,
                            "text": meta.get("text") or v.get("data") or "Fact",
                            "entity": meta.get("entity", "General"),
                            "category": meta.get("category", "preference"),
                            "importance": meta.get("importance", 7),
                            "expires_at": exp_at,
                        })
        except Exception as e:
            logger.debug(f"Upstash range error: {e}")

    # Fallback / merge local memories
    if not memories:
        local_mems = _load_local_memories()
        for m in local_mems:
            m_id = str(m.get("id", ""))
            meta = m.get("metadata", {})

            # Filter out alert tokens
            if m_id.startswith("alt_") or meta.get("type") == "alert_dedupe":
                continue

            exp_at = meta.get("expires_at")
            if exp_at and exp_at < today_str:
                expired_ids.append(m_id)
                continue

            memories.append({
                "id": m_id,
                "text": m.get("text", ""),
                "entity": meta.get("entity", "General"),
                "category": meta.get("category", "preference"),
                "importance": meta.get("importance", 7),
                "expires_at": exp_at,
            })

    if expired_ids:
        logger.info(f"Purging {len(expired_ids)} expired memories during listing.")
        delete_memory_vectors(expired_ids)

    if not memories:
        status_note = "☁️ Upstash Cloud Vector DB Active" if _is_upstash_configured() else "📁 Local Resilient Store Active"
        return (
            f"🧠 **Jarvis Long-Term Memory**\n_{status_note}_\n\n"
            "I have not logged any persistent personal facts or preferences yet, sir.\n\n"
            "_As you speak with me about your routines, investment preferences, or guidelines, "
            "I will autonomously evaluate and retain them._"
        )

    status_note = "☁️ Upstash Vector Cloud" if _is_upstash_configured() else "📁 Local Store"
    lines = [f"🧠 **Jarvis Learned Memory ({len(memories)} facts)**\n_{status_note}_\n"]
    for i, m in enumerate(memories, 1):
        cat_tag = f" `[{m['category'].title()}]`" if m.get("category") else ""
        exp_tag = f" ⏳ _(Expires: {m['expires_at']})_" if m.get("expires_at") else ""
        lines.append(f"{i}. {m['text']}{cat_tag}{exp_tag} (`{m['id']}`)")
    lines.append("\n💡 _Use `/forget <topic or id>` if you ever want me to erase a memory._")
    return "\n".join(lines)


def forget_memory(query: str) -> tuple[bool, str]:
    """Search for memories matching query/entity/id and remove them."""
    clean_q = query.strip()
    if not clean_q:
        return False, "Please specify a topic, company, or memory ID to forget (e.g. `/forget Tata Motors` or `/forget mem_123`)."

    # 1. Exact ID check
    if clean_q.startswith("mem_"):
        delete_memory_vectors([clean_q])
        return True, f"✅ Erased memory `{clean_q}` from my neural index, sir."

    # 2. Semantic lookup to find relevant memories to erase
    matched = recall_relevant_memories(clean_q, top_k=5, min_score=0.72)
    if not matched:
        # Check local keyword match
        local_mems = _load_local_memories()
        matched = [m for m in local_mems if clean_q.lower() in m.get("text", "").lower()]

    if not matched:
        return False, f"❌ I could not find any memories related to *'{clean_q}'* in my index, sir."

    ids_to_delete = [m["id"] for m in matched]
    delete_memory_vectors(ids_to_delete)

    deleted_previews = "\n".join([f"• _{m['text'][:70]}..._" for m in matched[:3]])
    return True, f"✅ Erased {len(ids_to_delete)} memory entry(s) related to *'{clean_q}'*:\n{deleted_previews}"
