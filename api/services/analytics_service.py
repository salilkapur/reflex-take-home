import asyncio
from typing import Dict, Any
from database.clickhouse_client import ClickHouseVideoDatabase

class AnalyticsService:
    def __init__(self, db: ClickHouseVideoDatabase):
        self.db = db

    async def get_analytics_summary(self) -> Dict[str, Any]:
        """Get analytics summary"""
        analytics = await asyncio.to_thread(self.db.get_analytics_summary)
        return {"analytics": analytics}