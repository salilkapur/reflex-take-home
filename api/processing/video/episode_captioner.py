import os
import tempfile
import logging
from typing import Dict, List, Optional, Tuple
import ffmpeg
from google import genai
from google.api_core.exceptions import GoogleAPIError
import time

logger = logging.getLogger(__name__)

class EpisodeCaptioner:
    """
    A class for generating captions for video episodes using Google Gemini API.
    Analyzes video segments and generates time-stamped descriptions.
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the EpisodeCaptioner.

        Args:
            api_key: Google Gemini API key. If None, uses GEMINI_API_KEY environment variable.
        """
        api_key = "AIzaSyBDVuX0cXnw8CplFUnhxebcSr29uMFTCys"
        api_key = api_key or os.getenv('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("Gemini API key must be provided or set as GEMINI_API_KEY environment variable")

        try:
            self.client = genai.Client(api_key=api_key)
            logger.info("Google Gemini client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Google Gemini client: {e}")
            raise

    def extract_video_segment(self, video_path: str, start_time: float, end_time: float, output_path: str) -> None:
        """
        Extract a video segment using FFmpeg.

        Args:
            video_path: Path to the source video file
            start_time: Start time in seconds
            end_time: End time in seconds
            output_path: Path for the extracted segment
        """
        try:
            (
                ffmpeg
                .input(video_path, ss=start_time, t=end_time - start_time)
                .output(output_path, vcodec='libx264', acodec='aac')
                .overwrite_output()
                .run(quiet=True)
            )
            logger.info(f"Extracted video segment: {start_time}s - {end_time}s")
        except Exception as e:
            logger.error(f"Failed to extract video segment: {e}")
            raise e

    def generate_caption_with_gemini(self, video_path: str) -> str:
        """
        Generate a caption for a video segment using Google Gemini.

        Args:
            video_path: Path to the video segment file

        Returns:
            Generated caption string
        """
        my_file = None  # Initialize my_file to ensure it's in scope for the finally block
        try:
            # 1. Upload the video file using the File API
            logger.info(f"Uploading video segment to Gemini: {video_path}")
            my_file = self.client.files.upload(file=video_path)

            # 2. Wait for the file to be ready with a timeout
            print(f"File upload state: {my_file.state.name}")
            print(f"Filename: {my_file.name}")
            while my_file.state.name == "PROCESSING":
                time.sleep(3)
                my_file = self.client.files.get(name=my_file.name)

            if my_file.state.name == "FAILED":
                raise ValueError(f"Video processing failed: {my_file.state.name}")

            # 3. Define the prompt and generate the caption
            prompt = "Provide a detailed but concise caption for this video. Describe the objects and the action being performed."

            logger.info("Generating caption with Gemini...")
            response = self.client.models.generate_content(
                model="gemini-1.5-flash", contents=[my_file, prompt]
            )

            caption = response.text.strip()
            logger.info(f"Generated caption: {caption}")
            return caption

        except GoogleAPIError as e:
            logger.error(f"Google Gemini API error: {e}")
            raise
        except Exception as e:
            logger.error(f"An unexpected error occurred: {e}")
            raise
        finally:
            # 4. Clean up: Delete the uploaded file
            if my_file and my_file.name:
                try:
                    logger.info(f"Deleting uploaded file: {my_file.name}")
                    self.client.files.delete(name=my_file.name)
                except Exception as e:
                    logger.warning(f"Failed to delete file {my_file.name}: {e}")

    def caption_episode(
        self,
        video_path: str,
        start_time: float,
        end_time: float,
        episode_id: str
    ) -> str:
        """
        Generate a caption for a specific episode.

        Args:
            video_path: Path to the source video file
            start_time: Episode start time in seconds
            end_time: Episode end time in seconds
            episode_id: Unique identifier for the episode

        Returns:
            Generated caption string
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                # Extract video segment
                segment_path = os.path.join(temp_dir, f"episode_{episode_id}.mp4")
                self.extract_video_segment(video_path, start_time, end_time, segment_path)

                # Generate caption using Gemini
                caption = self.generate_caption_with_gemini(segment_path)

                logger.debug(f"Generated caption for episode {episode_id}: {caption}")
                return caption

            except Exception as e:
                logger.error(f"Failed to caption episode {episode_id}: {e}")
            finally:
                os.remove(segment_path)
