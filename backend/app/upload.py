"""API to deal with file uploads via a runnable.

For now this code assumes that the content is a base64 encoded string.

The details here might change in the future.

For the time being, upload and ingestion are coupled
"""

from __future__ import annotations

import mimetypes
import os
from typing import BinaryIO, Callable, List, Optional

from fastapi import UploadFile
from langchain_community.vectorstores.pgvector import PGVector
from langchain_core.document_loaders.blob_loaders import Blob
from langchain_core.runnables import (
    ConfigurableField,
    RunnableConfig,
    RunnableSerializable,
)
from langchain_core.vectorstores import VectorStore
from langchain_openai import AzureOpenAIEmbeddings, OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter, TextSplitter
from pydantic import ConfigDict

from app.embeddings import get_embeddings_client
from app.ingest import ingest_blob
from app.parsing import MIMETYPE_BASED_PARSER


def _guess_mimetype(file_name: str, file_bytes: bytes) -> str:
    """Guess the mime-type of a file based on its name or bytes."""
    # Guess based on the file extension
    mime_type, _ = mimetypes.guess_type(file_name)

    # Return detected mime type from mimetypes guess, unless it's None
    if mime_type:
        return mime_type

    # Signature-based detection for common types
    if file_bytes.startswith(b"%PDF"):
        return "application/pdf"
    elif file_bytes.startswith(
        (b"\x50\x4B\x03\x04", b"\x50\x4B\x05\x06", b"\x50\x4B\x07\x08")
    ):
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    elif file_bytes.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        return "application/msword"
    elif file_bytes.startswith(b"\x09\x00\xff\x00\x06\x00"):
        return "application/vnd.ms-excel"

    # Check for CSV-like plain text content (commas, tabs, newlines)
    try:
        decoded = file_bytes[:1024].decode("utf-8", errors="ignore")
        if all(char in decoded for char in (",", "\n")) or all(
            char in decoded for char in ("\t", "\n")
        ):
            return "text/csv"
        elif decoded.isprintable() or decoded == "":
            return "text/plain"
    except UnicodeDecodeError:
        pass

    return "application/octet-stream"


def convert_ingestion_input_to_blob(file: UploadFile) -> tuple[Blob, int]:
    """Convert ingestion input to blob."""
    file_data = file.file.read()
    file_name = file.filename

    # Check if file_name is a valid string
    if not isinstance(file_name, str):
        raise TypeError(f"Expected string for file name, got {type(file_name)}")

    mimetype = _guess_mimetype(file_name, file_data)
    blob = Blob.from_data(
        data=file_data,
        path=file_name,
        mime_type=mimetype,
    )
    return blob, len(file_data)


def _collection_name() -> str:
    provider = os.environ.get("EMBEDDINGS_PROVIDER", "").lower()
    if provider == "local":
        model_id = os.environ.get("EMBEDDINGS_MODEL_ID", "local").lower()
        sanitized = model_id.replace("/", "_").replace(":", "_")
        return f"opengpts_local_{sanitized}"
    if os.environ.get("AZURE_OPENAI_API_KEY"):
        return "opengpts_azure_embeddings"
    return "opengpts_openai_embeddings"


def _determine_embeddings() -> PGVector:
    if os.environ.get("EMBEDDINGS_PROVIDER", "").lower() == "local":
        return PGVector(
            connection_string=PG_CONNECTION_STRING,
            embedding_function=get_embeddings_client(),
            use_jsonb=True,
            collection_name=_collection_name(),
        )
    if os.environ.get("OPENAI_API_KEY"):
        return PGVector(
            connection_string=PG_CONNECTION_STRING,
            embedding_function=OpenAIEmbeddings(),
            use_jsonb=True,
            collection_name=_collection_name(),
        )
    if os.environ.get("AZURE_OPENAI_API_KEY"):
        return PGVector(
            connection_string=PG_CONNECTION_STRING,
            embedding_function=AzureOpenAIEmbeddings(
                azure_endpoint=os.environ.get("AZURE_OPENAI_API_BASE"),
                azure_deployment=os.environ.get(
                    "AZURE_OPENAI_EMBEDDINGS_DEPLOYMENT_NAME"
                ),
                openai_api_version=os.environ.get("AZURE_OPENAI_API_VERSION"),
            ),
            use_jsonb=True,
            collection_name=_collection_name(),
        )
    raise ValueError(
        "Set EMBEDDINGS_PROVIDER=local with EMBEDDINGS_URL, or configure OPENAI_API_KEY/AZURE_OPENAI_API_KEY."
    )


class IngestRunnable(RunnableSerializable[BinaryIO, List[str]]):
    """Runnable for ingesting files into a vectorstore."""

    text_splitter: TextSplitter
    vectorstore: VectorStore
    assistant_id: Optional[str] = None
    thread_id: Optional[str] = None
    """Ingested documents will be associated with assistant_id or thread_id.
    
    ID is used as the namespace, and is filtered on at query time.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @property
    def namespace(self) -> str:
        if (self.assistant_id is None and self.thread_id is None) or (
            self.assistant_id is not None and self.thread_id is not None
        ):
            raise ValueError(
                "Exactly one of assistant_id or thread_id must be provided"
            )
        return self.assistant_id if self.assistant_id is not None else self.thread_id

    def invoke(
        self,
        blob: Blob,
        config: Optional[RunnableConfig] = None,
        *,
        progress_callback: Optional[Callable[[int], None]] = None,
        should_cancel: Optional[Callable[[], bool]] = None,
    ) -> List[str]:
        out = ingest_blob(
            blob,
            MIMETYPE_BASED_PARSER,
            self.text_splitter,
            self.vectorstore,
            self.namespace,
            batch_size=5,
            max_batch_chars=50_000,
            progress_callback=progress_callback,
            should_cancel=should_cancel,
        )
        return out


PG_CONNECTION_STRING = PGVector.connection_string_from_db_params(
    driver="psycopg2",
    host=os.environ["POSTGRES_HOST"],
    port=int(os.environ["POSTGRES_PORT"]),
    database=os.environ["POSTGRES_DB"],
    user=os.environ["POSTGRES_USER"],
    password=os.environ["POSTGRES_PASSWORD"],
)
vstore = _determine_embeddings()


ingest_runnable = IngestRunnable(
    text_splitter=RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200),
    vectorstore=vstore,
).configurable_fields(
    assistant_id=ConfigurableField(
        id="assistant_id",
        annotation=Optional[str],
        name="Assistant ID",
    ),
    thread_id=ConfigurableField(
        id="thread_id",
        annotation=Optional[str],
        name="Thread ID",
    ),
)
