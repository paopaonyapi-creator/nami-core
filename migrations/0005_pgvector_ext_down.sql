-- Phase 29 down — pgvector extension drop.
-- WARNING: drops vector type; only safe if no vector columns exist.
DROP EXTENSION IF EXISTS vector;
