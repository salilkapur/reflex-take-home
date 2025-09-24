from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from services.episode_service import EpisodeService
import json

router = APIRouter()

class AnnotationUpdate(BaseModel):
    status: str
    annotated_at: str = None

def setup_episode_routes(episode_service: EpisodeService):
    """Setup episode routes with dependency injection"""

    @router.get("/api/videos/{video_id}/episodes")
    async def get_video_episodes(video_id: str):
        try:
            episodes = await episode_service.get_episodes_for_video(video_id)
            return {"episodes": episodes}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/api/episodes/{episode_id}")
    async def get_episode(episode_id: str):
        try:
            episode = await episode_service.get_episode(episode_id)
            return episode
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.put("/api/episodes/{episode_id}/annotation")
    async def update_episode_annotation(episode_id: str, annotation: AnnotationUpdate):
        try:
            result = await episode_service.update_episode_annotation(episode_id, annotation.dict())
            return result
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.put("/api/episodes/{episode_id}/captions")
    async def update_episode_captions(episode_id: str, request: Request):
        try:
            body = await request.body()
            captions = body.decode('utf-8')
            result = await episode_service.update_episode_captions(episode_id, captions)
            return result
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/api/episodes/{episode_id}/stream")
    async def stream_episode(episode_id: str):
        try:
            # Get the video file info and timing for this episode
            video_info = await episode_service.get_episode_video_info(episode_id)

            if not video_info:
                raise HTTPException(status_code=404, detail="Video file not found for this episode")

            main_video_path = video_info['main_video_path']
            start_time = video_info['start_time']
            end_time = video_info['end_time']

            # Check if main video file exists
            import os
            if not os.path.exists(main_video_path):
                raise HTTPException(status_code=404, detail="Main video file not found on disk")

            # Use FFmpeg to stream the specific time segment
            import subprocess
            import tempfile
            from fastapi.responses import StreamingResponse
            import asyncio

            def generate_video_segment():
                """Generate video segment using FFmpeg"""
                # Use FFmpeg to extract the time segment
                cmd = [
                    'ffmpeg',
                    '-i', main_video_path,
                    '-ss', str(start_time),
                    '-to', str(end_time),
                    '-c', 'copy',  # Copy streams without re-encoding for speed
                    '-f', 'mp4',
                    '-movflags', 'frag_keyframe+empty_moov',  # Enable streaming
                    'pipe:1'
                ]

                try:
                    process = subprocess.Popen(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        bufsize=0
                    )

                    # Stream the output
                    while True:
                        chunk = process.stdout.read(8192)
                        if not chunk:
                            break
                        yield chunk

                    process.wait()
                    if process.returncode != 0:
                        stderr_output = process.stderr.read().decode()
                        print(f"FFmpeg error: {stderr_output}")

                except Exception as e:
                    print(f"Error generating video segment: {e}")
                finally:
                    if process and process.poll() is None:
                        process.terminate()

            return StreamingResponse(
                generate_video_segment(),
                media_type="video/mp4",
                headers={
                    "Content-Disposition": f"inline; filename=episode_{episode_id}.mp4",
                    "Accept-Ranges": "bytes"
                }
            )

        except ValueError:
            raise HTTPException(status_code=404, detail="Episode not found")
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/api/videos/{video_id}/episodes/caption")
    async def caption_episodes(video_id: str):
        """Caption all episodes for a video asynchronously"""
        try:
            result = await episode_service.caption_episodes_async(video_id)
            return result
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    return router