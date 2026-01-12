from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Sequence

from langchain_core.documents import Document
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from app.lifespan import get_pg_pool
from app.upload import _collection_name, vstore

MEMORY_SOURCE = "memory"


def memory_namespace(user_id: str) -> str:
    return f"user:{user_id}"


def _build_memory_document(
    *,
    content: str,
    user_id: str,
    thread_id: Optional[str],
    assistant_id: Optional[str],
    role: str,
) -> Document:
    text = content.strip()
    metadata = {
        "namespace": memory_namespace(user_id),
        "source": MEMORY_SOURCE,
        "role": role,
        "user_id": user_id,
        "thread_id": thread_id,
        "assistant_id": assistant_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    return Document(page_content=text, metadata=metadata)


def store_memory_messages(
    *,
    messages: Sequence[BaseMessage],
    user_id: str,
    thread_id: Optional[str],
    assistant_id: Optional[str],
) -> None:
    docs: list[Document] = []
    for message in messages:
        content = message.content
        if not isinstance(content, str) or not content.strip():
            continue
        if isinstance(message, HumanMessage):
            content = f"User: {content}"
            docs.append(
                _build_memory_document(
                    content=content,
                    user_id=user_id,
                    thread_id=thread_id,
                    assistant_id=assistant_id,
                    role="user",
                )
            )
        elif isinstance(message, AIMessage):
            content = f"Assistant: {content}"
            docs.append(
                _build_memory_document(
                    content=content,
                    user_id=user_id,
                    thread_id=thread_id,
                    assistant_id=assistant_id,
                    role="assistant",
                )
            )
    if docs:
        vstore.add_documents(docs)


def store_user_message(
    *,
    user_id: str,
    content: str,
    thread_id: Optional[str],
    assistant_id: Optional[str],
) -> None:
    if not content or not content.strip():
        return
    doc = _build_memory_document(
        content=f"User: {content}",
        user_id=user_id,
        thread_id=thread_id,
        assistant_id=assistant_id,
        role="user",
    )
    vstore.add_documents([doc])


def get_memory_retriever(user_id: str, *, k: int = 4):
    return vstore.as_retriever(
        search_kwargs={
            "k": k,
            "filter": {
                "namespace": {"$in": [memory_namespace(user_id)]},
                "source": MEMORY_SOURCE,
            },
        }
    )


async def build_memory_context(
    *,
    user_id: str,
    query: str,
    max_items: int = 4,
    max_chars: int = 1200,
) -> Optional[str]:
    if not query or not query.strip():
        return None
    retriever = get_memory_retriever(user_id, k=max_items)
    docs = await retriever.ainvoke(query)
    if not docs:
        return None
    lines: list[str] = []
    used_chars = 0
    for doc in docs:
        text = doc.page_content.strip()
        if not text:
            continue
        line = f"- {text}"
        if used_chars + len(line) > max_chars:
            break
        lines.append(line)
        used_chars += len(line)
    if not lines:
        return None
    return "User memory (use only if relevant):\n" + "\n".join(lines)


async def list_user_memory(
    *,
    user_id: str,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    async with get_pg_pool().acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT e.uuid, e.document, e.cmetadata
            FROM langchain_pg_embedding e
            JOIN langchain_pg_collection c ON e.collection_id = c.uuid
            WHERE c.name = $1
              AND e.cmetadata->>'source' = $2
              AND e.cmetadata->>'user_id' = $3
            ORDER BY e.cmetadata->>'created_at' DESC
            LIMIT $4 OFFSET $5
            """,
            _collection_name(),
            MEMORY_SOURCE,
            user_id,
            limit,
            offset,
        )
    items: list[dict] = []
    for row in rows:
        metadata = row["cmetadata"] or {}
        items.append(
            {
                "id": str(row["uuid"]),
                "content": row["document"],
                "role": metadata.get("role"),
                "created_at": metadata.get("created_at"),
                "thread_id": metadata.get("thread_id"),
                "assistant_id": metadata.get("assistant_id"),
            }
        )
    return items


async def delete_user_memory(
    *,
    user_id: str,
    memory_id: str,
) -> bool:
    async with get_pg_pool().acquire() as conn:
        result = await conn.execute(
            """
            DELETE FROM langchain_pg_embedding e
            USING langchain_pg_collection c
            WHERE e.collection_id = c.uuid
              AND c.name = $1
              AND e.uuid = $2
              AND e.cmetadata->>'source' = $3
              AND e.cmetadata->>'user_id' = $4
            """,
            _collection_name(),
            memory_id,
            MEMORY_SOURCE,
            user_id,
        )
    return result.split()[-1] != "0"


async def clear_user_memory(*, user_id: str) -> int:
    async with get_pg_pool().acquire() as conn:
        result = await conn.execute(
            """
            DELETE FROM langchain_pg_embedding e
            USING langchain_pg_collection c
            WHERE e.collection_id = c.uuid
              AND c.name = $1
              AND e.cmetadata->>'source' = $2
              AND e.cmetadata->>'user_id' = $3
            """,
            _collection_name(),
            MEMORY_SOURCE,
            user_id,
        )
    return int(result.split()[-1])
