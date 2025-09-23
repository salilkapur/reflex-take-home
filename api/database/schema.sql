-- ClickHouse Database Schema for Video Episode Processing
-- Run these commands in ClickHouse client

-- Create database
CREATE DATABASE IF NOT EXISTS video_episodes;
USE video_episodes;

-- Videos table - stores video file information
CREATE TABLE videos (
    id String,
    filename String,
    file_path String,
    file_size UInt64,
    duration_seconds Float32,
    chunk_length_seconds UInt32,
    total_chunks UInt32,
    processing_status LowCardinality(String) DEFAULT 'pending', -- pending, processing, completed, failed

    -- Timestamps
    created_at DateTime DEFAULT now(),
    updated_at DateTime DEFAULT now(),
    processing_started_at Nullable(DateTime),
    processing_completed_at Nullable(DateTime),

    -- Video metadata (configurable JSON)
    metadata String DEFAULT '{}', -- JSON string for flexible metadata

    -- File hash for deduplication
    file_hash String DEFAULT '',

    -- Processing statistics
    total_episodes UInt32 DEFAULT 0,
    successful_episodes UInt32 DEFAULT 0,
    failed_episodes UInt32 DEFAULT 0

) ENGINE = MergeTree()
ORDER BY (id, created_at)
SETTINGS index_granularity = 8192;

-- Episodes table - stores individual episodes
CREATE TABLE episodes (
    id String,
    video_id String,
    episode_number UInt32,

    -- Time boundaries
    start_time Float32,
    end_time Float32,
    duration Float32,

    -- Content
    transcript String,
    captions String DEFAULT '',
    word_count UInt32,

    -- Word-level data stored as arrays for efficiency
    words Array(Tuple(word String, start_time Float32, end_time Float32)),

    -- Timestamps
    created_at DateTime DEFAULT now(),
    updated_at DateTime DEFAULT now(),

    -- Episode metadata (configurable JSON)
    metadata String DEFAULT '{}', -- JSON string for custom fields

    -- Extracted file paths (if episodes are saved as separate files)
    video_file_path String DEFAULT '',
    audio_file_path String DEFAULT '',

    -- Quality metrics
    processing_time_seconds Float32 DEFAULT 0,
    transcription_confidence Float32 DEFAULT 0

) ENGINE = MergeTree()
ORDER BY (video_id, episode_number, created_at)
SETTINGS index_granularity = 8192;

-- Processing chunks table - for caching and debugging
CREATE TABLE processing_chunks (
    id String,
    video_id String,
    chunk_number UInt32,

    -- Chunk boundaries
    start_time Float32,
    end_time Float32,
    duration Float32,

    -- Caching
    cache_key String,
    cache_hit UInt8 DEFAULT 0, -- 1 if loaded from cache, 0 if processed

    -- Processing info
    processing_time_seconds Float32,
    transcription_word_count UInt32,

    -- Timestamps
    created_at DateTime DEFAULT now(),
    processed_at DateTime DEFAULT now()

) ENGINE = MergeTree()
ORDER BY (video_id, chunk_number, created_at)
SETTINGS index_granularity = 8192;

-- Create indexes for better query performance
-- Videos indexes
ALTER TABLE videos ADD INDEX idx_filename filename TYPE bloom_filter GRANULARITY 4;
ALTER TABLE videos ADD INDEX idx_status processing_status TYPE set(0) GRANULARITY 1;
ALTER TABLE videos ADD INDEX idx_created created_at TYPE minmax GRANULARITY 1;

-- Episodes indexes
ALTER TABLE episodes ADD INDEX idx_video_id video_id TYPE bloom_filter GRANULARITY 4;
ALTER TABLE episodes ADD INDEX idx_duration duration TYPE minmax GRANULARITY 1;
ALTER TABLE episodes ADD INDEX idx_transcript transcript TYPE tokenbf_v1(32768, 3, 0) GRANULARITY 1;

-- Processing chunks indexes
ALTER TABLE processing_chunks ADD INDEX idx_cache_key cache_key TYPE bloom_filter GRANULARITY 4;
ALTER TABLE processing_chunks ADD INDEX idx_cache_hit cache_hit TYPE set(0) GRANULARITY 1;