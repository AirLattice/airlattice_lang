"""Code to ingest blob into a vectorstore.

Code is responsible for taking binary data, parsing it and then indexing it
into a vector store.

This code should be agnostic to how the blob got generated; i.e., it does not
know about server/uploading etc.
"""
from typing import Callable, List, Optional

from langchain.text_splitter import TextSplitter
from langchain_community.document_loaders import Blob
from langchain_community.document_loaders.base import BaseBlobParser
from langchain_core.documents import Document
from langchain_core.vectorstores import VectorStore


def _update_document_metadata(document: Document, namespace: str) -> None:
    """Mutation in place that adds a namespace to the document metadata."""
    document.metadata["namespace"] = namespace


def _sanitize_document_content(document: Document) -> Document:
    """Sanitize the document."""
    # Without this, PDF ingestion fails with
    # "A string literal cannot contain NUL (0x00) characters".
    document.page_content = document.page_content.replace("\x00", "x")


# PUBLIC API


def ingest_blob(
    blob: Blob,
    parser: BaseBlobParser,
    text_splitter: TextSplitter,
    vectorstore: VectorStore,
    namespace: str,
    *,
    batch_size: int = 100,
    max_batch_chars: int = 50_000,
    progress_callback: Optional[Callable[[int], None]] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> List[str]:
    """Ingest a document into the vectorstore."""
    docs_to_index = []
    ids = []
    batch_chars = 0
    for document in parser.lazy_parse(blob):
        docs = text_splitter.split_documents([document])
        for doc in docs:
            if should_cancel and should_cancel():
                return ids
            _sanitize_document_content(doc)
            _update_document_metadata(doc, namespace)
            docs_to_index.append(doc)
            batch_chars += len(doc.page_content)
            if progress_callback:
                processed_bytes = len(doc.page_content.encode("utf-8"))
                if processed_bytes:
                    progress_callback(processed_bytes)

            if len(docs_to_index) >= batch_size or batch_chars >= max_batch_chars:
                if should_cancel and should_cancel():
                    return ids
                ids.extend(vectorstore.add_documents(docs_to_index))
                docs_to_index = []
                batch_chars = 0

    if docs_to_index:
        if should_cancel and should_cancel():
            return ids
        ids.extend(vectorstore.add_documents(docs_to_index))

    return ids
