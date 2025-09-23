ATTACH TABLE _ UUID 'ce7af5c9-b480-435c-83bd-59bfa2c57391'
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
    `failed_episodes` UInt32 DEFAULT 0,
    INDEX idx_filename filename TYPE bloom_filter GRANULARITY 4,
    INDEX idx_status processing_status TYPE set(0) GRANULARITY 1,
    INDEX idx_created created_at TYPE minmax GRANULARITY 1
)
ENGINE = MergeTree
ORDER BY (id, created_at)
SETTINGS index_granularity = 8192
