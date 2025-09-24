#!/usr/bin/env python3

import sys
import os
import logging
from pathlib import Path

# Add the processing directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), 'processing/video'))

from episode_captioner import EpisodeCaptioner

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    """Test the EpisodeCaptioner with the first 15 seconds of an existing video."""

    # Find the video file
    video_path = "/Users/salilkapur/work/reflex/api/data/robot_1.mp4"

    if not os.path.exists(video_path):
        video_path = "/Users/salilkapur/work/reflex/api/data/robot_2.mp4"

    if not os.path.exists(video_path):
        logger.error("No video file found. Please ensure robot_1.mp4 or robot_2.mp4 exists in the data/ folder.")
        return

    logger.info(f"Testing with video file: {video_path}")

    try:
        # Initialize the captioner
        logger.info("Initializing EpisodeCaptioner...")
        captioner = EpisodeCaptioner()

        # Caption the first 15 seconds
        logger.info("Generating caption for first 15 seconds...")
        caption = captioner.caption_episode(
            video_path=video_path,
            start_time=0.0,      # Start at beginning
            end_time=15.0,       # End at 15 seconds
            episode_id="test_episode_1"
        )

        logger.info("Caption generated successfully!")
        print("\n" + "="*60)
        print("GENERATED CAPTION:")
        print("="*60)
        print(caption)
        print("="*60 + "\n")

    except Exception as e:
        logger.error(f"Error during captioning: {e}")
        raise

if __name__ == "__main__":
    main()