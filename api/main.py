from fastapi import FastAPI, HTTPException, UploadFile, File, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Any, Optional
import os
import sys
from datetime import datetime, timedelta
import json
import glob
from pathlib import Path
import asyncio
import threading
import subprocess
from concurrent.futures import ThreadPoolExecutor
import time
import hashlib
from collections import OrderedDict
import io

# Add database module to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'database'))
sys.path.append(os.path.join(os.path.dirname(__file__), 'processing', 'video'))

from clickhouse_client import ClickHouseVideoDatabase
from video_transcribe import VideoTranscriber

app = FastAPI(title="Video Transcription API", version="1.0.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001", "http://127.0.0.1:3000", "http://127.0.0.1:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

class VideoCache:
    """
    Intelligent video cache for episode segments with pre-loading and memory management.
    """

    def __init__(self, max_size_mb: int = 100, max_age_minutes: int = 30):
        self.cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self.max_size_bytes = max_size_mb * 1024 * 1024  # Convert to bytes
        self.max_age_seconds = max_age_minutes * 60
        self.current_size_bytes = 0
        self.preload_tasks: Dict[str, asyncio.Task] = {}
        self.lock = threading.Lock()

    def _get_cache_key(self, episode_id: str) -> str:
        """Generate cache key for episode."""
        return f"episode_{episode_id}"

    def _cleanup_expired(self):
        """Remove expired cache entries."""
        current_time = time.time()
        expired_keys = []

        for key, entry in self.cache.items():
            if current_time - entry['timestamp'] > self.max_age_seconds:
                expired_keys.append(key)

        for key in expired_keys:
            self._remove_entry(key)

    def _remove_entry(self, key: str):
        """Remove a single cache entry."""
        if key in self.cache:
            entry = self.cache.pop(key)
            self.current_size_bytes -= entry['size']
            print(f"Cache: Removed {key}, freed {entry['size']} bytes")

    def _ensure_space(self, needed_bytes: int):
        """Ensure enough space by removing LRU entries."""
        while (self.current_size_bytes + needed_bytes > self.max_size_bytes
               and len(self.cache) > 0):
            # Remove least recently used (first item in OrderedDict)
            oldest_key = next(iter(self.cache))
            self._remove_entry(oldest_key)

    def get(self, episode_id: str) -> Optional[bytes]:
        """Get cached video data for episode."""
        with self.lock:
            key = self._get_cache_key(episode_id)
            if key in self.cache:
                # Move to end (mark as recently used)
                entry = self.cache.pop(key)
                entry['timestamp'] = time.time()  # Update access time
                self.cache[key] = entry
                print(f"Cache: HIT for {episode_id}")
                return entry['data']

            print(f"Cache: MISS for {episode_id}")
            return None

    def put(self, episode_id: str, data: bytes):
        """Store video data in cache."""
        with self.lock:
            key = self._get_cache_key(episode_id)
            data_size = len(data)

            # Cleanup expired entries first
            self._cleanup_expired()

            # Ensure we have enough space
            self._ensure_space(data_size)

            # Store the data
            self.cache[key] = {
                'data': data,
                'size': data_size,
                'timestamp': time.time()
            }
            self.current_size_bytes += data_size

            print(f"Cache: Stored {episode_id}, size: {data_size} bytes, total: {self.current_size_bytes}")

    def preload_episode(self, episode_id: str, video_path: str, start_time: float, end_time: float):
        """Start preloading an episode in the background."""
        if episode_id in self.preload_tasks:
            return  # Already preloading

        key = self._get_cache_key(episode_id)
        if key in self.cache:
            return  # Already cached

        print(f"Cache: Starting preload for {episode_id}")
        task = asyncio.create_task(self._preload_worker(episode_id, video_path, start_time, end_time))
        self.preload_tasks[episode_id] = task

    async def _preload_worker(self, episode_id: str, video_path: str, start_time: float, end_time: float):
        """Background worker to preload video segment."""
        try:
            # Generate the video segment
            data = await self._generate_video_segment(video_path, start_time, end_time)
            if data:
                self.put(episode_id, data)
                print(f"Cache: Preload completed for {episode_id}")
        except Exception as e:
            print(f"Cache: Preload failed for {episode_id}: {e}")
        finally:
            # Clean up task reference
            if episode_id in self.preload_tasks:
                del self.preload_tasks[episode_id]

    async def _generate_video_segment(self, video_path: str, start_time: float, end_time: float) -> Optional[bytes]:
        """Generate video segment data."""
        duration = end_time - start_time

        cmd = [
            'ffmpeg',
            '-ss', str(start_time),
            '-i', video_path,
            '-t', str(duration),
            '-vf', 'scale=854:480',
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-crf', '28',
            '-c:a', 'aac',
            '-ar', '44100',
            '-ac', '2',
            '-movflags', 'frag_keyframe+empty_moov+faststart',
            '-f', 'mp4',
            'pipe:1'
        ]

        try:
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = process.communicate()

            if process.returncode == 0:
                return stdout
            else:
                print(f"FFmpeg error: {stderr.decode()}")
                return None
        except Exception as e:
            print(f"Video generation error: {e}")
            return None

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self.lock:
            return {
                'entries': len(self.cache),
                'size_mb': round(self.current_size_bytes / (1024 * 1024), 2),
                'max_size_mb': round(self.max_size_bytes / (1024 * 1024), 2),
                'preload_tasks': len(self.preload_tasks),
                'cache_keys': list(self.cache.keys())
            }

# Database instance
db = ClickHouseVideoDatabase()

# Video cache instance
video_cache = VideoCache(max_size_mb=100, max_age_minutes=30)

# Transcriber instance
transcriber = VideoTranscriber(api_key=os.getenv("OPENAI_API_KEY"), db_client=db)

# Thread pool for background processing
executor = ThreadPoolExecutor(max_workers=2)

# Helper functions for data folder management
def get_data_folder_path():
    """Get the absolute path to the data folder."""
    return os.path.join(os.path.dirname(__file__), "data")

def scan_data_folder_for_videos():
    """
    Scan the data folder for video files and return list of unprocessed videos.

    Returns:
        List of dictionaries with video file information
    """
    data_folder = get_data_folder_path()
    if not os.path.exists(data_folder):
        return []

    video_extensions = {'.mp4', '.avi', '.mov', '.mkv', '.webm', '.m4v', '.flv'}
    video_files = []

    # Get all video files in data folder
    for extension in video_extensions:
        pattern = os.path.join(data_folder, f"*{extension}")
        video_files.extend(glob.glob(pattern, recursive=False))
        pattern = os.path.join(data_folder, f"*{extension.upper()}")
        video_files.extend(glob.glob(pattern, recursive=False))

    # Get already processed videos from database
    processed_files = set()
    try:
        query = "SELECT file_path FROM videos"
        result = db._execute_query(query)
        processed_files = {row[0] for row in result.result_rows}
    except Exception:
        pass

    # Filter out already processed videos
    unprocessed_videos = []
    for video_path in video_files:
        if video_path not in processed_files:
            try:
                file_stat = os.stat(video_path)
                video_info = {
                    "file_path": video_path,
                    "filename": os.path.basename(video_path),
                    "file_size": file_stat.st_size,
                    "modified_time": datetime.fromtimestamp(file_stat.st_mtime).isoformat(),
                    "is_processed": False
                }
                unprocessed_videos.append(video_info)
            except OSError:
                continue

    return unprocessed_videos

def process_video_background(video_id: str, file_path: str, chunk_length: int, max_chunks: Optional[int], metadata: Dict[str, Any]):
    """
    Background function to process video. This runs in a separate thread.
    """
    try:
        print(f"Starting background processing for video {video_id}")

        # Update status to processing
        db.update_video_status(video_id, 'processing')

        # Delete the existing record so transcriber can create a fresh one
        db._execute_command(f"DELETE FROM videos WHERE id = '{video_id}'")

        # Process video (transcriber will create a new video record)
        processed_video_id, chunk_results = transcriber.transcribe_video_chunked(
            file_path,
            max_chunks=max_chunks,
            video_metadata=metadata
        )

        # Extract episodes from the transcription chunks
        episodes = transcriber.extract_episodes_from_chunks(
            chunk_results,
            save_to_db=True,
            video_id=processed_video_id
        )

        print(f"Completed processing for video {video_id} -> {processed_video_id}, {len(episodes)} episodes")

    except Exception as e:
        print(f"Error processing video {video_id}: {str(e)}")
        # Update status to failed if something goes wrong
        try:
            db.update_video_status(video_id, 'failed', error_message=str(e))
        except:
            pass

@app.get("/", response_class=HTMLResponse)
async def root():
    # Serve the main web interface
    with open("static/index.html", "r") as f:
        return HTMLResponse(f.read())

@app.get("/api")
async def api_root():
    return {"message": "Video Transcription API", "version": "1.0.0"}

# Video Management APIs
@app.get("/api/videos")
async def list_videos(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    include_unprocessed: bool = Query(False, description="Include unprocessed videos from data folder")
):
    try:
        query = f"""
        SELECT * FROM videos
        ORDER BY created_at DESC
        LIMIT {limit} OFFSET {skip}
        """
        result = db._execute_query(query)

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

            # Calculate classification-based counts for each video
            video_id = video_data['id']
            episode_counts_query = """
            SELECT
                count() as total_episodes,
                sumIf(1, JSONExtractString(metadata, 'annotation', 'status') = 'success') as successful_episodes,
                sumIf(1, JSONExtractString(metadata, 'annotation', 'status') = 'failure') as failed_episodes,
                sumIf(1, JSONExtractString(metadata, 'annotation', 'status') = 'not_classified') as not_classified_episodes
            FROM episodes
            WHERE video_id = %(video_id)s
            """

            episode_result = db._execute_query(episode_counts_query, parameters={'video_id': video_id})
            if episode_result.result_rows:
                episode_counts = dict(zip(episode_result.column_names, episode_result.result_rows[0]))
                video_data.update(episode_counts)

            videos.append(video_data)

        response_data = {"videos": videos, "total": len(videos)}

        # Optionally include unprocessed videos from file system (only those not in DB)
        if include_unprocessed:
            # Get file paths already in database
            db_file_paths = {video['file_path'] for video in videos}

            # Get unprocessed videos from file system
            file_unprocessed_videos = scan_data_folder_for_videos()

            # Filter out videos that are already in the database
            unprocessed_videos = [
                video for video in file_unprocessed_videos
                if video['file_path'] not in db_file_paths
            ]

            response_data["unprocessed_videos"] = unprocessed_videos
            response_data["unprocessed_count"] = len(unprocessed_videos)

        return response_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/videos/unprocessed")
async def list_unprocessed_videos():
    """
    Get list of video files in data folder that haven't been processed yet.
    """
    try:
        unprocessed_videos = scan_data_folder_for_videos()
        return {
            "unprocessed_videos": unprocessed_videos,
            "count": len(unprocessed_videos),
            "data_folder": get_data_folder_path()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/videos/process-from-data")
async def process_video_from_data(
    filename: str = Query(..., description="Filename of video in data folder"),
    chunk_length: int = Query(15, ge=5, le=300),
    max_chunks: Optional[int] = Query(None, ge=1),
    metadata: Optional[str] = Query(None)
):
    """
    Process a video file that exists in the data folder.
    """
    try:
        data_folder = get_data_folder_path()
        file_path = os.path.join(data_folder, filename)

        # Verify file exists and is a video file
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="Video file not found in data folder")

        video_extensions = {'.mp4', '.avi', '.mov', '.mkv', '.webm', '.m4v', '.flv'}
        file_extension = Path(file_path).suffix.lower()
        if file_extension not in video_extensions:
            raise HTTPException(status_code=400, detail="File is not a supported video format")

        # Parse metadata first
        custom_metadata = {}
        if metadata:
            try:
                custom_metadata = json.loads(metadata)
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid metadata JSON")

        # Add source information to metadata
        custom_metadata["source"] = "data_folder"
        custom_metadata["original_location"] = file_path

        # Check if already processed (only block if it's actually completed processing)
        query = "SELECT id, processing_status FROM videos WHERE file_path = %(file_path)s"
        result = db._execute_query(query, parameters={'file_path': file_path})
        if result.result_rows:
            existing_video_id, processing_status = result.result_rows[0]
            if processing_status not in ['unprocessed', 'pending', 'failed']:
                raise HTTPException(
                    status_code=409,
                    detail=f"Video already processed. Video ID: {existing_video_id}, Status: {processing_status}"
                )
            # Delete the existing record so transcriber can create a fresh one
            db._execute_command(f"DELETE FROM videos WHERE id = '{existing_video_id}'")

        # Process video (transcriber will create a new video record)
        video_id, chunk_results = transcriber.transcribe_video_chunked(
            file_path,
            max_chunks=max_chunks,
            video_metadata=custom_metadata
        )

        # Extract episodes from the transcription chunks
        episodes = transcriber.extract_episodes_from_chunks(
            chunk_results,
            save_to_db=True,
            video_id=video_id
        )

        return {
            "video_id": video_id,
            "episodes_count": len(episodes),
            "filename": filename,
            "file_path": file_path,
            "message": "Video from data folder processed successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")

@app.post("/api/videos/process-all-unprocessed")
async def process_all_unprocessed_videos(
    chunk_length: int = Query(15, ge=5, le=300),
    max_chunks: Optional[int] = Query(None, ge=1),
    metadata: Optional[str] = Query(None)
):
    """
    Process all unprocessed video files in the data folder.
    """
    try:
        unprocessed_videos = scan_data_folder_for_videos()

        if not unprocessed_videos:
            return {
                "message": "No unprocessed videos found in data folder",
                "processed_videos": [],
                "total_processed": 0
            }

        # Parse metadata
        custom_metadata = {}
        if metadata:
            try:
                custom_metadata = json.loads(metadata)
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid metadata JSON")

        processed_videos = []
        failed_videos = []

        for video_info in unprocessed_videos:
            try:
                # Add source information to metadata for each video
                video_metadata = custom_metadata.copy()
                video_metadata["source"] = "data_folder"
                video_metadata["original_location"] = video_info["file_path"]
                video_metadata["batch_processed"] = True

                # Process video
                video_id, chunk_results = transcriber.transcribe_video_chunked(
                    video_info["file_path"],
                    chunk_length_seconds=chunk_length,
                    max_chunks=max_chunks,
                    metadata=video_metadata
                )

                # Extract episodes from the transcription chunks
                episodes = transcriber.extract_episodes_from_chunks(
                    chunk_results,
                    save_to_db=True,
                    video_id=video_id
                )

                processed_videos.append({
                    "video_id": video_id,
                    "filename": video_info["filename"],
                    "episodes_count": len(episodes),
                    "file_path": video_info["file_path"]
                })

            except Exception as e:
                failed_videos.append({
                    "filename": video_info["filename"],
                    "file_path": video_info["file_path"],
                    "error": str(e)
                })

        return {
            "message": f"Batch processing completed. {len(processed_videos)} videos processed successfully, {len(failed_videos)} failed.",
            "processed_videos": processed_videos,
            "failed_videos": failed_videos,
            "total_processed": len(processed_videos),
            "total_failed": len(failed_videos)
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Batch processing failed: {str(e)}")

@app.post("/api/videos/prepopulate-unprocessed")
async def prepopulate_unprocessed_videos():
    """
    Create database entries for unprocessed videos in the data folder.
    This allows them to appear in the video list with 'unprocessed' status.
    """
    try:
        unprocessed_videos = scan_data_folder_for_videos()

        if not unprocessed_videos:
            return {
                "message": "No unprocessed videos found in data folder",
                "prepopulated_videos": [],
                "total_prepopulated": 0
            }

        prepopulated_videos = []
        failed_videos = []

        for video_info in unprocessed_videos:
            try:
                # Get file size and basic metadata
                file_stats = os.stat(video_info["file_path"])

                # Create database record with 'unprocessed' status
                video_id = db.create_video_record(
                    video_path=video_info["file_path"],
                    file_size=file_stats.st_size,
                    duration=0.0,  # Will be determined during processing
                    chunk_length=15,  # Default chunk length
                    metadata={
                        "source": "data_folder",
                        "prepopulated": True,
                        "original_location": video_info["file_path"]
                    }
                )

                # Update status to 'unprocessed' instead of default 'pending'
                db.update_video_status(video_id, 'unprocessed')

                prepopulated_videos.append({
                    "video_id": video_id,
                    "filename": video_info["filename"],
                    "file_path": video_info["file_path"],
                    "file_size": file_stats.st_size
                })

            except Exception as e:
                failed_videos.append({
                    "filename": video_info["filename"],
                    "file_path": video_info["file_path"],
                    "error": str(e)
                })

        return {
            "message": f"Prepopulated {len(prepopulated_videos)} unprocessed videos in database. {len(failed_videos)} failed.",
            "prepopulated_videos": prepopulated_videos,
            "failed_videos": failed_videos,
            "total_prepopulated": len(prepopulated_videos),
            "total_failed": len(failed_videos)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Prepopulation failed: {str(e)}")

@app.post("/api/videos/start-processing")
async def start_video_processing(
    filename: str = Query(..., description="Filename of video in data folder"),
    chunk_length: int = Query(15, ge=5, le=300),
    max_chunks: Optional[int] = Query(None, ge=1),
    metadata: Optional[str] = Query(None)
):
    """
    Start background processing of a video file from the data folder.
    Returns immediately with processing status, actual processing happens in background.
    """
    try:
        data_folder = get_data_folder_path()
        file_path = os.path.join(data_folder, filename)

        # Verify file exists and is a video file
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="Video file not found in data folder")

        video_extensions = {'.mp4', '.avi', '.mov', '.mkv', '.webm', '.m4v', '.flv'}
        file_extension = Path(file_path).suffix.lower()
        if file_extension not in video_extensions:
            raise HTTPException(status_code=400, detail="File is not a supported video format")

        # Parse metadata first
        custom_metadata = {}
        if metadata:
            try:
                custom_metadata = json.loads(metadata)
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid metadata JSON")

        # Add source information to metadata
        custom_metadata["source"] = "data_folder"
        custom_metadata["original_location"] = file_path

        # Check if video exists in database
        query = "SELECT id, processing_status FROM videos WHERE file_path = %(file_path)s"
        result = db._execute_query(query, parameters={'file_path': file_path})

        if not result.result_rows:
            raise HTTPException(status_code=404, detail="Video not found in database. Please run prepopulation first.")

        video_id, processing_status = result.result_rows[0]

        if processing_status == 'processing':
            raise HTTPException(status_code=409, detail="Video is already being processed")

        if processing_status not in ['unprocessed', 'pending', 'failed']:
            raise HTTPException(
                status_code=409,
                detail=f"Video already processed. Status: {processing_status}"
            )

        # Start background processing
        executor.submit(
            process_video_background,
            video_id,
            file_path,
            chunk_length,
            max_chunks,
            custom_metadata
        )

        return {
            "video_id": video_id,
            "filename": filename,
            "status": "processing_started",
            "message": "Video processing started in background. Check video status for progress."
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start processing: {str(e)}")

@app.get("/api/videos/{video_id}")
async def get_video(video_id: str):
    video = db.get_video_by_id(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    return {"video": video}

@app.post("/api/videos")
async def upload_video(
    file: UploadFile = File(...),
    chunk_length: int = Query(15, ge=5, le=300),
    max_chunks: Optional[int] = Query(None, ge=1),
    metadata: Optional[str] = Query(None)
):
    if not file.filename.lower().endswith(('.mp4', '.avi', '.mov', '.mkv', '.webm')):
        raise HTTPException(status_code=400, detail="Invalid video format")

    # Save uploaded file to data repository
    upload_dir = os.path.join(os.path.dirname(__file__), "data")
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, file.filename)

    with open(file_path, "wb") as buffer:
        content = await file.read()
        buffer.write(content)

    # Parse metadata
    custom_metadata = {}
    if metadata:
        try:
            custom_metadata = json.loads(metadata)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid metadata JSON")

    try:
        # Process video
        video_id, chunk_results = transcriber.transcribe_video_chunked(
            file_path,
            max_chunks=max_chunks,
            video_metadata=custom_metadata
        )

        # Extract episodes from the transcription chunks
        episodes = transcriber.extract_episodes_from_chunks(
            chunk_results,
            save_to_db=True,
            video_id=video_id
        )

        return {
            "video_id": video_id,
            "episodes_count": len(episodes),
            "message": "Video uploaded and processed successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")

@app.put("/api/videos/{video_id}/status")
async def update_video_status(video_id: str, status: str, **kwargs):
    try:
        db.update_video_status(video_id, status, **kwargs)
        return {"message": "Status updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/videos/{video_id}")
async def delete_video(video_id: str):
    try:
        # Delete episodes first
        db._execute_command(f"DELETE FROM episodes WHERE video_id = '{video_id}'")
        # Delete processing chunks
        db._execute_command(f"DELETE FROM processing_chunks WHERE video_id = '{video_id}'")
        # Delete video
        db._execute_command(f"DELETE FROM videos WHERE id = '{video_id}'")

        return {"message": "Video deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Episode Management APIs
@app.get("/api/videos/{video_id}/episodes")
async def get_video_episodes(video_id: str):
    episodes = db.get_episodes_for_video(video_id)
    return {"episodes": episodes}

@app.get("/api/episodes/{episode_id}")
async def get_episode(episode_id: str):
    try:
        query = "SELECT * FROM episodes WHERE id = %(episode_id)s"
        result = db._execute_query(query, parameters={'episode_id': episode_id})

        if not result.result_rows:
            raise HTTPException(status_code=404, detail="Episode not found")

        episode_data = dict(zip(result.column_names, result.result_rows[0]))
        if episode_data.get('metadata'):
            try:
                episode_data['metadata'] = json.loads(episode_data['metadata'])
            except json.JSONDecodeError:
                episode_data['metadata'] = {}

        return {"episode": episode_data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/episodes/{episode_id}/metadata")
async def update_episode_metadata(episode_id: str, metadata: Dict[str, Any]):
    try:
        db.update_episode_metadata(episode_id, metadata)
        return {"message": "Metadata updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/episodes/{episode_id}/annotation")
async def annotate_episode(episode_id: str, annotation: Dict[str, Any]):
    try:
        # Get current episode metadata
        query = "SELECT metadata FROM episodes WHERE id = %(episode_id)s"
        result = db._execute_query(query, parameters={'episode_id': episode_id})

        if not result.result_rows:
            raise HTTPException(status_code=404, detail="Episode not found")

        current_metadata_str = result.result_rows[0][0] or '{}'
        try:
            current_metadata = json.loads(current_metadata_str)
        except json.JSONDecodeError:
            current_metadata = {}

        # Add annotation to metadata
        current_metadata.update({
            "annotation": annotation,
            "annotated_at": datetime.now().isoformat(),
        })

        db.update_episode_metadata(episode_id, current_metadata)
        return {"message": "Episode annotated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/episodes/{episode_id}/mark-success")
async def mark_episode_success(episode_id: str):
    """Mark an episode as successful."""
    try:
        annotation = {
            "status": "success",
            "quality": "high",
            "notes": "Manually marked as success"
        }
        return await annotate_episode(episode_id, annotation)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/episodes/{episode_id}/mark-failure")
async def mark_episode_failure(episode_id: str):
    """Mark an episode as failure."""
    try:
        annotation = {
            "status": "failure",
            "quality": "low",
            "notes": "Manually marked as failure"
        }
        return await annotate_episode(episode_id, annotation)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/episodes/{episode_id}/captions")
async def update_episode_captions(episode_id: str, captions_data: Dict[str, str]):
    try:
        captions = captions_data.get("captions", "").strip()

        # Update the episode captions
        query = f"""
        ALTER TABLE episodes UPDATE
            captions = %(captions)s,
            updated_at = now()
        WHERE id = %(episode_id)s
        """

        db._execute_command(query % {
            'captions': f"'{captions.replace("'", "''")}'",
            'episode_id': f"'{episode_id}'"
        })

        return {"message": "Captions updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/episodes/search")
async def search_episodes(q: str = Query(..., min_length=1), limit: int = Query(100, ge=1, le=1000)):
    try:
        episodes = db.search_episodes_by_transcript(q, limit)
        return {"episodes": episodes, "query": q}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Analytics APIs
@app.get("/api/analytics/summary")
async def get_analytics_summary():
    try:
        analytics = db.get_analytics_summary()
        return {"analytics": analytics}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/analytics/episodes")
async def get_episode_analytics():
    try:
        analytics = db.get_episode_analytics()
        return {"analytics": analytics}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/analytics/processing")
async def get_processing_analytics():
    try:
        query = """
        SELECT
            count() as total_chunks,
            sumIf(1, cache_hit = 1) as cache_hits,
            sumIf(1, cache_hit = 0) as cache_misses,
            avg(processing_time_seconds) as avg_processing_time,
            sum(processing_time_seconds) as total_processing_time,
            avg(transcription_word_count) as avg_words_per_chunk
        FROM processing_chunks
        """

        result = db._execute_query(query)
        if result.result_rows:
            analytics = dict(zip(result.column_names, result.result_rows[0]))
            return {"analytics": analytics}

        return {"analytics": {}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/videos/{video_id}/analytics")
async def get_video_analytics(video_id: str):
    try:
        # Video-specific analytics
        query = """
        SELECT
            v.processing_status,
            v.total_episodes,
            v.successful_episodes,
            v.failed_episodes,
            v.duration_seconds,
            count(pc.id) as processing_chunks,
            sum(pc.processing_time_seconds) as total_processing_time,
            sumIf(1, pc.cache_hit = 1) as cache_hits
        FROM videos v
        LEFT JOIN processing_chunks pc ON v.id = pc.video_id
        WHERE v.id = %(video_id)s
        GROUP BY v.id, v.processing_status, v.total_episodes,
                 v.successful_episodes, v.failed_episodes, v.duration_seconds
        """

        result = db._execute_query(query, parameters={'video_id': video_id})
        if result.result_rows:
            analytics = dict(zip(result.column_names, result.result_rows[0]))
            return {"analytics": analytics}

        raise HTTPException(status_code=404, detail="Video not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Processing APIs
@app.post("/api/videos/{video_id}/reprocess")
async def reprocess_video(
    video_id: str,
    chunk_length: int = Query(15, ge=5, le=300),
    max_chunks: Optional[int] = Query(None, ge=1)
):
    try:
        video = db.get_video_by_id(video_id)
        if not video:
            raise HTTPException(status_code=404, detail="Video not found")

        # Clear existing episodes and chunks
        db._execute_command(f"DELETE FROM episodes WHERE video_id = '{video_id}'")
        db._execute_command(f"DELETE FROM processing_chunks WHERE video_id = '{video_id}'")

        # Reprocess
        video_id, chunk_results = transcriber.transcribe_video_chunked(
            video['file_path'],
            chunk_length_seconds=chunk_length,
            max_chunks=max_chunks,
            metadata=video.get('metadata', {})
        )

        # Extract episodes from the transcription chunks
        episodes = transcriber.extract_episodes_from_chunks(
            chunk_results,
            save_to_db=True,
            video_id=video_id
        )

        return {
            "video_id": video_id,
            "episodes_count": len(episodes),
            "message": "Video reprocessed successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/videos/{video_id}/chunks")
async def get_processing_chunks(video_id: str):
    try:
        query = """
        SELECT * FROM processing_chunks
        WHERE video_id = %(video_id)s
        ORDER BY chunk_number
        """

        result = db._execute_query(query, parameters={'video_id': video_id})
        chunks = []

        for row in result.result_rows:
            chunk_data = dict(zip(result.column_names, row))
            chunks.append(chunk_data)

        return {"chunks": chunks}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/processing/status")
async def get_processing_status():
    try:
        query = """
        SELECT
            processing_status,
            count() as count
        FROM videos
        GROUP BY processing_status
        """

        result = db._execute_query(query)
        status_counts = {}

        for row in result.result_rows:
            status, count = row
            status_counts[status] = count

        return {"processing_status": status_counts}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Video Streaming API
@app.get("/api/episodes/{episode_id}/stream")
async def stream_episode(episode_id: str, request: Request):
    """
    Stream an episode video segment.

    Args:
        episode_id: Episode ID to stream
        request: FastAPI request object for range header support

    Returns:
        StreamingResponse with video content
    """
    try:
        # Get episode details
        episode_query = """
        SELECT e.*, v.file_path as video_file_path
        FROM episodes e
        JOIN videos v ON e.video_id = v.id
        WHERE e.id = %(episode_id)s
        """

        result = db._execute_query(episode_query, parameters={'episode_id': episode_id})

        if not result.result_rows:
            raise HTTPException(status_code=404, detail="Episode not found")

        episode_data = dict(zip(result.column_names, result.result_rows[0]))
        video_file_path = episode_data['video_file_path']
        start_time = episode_data['start_time']
        end_time = episode_data['end_time']
        video_id = episode_data['video_id']
        episode_number = episode_data['episode_number']

        if not os.path.exists(video_file_path):
            raise HTTPException(status_code=404, detail="Video file not found")

        # Temporarily disable caching - stream directly
        return await stream_video_segment(video_file_path, start_time, end_time)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error streaming episode: {str(e)}")

async def stream_video_segment(video_path: str, start_time: float, end_time: float):
    """
    Stream video segment using ffmpeg.

    Args:
        video_path: Path to the source video file
        start_time: Start time in seconds
        end_time: End time in seconds

    Returns:
        StreamingResponse with video content
    """
    duration = end_time - start_time

    # FFmpeg command to extract segment and output as optimized MP4
    cmd = [
        'ffmpeg',
        '-ss', str(start_time),
        '-i', video_path,
        '-t', str(duration),
        '-vf', 'scale=854:480',  # Resize to 480p for faster streaming
        '-c:v', 'libx264',       # Re-encode video for better browser compatibility
        '-preset', 'ultrafast',  # Faster encoding, larger file but quicker processing
        '-crf', '28',           # Slightly lower quality for smaller size
        '-c:a', 'aac',          # Re-encode audio for better browser compatibility
        '-ar', '44100',         # Standard audio sample rate
        '-ac', '2',             # Stereo audio
        '-movflags', 'frag_keyframe+empty_moov+faststart',  # Enable streaming and fast start
        '-f', 'mp4',
        'pipe:1'
    ]

    def generate():
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            while True:
                chunk = process.stdout.read(8192)
                if not chunk:
                    break
                yield chunk
        finally:
            process.terminate()
            process.wait()

    return StreamingResponse(
        generate(),
        media_type="video/mp4",
        headers={
            "Accept-Ranges": "bytes",
            "Content-Disposition": f"inline; filename=episode_{start_time}-{end_time}.mp4"
        }
    )

async def stream_video_segment_with_range(video_path: str, start_time: float, end_time: float, range_header: str):
    """
    Stream video segment with HTTP range support for seeking.

    Args:
        video_path: Path to the source video file
        start_time: Start time in seconds
        end_time: End time in seconds
        range_header: HTTP Range header value

    Returns:
        StreamingResponse with partial content
    """
    # For simplicity, we'll stream the entire segment and let the browser handle ranges
    # A more sophisticated implementation would handle byte ranges within the segment
    return await stream_video_segment(video_path, start_time, end_time)

async def preload_next_episode(video_id: str, current_episode_number: int):
    """
    Preload the next episode in the background for instant navigation.

    Args:
        video_id: The video ID
        current_episode_number: Current episode number
    """
    try:
        # Get next episode
        next_episode_query = """
        SELECT e.*, v.file_path as video_file_path
        FROM episodes e
        JOIN videos v ON e.video_id = v.id
        WHERE e.video_id = %(video_id)s AND e.episode_number = %(next_episode_number)s
        """

        result = db._execute_query(next_episode_query, parameters={
            'video_id': video_id,
            'next_episode_number': current_episode_number + 1
        })

        if result.result_rows:
            episode_data = dict(zip(result.column_names, result.result_rows[0]))
            next_episode_id = episode_data['id']

            # Check if already cached
            if not video_cache.get(next_episode_id):
                await video_cache.preload_episode(
                    next_episode_id,
                    episode_data['video_file_path'],
                    episode_data['start_time'],
                    episode_data['end_time']
                )
    except Exception as e:
        print(f"Error preloading next episode: {e}")

@app.get("/api/cache/stats")
async def get_cache_stats():
    """Get video cache statistics."""
    return {
        "cache_size": len(video_cache.cache),
        "max_size_mb": video_cache.max_size_bytes / (1024 * 1024),
        "current_size_mb": video_cache.current_size_bytes / (1024 * 1024),
        "cache_usage_mb": sum(len(data['data']) for data in video_cache.cache.values()) / (1024 * 1024),
        "cached_episodes": list(video_cache.cache.keys())
    }

@app.delete("/api/cache/clear")
async def clear_cache():
    """Clear the video cache."""
    video_cache.cache.clear()
    video_cache.current_size_bytes = 0
    return {"message": "Cache cleared successfully"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
