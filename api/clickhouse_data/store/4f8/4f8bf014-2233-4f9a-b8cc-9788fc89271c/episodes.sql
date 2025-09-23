ATTACH TABLE _ UUID '7c3ac3a9-3406-494e-a52a-c12aa2c0484d'
(
    `id` String,
    `video_id` String,
    `episode_number` UInt32,
    `start_time` Float32,
    `end_time` Float32,
    `duration` Float32,
    `transcript` String,
    `word_count` UInt32,
    `words` Array(Tuple(word String, start_time Float32, end_time Float32)),
    `created_at` DateTime DEFAULT now(),
    `updated_at` DateTime DEFAULT now(),
    `metadata` String DEFAULT '{}',
    `video_file_path` String DEFAULT '',
    `audio_file_path` String DEFAULT '',
    `processing_time_seconds` Float32 DEFAULT 0,
    `transcription_confidence` Float32 DEFAULT 0,
    `captions` String DEFAULT '',
    INDEX idx_video_id video_id TYPE bloom_filter GRANULARITY 4,
    INDEX idx_duration duration TYPE minmax GRANULARITY 1,
    INDEX idx_transcript transcript TYPE tokenbf_v1(32768, 3, 0) GRANULARITY 1
)
ENGINE = MergeTree
ORDER BY (video_id, episode_number, created_at)
SETTINGS index_granularity = 8192
