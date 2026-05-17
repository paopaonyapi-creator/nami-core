-- Migration 0007: Create IVFFlat cosine index on embeddings table.
-- Improves query_semantic() performance for >100 rows.
-- Note: IVFFlat requires at least some data to build the index.
-- If the table is empty, CREATE INDEX will succeed but the index
-- will be empty until the first VACUUM ANALYZE after data load.

-- Create the IVFFlat index for cosine similarity search
CREATE INDEX IF NOT EXISTS idx_embeddings_cosine
    ON embeddings USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- Create a B-tree index for common filtered queries
CREATE INDEX IF NOT EXISTS idx_embeddings_namespace_model
    ON embeddings (namespace, model_version);

-- Index for agent_episodes embedding search (if populated)
CREATE INDEX IF NOT EXISTS idx_episodes_cosine
    ON agent_episodes USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 50);

-- Refresh statistics
ANALYZE embeddings;
ANALYZE agent_episodes;
