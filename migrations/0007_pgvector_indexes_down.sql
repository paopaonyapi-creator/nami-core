-- Rollback migration 0007: Drop pgvector indexes.
DROP INDEX IF EXISTS idx_embeddings_cosine;
DROP INDEX IF EXISTS idx_embeddings_namespace_model;
DROP INDEX IF EXISTS idx_episodes_cosine;
