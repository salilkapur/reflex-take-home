ATTACH TABLE _ UUID '8fc9ee8a-4b6c-4d63-bf56-56c5dbcbb38c'
(
    `id` String,
    `video_id` String,
    `episode_number` UInt32,
    `start_time` Float32,
    `end_time` Float32,
    `duration` Float32,
    `transcript` String,
    `captions` String DEFAULT '',
    `word_count` UInt32,
    `words` Array(Tuple(word String, start_time Float32, end_time Float32)),
    `created_at` DateTime DEFAULT now(),
    `updated_at` DateTime DEFAULT now(),
    `metadata` String DEFAULT '{}',
    `video_file_path` String DEFAULT '',
    `audio_file_path` String DEFAULT '',
    `processing_time_seconds` Float32 DEFAULT 0,
    `transcription_confidence` Float32 DEFAULT 0
)
ENGINE = MergeTree
ORDER BY (video_id, episode_number, created_at)
SETTINGS index_granularity = 8192
