from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Import database
from database.clickhouse_client import ClickHouseVideoDatabase

# Import services
from services.video_service import VideoService
from services.episode_service import EpisodeService
from services.analytics_service import AnalyticsService

# Import route setup functions
from routes.videos import setup_video_routes
from routes.episodes import setup_episode_routes
from routes.analytics import setup_analytics_routes

# Initialize FastAPI app
app = FastAPI(
    title="Video Transcription API",
    description="API for video transcription and episode management",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize database
db = ClickHouseVideoDatabase()

# Initialize services
video_service = VideoService(db)
episode_service = EpisodeService(db)
analytics_service = AnalyticsService(db)

# Setup routes
video_router = setup_video_routes(video_service)
episode_router = setup_episode_routes(episode_service)
analytics_router = setup_analytics_routes(analytics_service)

# Include routers
app.include_router(video_router)
app.include_router(episode_router)
app.include_router(analytics_router)

# Health check endpoint
@app.get("/")
async def root():
    return {"message": "Video Transcription API", "version": "1.0.0"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)