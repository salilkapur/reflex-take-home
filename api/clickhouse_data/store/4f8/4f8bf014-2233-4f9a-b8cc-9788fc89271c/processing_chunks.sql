ATTACH TABLE _ UUID '80c01914-cc59-42da-93a1-4a1131bb2d1e'
(
    `id` String,
    `video_id` String,
    `chunk_number` UInt32,
    `start_time` Float32,
    `end_time` Float32,
    `duration` Float32,
    `cache_key` String,
    `cache_hit` UInt8 DEFAULT 0,
    `processing_time_seconds` Float32,
    `transcription_word_count` UInt32,
    `created_at` DateTime DEFAULT now(),
    `processed_at` DateTime DEFAULT now(),
    INDEX idx_cache_key cache_key TYPE bloom_filter GRANULARITY 4,
    INDEX idx_cache_hit cache_hit TYPE set(0) GRANULARITY 1
)
ENGINE = MergeTree
ORDER BY (video_id, chunk_number, created_at)
SETTINGS index_granularity = 8192
