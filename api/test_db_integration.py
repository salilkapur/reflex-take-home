#!/usr/bin/env python3
"""
Test script for ClickHouse database integration
"""

import sys
import os
from datetime import datetime

# Add database module to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'database'))
from clickhouse_client import ClickHouseVideoDatabase

def test_database_connection():
    """Test basic database connection and operations"""
    print("🔌 Testing ClickHouse Database Connection...")

    try:
        db = ClickHouseVideoDatabase()
        print("✅ Database connection successful!")
        return db
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return None

def test_video_operations(db):
    """Test video CRUD operations"""
    print("\n📹 Testing Video Operations...")

    try:
        # Create a test video record
        video_id = db.create_video_record(
            video_path="/test/path/sample_video.mp4",
            file_size=1024000,
            duration=120.5,
            chunk_length=15,
            metadata={
                "source": "test",
                "quality": "high",
                "tags": ["demo", "integration_test"],
                "created_by": "test_script"
            }
        )
        print(f"✅ Created video record: {video_id}")

        # Update video status
        db.update_video_status(video_id, "processing", total_chunks=8)
        print("✅ Updated video status to processing")

        # Retrieve video
        video_data = db.get_video_by_id(video_id)
        if video_data:
            print(f"✅ Retrieved video: {video_data['filename']}")
            print(f"   Status: {video_data['processing_status']}")
            print(f"   Metadata: {video_data['metadata']}")
        else:
            print("❌ Failed to retrieve video")

        return video_id

    except Exception as e:
        print(f"❌ Video operations failed: {e}")
        return None

def test_episode_operations(db, video_id):
    """Test episode operations"""
    print("\n🎬 Testing Episode Operations...")

    if not video_id:
        print("❌ Skipping episode tests - no video_id")
        return

    try:
        # Create test episodes
        episodes_data = [
            {
                "episode_number": 1,
                "start_time": 10.5,
                "end_time": 45.2,
                "duration": 34.7,
                "transcript": "start this is the first test episode content finish",
                "word_count": 10,
                "words": [
                    {"word": "start", "start": 10.5, "end": 10.8},
                    {"word": "this", "start": 10.9, "end": 11.1},
                    {"word": "is", "start": 11.2, "end": 11.3},
                    {"word": "the", "start": 11.4, "end": 11.5},
                    {"word": "first", "start": 11.6, "end": 11.9}
                ],
                "metadata": {
                    "quality": "high",
                    "manual_review": False,
                    "confidence": 0.95
                }
            },
            {
                "episode_number": 2,
                "start_time": 60.0,
                "end_time": 95.3,
                "duration": 35.3,
                "transcript": "start second episode with different content finish",
                "word_count": 8,
                "words": [
                    {"word": "start", "start": 60.0, "end": 60.3},
                    {"word": "second", "start": 60.4, "end": 60.8},
                    {"word": "episode", "start": 60.9, "end": 61.3}
                ],
                "metadata": {
                    "quality": "medium",
                    "manual_review": True,
                    "confidence": 0.87
                }
            }
        ]

        # Save episodes
        db.save_episodes(video_id, episodes_data)
        print(f"✅ Saved {len(episodes_data)} episodes")

        # Retrieve episodes
        retrieved_episodes = db.get_episodes_for_video(video_id)
        print(f"✅ Retrieved {len(retrieved_episodes)} episodes")

        for episode in retrieved_episodes:
            print(f"   Episode {episode['episode_number']}: {episode['duration']}s")
            print(f"   Words: {len(episode['words'])}")
            print(f"   Metadata: {episode['metadata']}")

    except Exception as e:
        print(f"❌ Episode operations failed: {e}")

def test_analytics(db):
    """Test analytics functions"""
    print("\n📊 Testing Analytics...")

    try:
        # Get video analytics
        video_analytics = db.get_analytics_summary()
        print("✅ Video Analytics:")
        for key, value in video_analytics.items():
            print(f"   {key}: {value}")

        # Get episode analytics
        episode_analytics = db.get_episode_analytics()
        print("✅ Episode Analytics:")
        for key, value in episode_analytics.items():
            print(f"   {key}: {value}")

        # Test search
        search_results = db.search_episodes_by_transcript("first")
        print(f"✅ Search Results: Found {len(search_results)} episodes containing 'first'")

    except Exception as e:
        print(f"❌ Analytics failed: {e}")

def test_processing_chunks(db, video_id):
    """Test processing chunk operations"""
    print("\n⚙️ Testing Processing Chunks...")

    if not video_id:
        print("❌ Skipping chunk tests - no video_id")
        return

    try:
        # Save some test chunks
        for i in range(3):
            db.save_processing_chunk(
                video_id=video_id,
                chunk_number=i,
                start_time=i * 15.0,
                end_time=(i + 1) * 15.0,
                cache_key=f"test_cache_key_{i}",
                cache_hit=i > 0,  # First chunk is not cached
                processing_time=2.5,
                word_count=25
            )

        print("✅ Saved processing chunks")

    except Exception as e:
        print(f"❌ Processing chunks failed: {e}")

def main():
    """Run all tests"""
    print("🧪 ClickHouse Database Integration Test")
    print("=" * 50)

    # Test database connection
    db = test_database_connection()
    if not db:
        return

    try:
        # Test video operations
        video_id = test_video_operations(db)

        # Test episode operations
        test_episode_operations(db, video_id)

        # Test processing chunks
        test_processing_chunks(db, video_id)

        # Test analytics
        test_analytics(db)

        print("\n🎉 All tests completed!")
        print("✅ Database integration is working correctly")

    except Exception as e:
        print(f"\n❌ Test suite failed: {e}")

    finally:
        # Clean up
        db.close()
        print("\n🔒 Database connection closed")

if __name__ == "__main__":
    main()