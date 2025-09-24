from fastapi import APIRouter, HTTPException
from services.analytics_service import AnalyticsService

router = APIRouter()

def setup_analytics_routes(analytics_service: AnalyticsService):
    """Setup analytics routes with dependency injection"""

    @router.get("/api/analytics/summary")
    async def get_analytics_summary():
        try:
            return await analytics_service.get_analytics_summary()
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    return router