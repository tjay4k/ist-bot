-- ============================================================
-- MESSAGE IMAGE CACHE
-- ============================================================

CREATE TABLE IF NOT EXISTS message_images (
    id SERIAL PRIMARY KEY,
    message_id BIGINT NOT NULL,
    attachment_id BIGINT NOT NULL,
    filename VARCHAR(255) NOT NULL,
    filepath TEXT NOT NULL,
    file_type VARCHAR(50),  -- 'image', 'gif', 'document', etc.
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(message_id, attachment_id)
);

-- Index for faster lookups on delete
CREATE INDEX IF NOT EXISTS idx_message_images_message_id ON message_images(message_id);

-- Index for cleanup task
CREATE INDEX IF NOT EXISTS idx_message_images_created_at ON message_images(created_at);