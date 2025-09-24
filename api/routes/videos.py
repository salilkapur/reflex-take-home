from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from services.video_service import VideoService

router = APIRouter()

def setup_video_routes(video_service: VideoService):
    """Setup video routes with dependency injection"""

    @router.get("/api/videos")
    async def list_videos(
        skip: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=1000),
        include_unprocessed: bool = Query(False, description="Include unprocessed videos from data folder")
    ):
        try:
            return await video_service.get_videos(skip, limit, include_unprocessed)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/api/videos/unprocessed")
    async def list_unprocessed_videos():
        try:
            return await video_service.get_unprocessed_videos()
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/api/videos/start-processing")
    async def start_video_processing(
        filename: str = Query(..., description="Video filename to process"),
        chunk_length: int = Query(15, description="Length of each chunk in seconds"),
        max_chunks: Optional[int] = Query(None, description="Maximum number of chunks to process")
    ):
        try:
            return await video_service.start_processing(filename, chunk_length, max_chunks)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    return router