import asyncio
import json
import os
import sys
from typing import Dict, List, Any, Optional
from database.clickhouse_client import ClickHouseVideoDatabase
sys.path.append(os.path.join(os.path.dirname(__file__), '../processing/video'))
from video_transcribe import VideoTranscriber

class VideoService:
    def __init__(self, db: ClickHouseVideoDatabase):
        self.db = db

    async def get_videos(self, skip: int = 0, limit: int = 100, include_unprocessed: bool = False) -> Dict[str, Any]:
        """Get videos with pagination"""
        # Simple query - just get videos without episode aggregations
        query = f"""
        SELECT
            id,
            filename,
            file_path,
            file_size,
            duration_seconds,
            chunk_length_seconds,
            total_chunks,
            processing_status,
            created_at,
            updated_at,
            processing_started_at,
            processing_completed_at,
            metadata,
            file_hash
        FROM videos
        ORDER BY created_at DESC
        LIMIT {limit} OFFSET {skip}
        """
        result = await asyncio.to_thread(self.db._execute_query, query)

        videos = []
        for row in result.result_rows:
            video_data = dict(zip(result.column_names, row))
            if video_data.get('metadata'):
                try:
                    video_data['metadata'] = json.loads(video_data['metadata'])
                except json.JSONDecodeError:
                    video_data['metadata'] = {}
            # Mark videos as processed/unprocessed based on their status
            video_data['is_processed'] = video_data['processing_status'] not in ['unprocessed', 'pending']
            videos.append(video_data)

        response_data = {"videos": videos, "total": len(videos)}

        # Optionally include unprocessed videos from file system (placeholder)
        if include_unprocessed:
            response_data["unprocessed_videos"] = []
            response_data["unprocessed_count"] = 0

        return response_data

    async def get_unprocessed_videos(self) -> Dict[str, Any]:
        """Get unprocessed videos from file system (placeholder)"""
        return {"unprocessed_videos": []}

    async def start_processing(self, filename: str, chunk_length: int = 15, max_chunks: Optional[int] = None) -> Dict[str, Any]:
        """Start video processing"""
        try:
            # Find the video record by filename
            query = "SELECT id, file_path, processing_status FROM videos WHERE filename = %(filename)s LIMIT 1"
            result = await asyncio.to_thread(self.db._execute_query, query, {"filename": filename})

            if not result.result_rows:
                return {"error": f"Video not found: {filename}"}

            video_data = dict(zip(result.column_names, result.result_rows[0]))
            video_id = video_data['id']
            video_path = video_data['file_path']
            current_status = video_data['processing_status']

            # Check if video is already processing (but allow reprocessing of completed or failed videos)
            if current_status == 'processing':
                return {"message": f"Video {filename} is already processing"}

            # Check if file exists
            if not os.path.exists(video_path):
                return {"error": f"Video file not found at path: {video_path}"}

            # Start background processing
            asyncio.create_task(self._process_video_background(video_id, video_path, chunk_length, max_chunks, filename))

            return {
                "message": f"Processing started for {filename}",
                "video_id": video_id,
                "chunk_length": chunk_length,
                "max_chunks": max_chunks
            }

        except Exception as e:
            return {"error": f"Failed to start processing: {str(e)}"}

    async def _process_video_background(self, video_id: str, video_path: str, chunk_length: int, max_chunks: Optional[int], filename: str) -> None:
        """Process video in background"""
        try:
            print(f"Starting background processing for video {filename} (ID: {video_id})")

            # Update status to processing
            await asyncio.to_thread(self.db.update_video_status, video_id, 'processing')
            print(f"Updated video status to 'processing' for {filename}")

            # OpenAI API key is hardcoded in transcriber initialization

            # Initialize transcriber
            print(f"Initializing VideoTranscriber for {filename}")
            transcriber = VideoTranscriber(
                api_key=os.getenv("OPENAI_API_KEY"),
                chunk_length_seconds=chunk_length,
                db_client=self.db
            )

            # Get video metadata
            video_metadata = {
                "source": "user_upload",
                "processing_parameters": {
                    "chunk_length": chunk_length,
                    "max_chunks": max_chunks
                }
            }

            # Transcribe video in chunks
            _, chunk_results = await asyncio.to_thread(
                transcriber.transcribe_video_chunked,
                video_path,
                save_to_db=False,  # We already have the video record
                max_chunks=max_chunks,
                video_metadata=video_metadata
            )

            # Extract episodes from chunks
            episodes = await asyncio.to_thread(
                transcriber.extract_episodes_from_chunks,
                chunk_results,
                start_word="start",
                end_word="finish",
                save_to_db=True,
                video_id=video_id
            )

            # Update status to completed
            await asyncio.to_thread(self.db.update_video_status, video_id, 'completed', total_chunks=len(chunk_results))

            print(f"Successfully processed {filename}: {len(episodes)} episodes extracted")

        except Exception as e:
            print(f"Error processing video {filename}: {str(e)}")
            # Update status to failed
            try:
                await asyncio.to_thread(self.db.update_video_status, video_id, 'failed')
            except:
                pass