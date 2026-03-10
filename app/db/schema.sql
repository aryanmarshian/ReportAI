-- PostgreSQL schema for reportai

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS tasks (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    input_text TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,
    plan_json JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE tasks
ADD COLUMN IF NOT EXISTS plan_json JSONB;

ALTER TABLE tasks
ADD COLUMN IF NOT EXISTS input_text TEXT NOT NULL DEFAULT '';

CREATE TABLE IF NOT EXISTS agent_outputs (
    id BIGSERIAL PRIMARY KEY,
    task_id BIGINT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    agent_name TEXT NOT NULL,
    output_json JSONB NOT NULL,
    confidence NUMERIC(5,4),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS memory_embeddings (
    id BIGSERIAL PRIMARY KEY,
    task_id BIGINT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    embedding_vector VECTOR
);

CREATE INDEX IF NOT EXISTS idx_tasks_user_id ON tasks(user_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_agent_outputs_task_id ON agent_outputs(task_id);
CREATE INDEX IF NOT EXISTS idx_memory_embeddings_task_id ON memory_embeddings(task_id);
