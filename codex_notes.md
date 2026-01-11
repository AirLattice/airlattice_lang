# Codex Continuity Notes

## Project
- Repo: /home/airlattice/opengpts
- Goal: Local OpenGPTs setup with JWT login, local embeddings, RAG uploads, upload progress + cancel.

## Current State
- Running services: postgres, backend, frontend, embeddings (TEI) via docker compose.
- JWT auth enabled; login via /login, token in localStorage.
- Local embeddings enabled; current model: BAAI/bge-m3.
- Upload progress shown in UI; cancel now calls backend cancel endpoint.
- Token usage shown as estimated in UI.

## Key Config
- .env:
  - AUTH_TYPE=jwt_local
  - JWT_ISS/JWT_AUD/JWT_ALG/JWT_DECODE_KEY_B64 set
  - EMBEDDINGS_PROVIDER=local
  - EMBEDDINGS_URL=http://embeddings:8080
  - EMBEDDINGS_MODEL_ID=BAAI/bge-m3
- docker-compose.yml includes embeddings service and mounts ./embeddings-cache

## Embeddings Model Cache
- BAAI/bge-m3 path: /home/airlattice/opengpts/embeddings-cache/BAAI/bge-m3
- intfloat/multilingual-e5-small path: /home/airlattice/opengpts/embeddings-cache/intfloat/multilingual-e5-small

## Notable Changes
- /login + /me endpoints added (jwt_local only)
- Frontend auth gate + login page + authFetch
- File upload: CSV support, larger max size, progress display, cancel API
- Local embeddings service (HuggingFace TEI)
- Token usage display (estimated)

## Known Issues/Notes
- Local embeddings can be slow for large files (CPU-bound)
- Cancel stops future batches; in-flight embed requests finish
- RAG query rewrite may generate unexpected queries

## Helpful Commands
- docker compose up -d
- docker compose logs -f backend
- docker compose logs -f embeddings
- docker compose logs -f frontend

