import asyncio
import json
import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime
import clickhouse_connect
from clickhouse_connect.driver.exceptions import DatabaseError


class ClickHouseVideoDatabase:
    """
    ClickHouse database client for video episode processing.
    Handles videos, episodes, and processing chunks with configurable metadata.
    """

    def __init__(self, host: str = 'localhost', port: int = 8123, database: str = 'video_episodes',
                 username: str = 'default', password: str = ''):
        """
        Initialize ClickHouse client.

        Args:
            host: ClickHouse server host
            port: ClickHouse HTTP port
            database: Database name
            username: Username
            password: Password
        """
        self.host = host
        self.port = port
        self.database = database
        self.username = username
        self.password = password

    def _get_client(self):
        """Get a new ClickHouse client instance for thread safety."""
        return clickhouse_connect.get_client(
            host=self.host,
            port=self.port,
            database=self.database,
            username=self.username,
            password=self.password
        )

    @property
    def client(self):
        """Maintain backward compatibility for direct client access."""
        return self._get_client()

    def _execute_query(self, query: str, parameters: Dict[str, Any] = None):
        """Execute a query with a dedicated client instance."""
        client = self._get_client()
        return client.query(query, parameters=parameters)

    def _execute_command(self, command: str):
        """Execute a command with a dedicated client instance."""
        client = self._get_client()
        return client.command(command)

    def _execute_insert(self, table: str, data: list, column_names: list):
        """Execute an insert with a dedicated client instance."""
        client = self._get_client()
        return client.insert(table, data, column_names=column_names)

    def create_video_record(self, video_path: str, file_size: int, duration: float,
                          chunk_length: int, metadata: Dict[str, Any] = None) -> str:
        """
        Create a new video record in the database.

        Args:
            video_path: Path to the video file
            file_size: Size of the video file in bytes
            duration: Duration of the video in seconds
            chunk_length: Length of processing chunks in seconds
            metadata: Custom metadata dictionary

        Returns:
            Video ID (UUID string)
        """
        video_id = str(uuid.uuid4())
        metadata_json = json.dumps(metadata or {})

        query = """
        INSERT INTO videos (
            id, filename, file_path, file_size, duration_seconds,
            chunk_length_seconds, metadata, processing_status
        ) VALUES
        """

        data = [(
            video_id,
            video_path.split('/')[-1],  # Extract filename
            video_path,
            file_size,
            duration,
            chunk_length,
            metadata_json,
            'pending'
        )]

        self._execute_insert('videos', data, column_names=[
            'id', 'filename', 'file_path', 'file_size', 'duration_seconds',
            'chunk_length_seconds', 'metadata', 'processing_status'
        ])

        return video_id

    def update_video_status(self, video_id: str, status: str, **kwargs):
        """
        Update video processing status and other fields.

        Args:
            video_id: Video ID
            status: New processing status
            **kwargs: Additional fields to update (total_chunks, successful_episodes, etc.)
        """
        set_clauses = [f"processing_status = '{status}'", "updated_at = now()"]

        if status == 'processing':
            set_clauses.append("processing_started_at = now()")
        elif status == 'completed':
            set_clauses.append("processing_completed_at = now()")

        for key, value in kwargs.items():
            if isinstance(value, str):
                set_clauses.append(f"{key} = '{value}'")
            else:
                set_clauses.append(f"{key} = {value}")

        query = f"""
        ALTER TABLE videos UPDATE {', '.join(set_clauses)}
        WHERE id = '{video_id}'
        """

        self._execute_command(query)

    def save_episodes(self, video_id: str, episodes: List[Dict[str, Any]]):
        """
        Save episodes to the database.

        Args:
            video_id: Video ID
            episodes: List of episode dictionaries
        """
        if not episodes:
            return

        data = []
        for episode in episodes:
            episode_id = str(uuid.uuid4())

            # Convert words to ClickHouse tuple array format
            words_array = [
                (word_data['word'], word_data['start'], word_data['end'])
                for word_data in episode.get('words', [])
            ]

            # Prepare metadata
            metadata = episode.get('metadata', {})
            metadata_json = json.dumps(metadata)

            data.append((
                episode_id,
                video_id,
                episode['episode_number'],
                episode['start_time'],
                episode['end_time'],
                episode['duration'],
                episode['transcript'],
                episode['word_count'],
                words_array,
                metadata_json
            ))

        self._execute_insert('episodes', data, column_names=[
            'id', 'video_id', 'episode_number', 'start_time', 'end_time',
            'duration', 'transcript', 'word_count', 'words', 'metadata'
        ])

        # Update video statistics
        total_episodes = len(episodes)
        successful_episodes = sum(1 for ep in episodes if not ep.get('incomplete', False))

        self.update_video_status(
            video_id,
            'completed',
            total_episodes=total_episodes,
            successful_episodes=successful_episodes,
            failed_episodes=total_episodes - successful_episodes
        )

    def save_processing_chunk(self, video_id: str, chunk_number: int, start_time: float,
                            end_time: float, cache_key: str, cache_hit: bool = False,
                            processing_time: float = 0, word_count: int = 0):
        """
        Save processing chunk information.

        Args:
            video_id: Video ID
            chunk_number: Chunk number
            start_time: Chunk start time
            end_time: Chunk end time
            cache_key: Cache key used
            cache_hit: Whether this was a cache hit
            processing_time: Time taken to process
            word_count: Number of words transcribed
        """
        chunk_id = str(uuid.uuid4())
        duration = end_time - start_time

        data = [(
            chunk_id,
            video_id,
            chunk_number,
            start_time,
            end_time,
            duration,
            cache_key,
            1 if cache_hit else 0,
            processing_time,
            word_count
        )]

        self._execute_insert('processing_chunks', data, column_names=[
            'id', 'video_id', 'chunk_number', 'start_time', 'end_time',
            'duration', 'cache_key', 'cache_hit', 'processing_time_seconds',
            'transcription_word_count'
        ])

    def get_video_by_id(self, video_id: str) -> Optional[Dict[str, Any]]:
        """
        Get video record by ID.

        Args:
            video_id: Video ID

        Returns:
            Video record dictionary or None
        """
        query = "SELECT * FROM videos WHERE id = %(video_id)s"
        result = self._execute_query(query, parameters={'video_id': video_id})

        if result.result_rows:
            row = result.result_rows[0]
            columns = result.column_names
            video_data = dict(zip(columns, row))

            # Parse metadata JSON
            if video_data.get('metadata'):
                try:
                    video_data['metadata'] = json.loads(video_data['metadata'])
                except json.JSONDecodeError:
                    video_data['metadata'] = {}

            return video_data

        return None

    def get_episodes_for_video(self, video_id: str) -> List[Dict[str, Any]]:
        """
        Get all episodes for a video.

        Args:
            video_id: Video ID

        Returns:
            List of episode dictionaries
        """
        query = """
        SELECT * FROM episodes
        WHERE video_id = %(video_id)s
        ORDER BY episode_number
        """

        result = self._execute_query(query, parameters={'video_id': video_id})
        episodes = []

        for row in result.result_rows:
            columns = result.column_names
            episode_data = dict(zip(columns, row))

            # Parse metadata JSON
            if episode_data.get('metadata'):
                try:
                    episode_data['metadata'] = json.loads(episode_data['metadata'])
                except json.JSONDecodeError:
                    episode_data['metadata'] = {}

            episodes.append(episode_data)

        return episodes

    def update_episode_metadata(self, episode_id: str, metadata: Dict[str, Any]):
        """
        Update episode metadata.

        Args:
            episode_id: Episode ID
            metadata: New metadata dictionary
        """
        metadata_json = json.dumps(metadata)

        query = f"""
        ALTER TABLE episodes UPDATE
            metadata = '{metadata_json}',
            updated_at = now()
        WHERE id = '{episode_id}'
        """

        self._execute_command(query)

    def search_episodes_by_transcript(self, search_text: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Search episodes by transcript content.

        Args:
            search_text: Text to search for
            limit: Maximum number of results

        Returns:
            List of matching episodes with video info
        """
        query = """
        SELECT
            e.id as episode_id,
            e.episode_number,
            e.transcript,
            e.start_time,
            e.end_time,
            e.duration,
            v.filename,
            v.id as video_id
        FROM episodes e
        JOIN videos v ON e.video_id = v.id
        WHERE positionCaseInsensitive(e.transcript, %(search_text)s) > 0
        ORDER BY e.created_at DESC
        LIMIT %(limit)s
        """

        result = self._execute_query(query, parameters={
            'search_text': search_text,
            'limit': limit
        })

        episodes = []
        for row in result.result_rows:
            columns = result.column_names
            episodes.append(dict(zip(columns, row)))

        return episodes

    def get_analytics_summary(self) -> Dict[str, Any]:
        """
        Get analytics summary for dashboard.

        Returns:
            Dictionary with analytics data
        """
        # Get video counts and basic stats
        video_query = """
        SELECT
            count() as total_videos,
            avg(duration_seconds) as avg_video_duration,
            sumIf(1, processing_status = 'completed') as completed_videos,
            sumIf(1, processing_status = 'pending') as pending_videos,
            sumIf(1, processing_status = 'processing') as processing_videos,
            sumIf(1, processing_status = 'failed') as failed_videos,
            sumIf(1, processing_status = 'unprocessed') as unprocessed_videos
        FROM videos
        """

        # Get episode counts based on classification metadata
        episode_query = """
        SELECT
            count() as total_episodes,
            sumIf(1, JSONExtractString(metadata, 'annotation', 'status') = 'success') as successful_episodes,
            sumIf(1, JSONExtractString(metadata, 'annotation', 'status') = 'failure') as failed_episodes,
            sumIf(1, JSONExtractString(metadata, 'annotation', 'status') = 'not_classified') as not_classified_episodes
        FROM episodes
        """

        video_result = self._execute_query(video_query)
        episode_result = self._execute_query(episode_query)

        analytics = {}

        if video_result.result_rows:
            video_columns = video_result.column_names
            analytics.update(dict(zip(video_columns, video_result.result_rows[0])))

        if episode_result.result_rows:
            episode_columns = episode_result.column_names
            analytics.update(dict(zip(episode_columns, episode_result.result_rows[0])))

        return analytics

    def get_episode_analytics(self) -> Dict[str, Any]:
        """
        Get episode-level analytics.

        Returns:
            Dictionary with episode analytics
        """
        query = """
        SELECT
            count() as total_episodes,
            sumIf(1, JSONExtractString(metadata, 'annotation', 'status') = 'success') as complete_episodes,
            sumIf(1, JSONExtractString(metadata, 'annotation', 'status') = 'failure') as incomplete_episodes,
            avg(duration) as avg_episode_duration,
            quantile(0.5)(duration) as median_episode_duration,
            avg(word_count) as avg_word_count,
            sum(word_count) as total_words
        FROM episodes
        """

        result = self._execute_query(query)
        if result.result_rows:
            columns = result.column_names
            return dict(zip(columns, result.result_rows[0]))

        return {}

    def close(self):
        """Close the database connection."""
        if hasattr(self.client, 'close'):
            self.client.close()


# Example usage and testing
if __name__ == "__main__":
    # Initialize database
    db = ClickHouseVideoDatabase()

    # Create a video record
    video_id = db.create_video_record(
        video_path="/path/to/video.mp4",
        file_size=1024000,
        duration=3600.0,
        chunk_length=15,
        metadata={
            "resolution": "1080p",
            "fps": 30,
            "codec": "h264",
            "tags": ["important", "demo"]
        }
    )

    print(f"Created video: {video_id}")

    # Example episodes data
    episodes_data = [
        {
            "episode_number": 1,
            "start_time": 45.2,
            "end_time": 128.7,
            "duration": 83.5,
            "transcript": "start this is the first episode content finish",
            "word_count": 9,
            "words": [
                {"word": "start", "start": 45.2, "end": 45.6},
                {"word": "this", "start": 45.7, "end": 45.9},
                {"word": "is", "start": 46.0, "end": 46.1}
            ],
            "metadata": {
                "quality": "high",
                "manual_review": False
            }
        }
    ]

    # Save episodes
    db.save_episodes(video_id, episodes_data)

    # Get analytics
    summary = db.get_analytics_summary()
    print("Analytics:", summary)