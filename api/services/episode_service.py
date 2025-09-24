import asyncio
import json
import os
import sys
from typing import Dict, List, Any, Optional
from database.clickhouse_client import ClickHouseVideoDatabase
sys.path.append(os.path.join(os.path.dirname(__file__), '../processing/video'))
from episode_captioner import EpisodeCaptioner

class EpisodeService:
    def __init__(self, db: ClickHouseVideoDatabase):
        self.db = db

    async def get_episodes_for_video(self, video_id: str) -> List[Dict[str, Any]]:
        """Get all episodes for a video"""
        episodes = await asyncio.to_thread(self.db.get_episodes_for_video, video_id)
        return episodes

    async def get_episode(self, episode_id: str) -> Dict[str, Any]:
        """Get a single episode by ID"""
        query = "SELECT * FROM episodes WHERE id = %(episode_id)s"
        result = await asyncio.to_thread(self.db._execute_query, query, {"episode_id": episode_id})

        if not result.result_rows:
            raise ValueError("Episode not found")

        episode_data = dict(zip(result.column_names, result.result_rows[0]))
        if episode_data.get('metadata'):
            if isinstance(episode_data['metadata'], str):
                try:
                    episode_data['metadata'] = json.loads(episode_data['metadata'])
                except json.JSONDecodeError:
                    episode_data['metadata'] = {}
            elif not isinstance(episode_data['metadata'], dict):
                episode_data['metadata'] = {}

        # Parse words from JSON
        if episode_data.get('words'):
            if isinstance(episode_data['words'], str):
                try:
                    episode_data['words'] = json.loads(episode_data['words'])
                except json.JSONDecodeError:
                    episode_data['words'] = []
            elif not isinstance(episode_data['words'], list):
                episode_data['words'] = []

        return episode_data

    async def update_episode_annotation(self, episode_id: str, annotation_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update episode annotation"""
        result = await asyncio.to_thread(self.db.update_episode_annotation, episode_id, annotation_data)
        return {"status": "success", "message": "Annotation updated"}

    async def update_episode_captions(self, episode_id: str, captions: str) -> Dict[str, Any]:
        """Update episode captions"""
        result = await asyncio.to_thread(self.db.update_episode_captions, episode_id, captions)
        return {"status": "success", "message": "Captions updated"}

    async def get_episode_stream_url(self, episode_id: str) -> str:
        """Get episode stream URL"""
        # For now, return a placeholder URL
        return f"/api/episodes/{episode_id}/stream"

    async def get_episode_video_info(self, episode_id: str) -> Optional[Dict[str, Any]]:
        """Get the video file info and timing for an episode"""
        import asyncio

        episode = await self.get_episode(episode_id)
        video_id = episode.get('video_id')

        if not video_id:
            return None

        # Get the main video file path from the video record
        video_query = "SELECT file_path FROM videos WHERE id = %(video_id)s"
        result = await asyncio.to_thread(self.db._execute_query, video_query, {"video_id": video_id})

        if not result.result_rows:
            return None

        main_video_path = result.result_rows[0][0]

        if not main_video_path:
            return None

        import os
        if not os.path.exists(main_video_path):
            return None

        return {
            'main_video_path': main_video_path,
            'start_time': episode.get('start_time', 0),
            'end_time': episode.get('end_time', 0),
            'duration': episode.get('duration', 0)
        }

    async def caption_episodes_async(self, video_id: str) -> Dict[str, Any]:
        """Caption all episodes for a video asynchronously"""
        try:
            # Get all episodes for the video
            episodes = await self.get_episodes_for_video(video_id)

            if not episodes:
                return {"status": "success", "message": "No episodes found for this video", "processed": 0, "skipped": 0}

            # Get video file path
            video_query = "SELECT file_path FROM videos WHERE id = %(video_id)s"
            result = await asyncio.to_thread(self.db._execute_query, video_query, {"video_id": video_id})

            if not result.result_rows:
                return {"status": "error", "message": "Video not found"}

            video_path = result.result_rows[0][0]

            if not os.path.exists(video_path):
                return {"status": "error", "message": "Video file not found on disk"}

            # Initialize captioner
            captioner = EpisodeCaptioner()

            processed_count = 0
            skipped_count = 0
            errors = []

            for episode in episodes:
                episode_id = episode.get('id')
                existing_caption = episode.get('caption')

                # Skip if caption already exists
                if existing_caption and existing_caption.strip():
                    skipped_count += 1
                    continue

                try:
                    start_time = episode.get('start_time', 0)
                    end_time = episode.get('end_time', 0)

                    # Generate caption
                    caption = await asyncio.to_thread(
                        captioner.caption_episode,
                        video_path,
                        start_time,
                        end_time,
                        episode_id
                    )

                    # Update database with caption
                    if caption:
                        await self.update_episode_captions(episode_id, caption)
                        processed_count += 1

                except Exception as e:
                    error_msg = f"Failed to caption episode {episode_id}: {str(e)}"
                    errors.append(error_msg)
                    print(error_msg)

            return {
                "status": "success" if not errors else "partial_success",
                "message": f"Captioning completed. Processed: {processed_count}, Skipped: {skipped_count}",
                "processed": processed_count,
                "skipped": skipped_count,
                "errors": errors
            }

        except Exception as e:
            return {"status": "error", "message": f"Failed to start captioning: {str(e)}"}