ATTACH TABLE _ UUID '1c1a8494-1cdd-4f3f-8a8e-94ecca5e3e16'
(
    `id` String,
    `filename` String,
    `file_path` String,
    `file_size` UInt64,
    `duration_seconds` Float32,
    `chunk_length_seconds` UInt32,
    `total_chunks` UInt32,
    `processing_status` LowCardinality(String) DEFAULT 'pending',
    `created_at` DateTime DEFAULT now(),
    `updated_at` DateTime DEFAULT now(),
    `processing_started_at` Nullable(DateTime),
    `processing_completed_at` Nullable(DateTime),
    `metadata` String DEFAULT '{}',
    `file_hash` String DEFAULT '',
    `total_episodes` UInt32 DEFAULT 0,
    `successful_episodes` UInt32 DEFAULT 0,
    `failed_episodes` UInt32 DEFAULT 0
)
ENGINE = MergeTree
ORDER BY (id, created_at)
SETTINGS index_granularity = 8192
