import asyncio
import json
import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime
import clickhouse_connect
from clickhouse_connect.driver.exceptions import DatabaseError
import threading
import time


class ClickHouseConnectionPool:
    """Connection pool for ClickHouse clients."""

    def __init__(self, host: str, port: int, database: str, username: str, password: str,
                 pool_size: int = 10, max_lifetime: int = 3600, query_timeout: int = 30):
        """
        Initialize connection pool.

        Args:
            host: ClickHouse server host
            port: ClickHouse HTTP port
            database: Database name
            username: Username
            password: Password
            pool_size: Maximum number of connections in pool
            max_lifetime: Maximum lifetime of a connection in seconds
            query_timeout: Query timeout in seconds
        """
        self.host = host
        self.port = port
        self.database = database
        self.username = username
        self.password = password
        self.pool_size = pool_size
        self.max_lifetime = max_lifetime
        self.query_timeout = query_timeout

        self._pool = []
        self._lock = threading.RLock()
        self._created_connections = 0

    def _create_connection(self):
        """Create a new ClickHouse connection with timeout settings."""
        return {
            'client': clickhouse_connect.get_client(
                host=self.host,
                port=self.port,
                database=self.database,
                username=self.username,
                password=self.password,
                connect_timeout=10,
                send_receive_timeout=self.query_timeout,
                settings={
                    'max_execution_time': self.query_timeout,
                    'max_query_size': 50000000,  # 50MB max query size
                    'query_profiler_real_time_period_ns': 0,  # Disable profiler for performance
                    'readonly': 0
                }
            ),
            'created_at': time.time(),
            'in_use': False
        }

    def get_connection(self):
        """Get a connection from the pool."""
        with self._lock:
            # Try to find an available connection
            for conn in self._pool:
                if not conn['in_use']:
                    # Check if connection is still valid (not too old)
                    if time.time() - conn['created_at'] < self.max_lifetime:
                        conn['in_use'] = True
                        return conn
                    else:
                        # Remove expired connection
                        self._pool.remove(conn)
                        try:
                            conn['client'].close()
                        except:
                            pass

            # Create new connection if pool has space
            if len(self._pool) < self.pool_size:
                conn = self._create_connection()
                conn['in_use'] = True
                self._pool.append(conn)
                self._created_connections += 1
                return conn

            # Pool is full, wait for a connection to be released
            # For simplicity, create a temporary connection
            return self._create_connection()

    def return_connection(self, conn):
        """Return a connection to the pool."""
        with self._lock:
            if conn in self._pool:
                conn['in_use'] = False
            else:
                # This was a temporary connection, close it
                try:
                    conn['client'].close()
                except:
                    pass

    def close_all(self):
        """Close all connections in the pool."""
        with self._lock:
            for conn in self._pool:
                try:
                    conn['client'].close()
                except:
                    pass
            self._pool.clear()

    def get_stats(self):
        """Get pool statistics."""
        with self._lock:
            in_use = sum(1 for conn in self._pool if conn['in_use'])
            return {
                'pool_size': len(self._pool),
                'in_use': in_use,
                'available': len(self._pool) - in_use,
                'max_pool_size': self.pool_size,
                'total_created': self._created_connections
            }


class ClickHouseVideoDatabase:
    """
    ClickHouse database client for video episode processing.
    Handles videos, episodes, and processing chunks with configurable metadata.
    Now uses connection pooling for better performance under concurrent load.
    """

    def __init__(self, host: str = 'localhost', port: int = 8123, database: str = 'video_episodes',
                 username: str = 'default', password: str = '', pool_size: int = 10):
        """
        Initialize ClickHouse client with connection pooling.

        Args:
            host: ClickHouse server host
            port: ClickHouse HTTP port
            database: Database name
            username: Username
            password: Password
            pool_size: Maximum number of connections in pool
        """
        self.host = host
        self.port = port
        self.database = database
        self.username = username
        self.password = password

        # Initialize connection pool
        self._pool = ClickHouseConnectionPool(
            host=host, port=port, database=database,
            username=username, password=password, pool_size=pool_size
        )

    def _get_client(self):
        """Get a ClickHouse client from the connection pool."""
        return self._pool.get_connection()

    @property
    def client(self):
        """Maintain backward compatibility for direct client access."""
        # Note: This breaks pooling but maintains compatibility
        conn = self._get_client()
        return conn['client']

    def _execute_query(self, query: str, parameters: Dict[str, Any] = None):
        """Execute a query using a pooled connection with timeout handling."""
        conn = self._get_client()
        try:
            result = conn['client'].query(query, parameters=parameters)
            return result
        except Exception as e:
            # Log the error and re-raise
            print(f"Query execution failed: {e}")
            print(f"Query: {query}")
            print(f"Parameters: {parameters}")
            raise e
        finally:
            self._pool.return_connection(conn)

    def _execute_command(self, command: str):
        """Execute a command using a pooled connection with timeout handling."""
        conn = self._get_client()
        try:
            result = conn['client'].command(command)
            return result
        except Exception as e:
            # Log the error and re-raise
            print(f"Command execution failed: {e}")
            print(f"Command: {command}")
            raise e
        finally:
            self._pool.return_connection(conn)

    def _execute_insert(self, table: str, data: list, column_names: list):
        """Execute an insert using a pooled connection with timeout handling."""
        conn = self._get_client()
        try:
            result = conn['client'].insert(table, data, column_names=column_names)
            return result
        except Exception as e:
            # Log the error and re-raise
            print(f"Insert execution failed: {e}")
            print(f"Table: {table}")
            print(f"Data length: {len(data) if data else 0}")
            raise e
        finally:
            self._pool.return_connection(conn)

    def get_pool_stats(self):
        """Get connection pool statistics."""
        return self._pool.get_stats()

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

        if not result.result_rows:
            return []

        # Get column names once, outside the loop
        columns = result.column_names
        metadata_col_idx = None

        # Find metadata column index for faster access
        try:
            metadata_col_idx = columns.index('metadata')
        except ValueError:
            pass  # No metadata column

        episodes = []
        for row in result.result_rows:
            episode_data = dict(zip(columns, row))

            # Parse metadata JSON only if metadata column exists and has data
            if metadata_col_idx is not None and row[metadata_col_idx]:
                try:
                    episode_data['metadata'] = json.loads(row[metadata_col_idx])
                except (json.JSONDecodeError, TypeError):
                    episode_data['metadata'] = {}
            elif metadata_col_idx is not None:
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

    def update_episode_annotation(self, episode_id: str, annotation_data: Dict[str, Any]):
        """
        Update episode annotation in metadata.

        Args:
            episode_id: Episode ID
            annotation_data: Annotation data to update
        """
        # Get current metadata first
        query = "SELECT metadata FROM episodes WHERE id = %(episode_id)s"
        result = self._execute_query(query, parameters={'episode_id': episode_id})

        if not result.result_rows:
            raise ValueError(f"Episode {episode_id} not found")

        current_metadata = result.result_rows[0][0] or "{}"

        # Parse current metadata
        try:
            metadata = json.loads(current_metadata) if current_metadata else {}
        except json.JSONDecodeError:
            metadata = {}

        # Update annotation section
        if 'annotation' not in metadata:
            metadata['annotation'] = {}

        metadata['annotation'].update(annotation_data)
        metadata_json = json.dumps(metadata)

        # Update the record
        query = f"""
        ALTER TABLE episodes UPDATE
            metadata = '{metadata_json}',
            updated_at = now()
        WHERE id = '{episode_id}'
        """

        self._execute_command(query)

    def update_episode_captions(self, episode_id: str, captions: str):
        """
        Update episode captions.

        Args:
            episode_id: Episode ID
            captions: Caption text
        """
        # Escape single quotes in captions for SQL safety
        captions_escaped = captions.replace("'", "\\'")

        query = f"""
        ALTER TABLE episodes UPDATE
            captions = '{captions_escaped}',
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
        """Close all database connections in the pool."""
        self._pool.close_all()


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