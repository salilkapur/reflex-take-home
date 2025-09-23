import os
import tempfile
from typing import List, Dict, Any
import ffmpeg


class EpisodeVideoExtractor:
    """
    A utility class for extracting episodes as separate video files.
    This is primarily for testing and debugging purposes.
    """

    def __init__(self, output_dir: str = "extracted_episodes"):
        """
        Initialize the episode extractor.

        Args:
            output_dir: Directory to save extracted episode videos
        """
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def extract_episode_videos(self, video_path: str, episodes: List[Dict[str, Any]]) -> List[str]:
        """
        Extract episodes as separate video files.

        Args:
            video_path: Path to the original video file
            episodes: List of episode dictionaries from VideoTranscriber

        Returns:
            List of paths to extracted episode video files
        """
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")

        extracted_files = []

        for episode in episodes:
            if episode.get('incomplete', False):
                print(f"Skipping incomplete episode {episode['episode_number']}")
                continue

            output_file = self._generate_output_filename(episode)

            try:
                self._extract_video_segment(
                    video_path,
                    output_file,
                    episode['start_time'],
                    episode['duration']
                )

                extracted_files.append(output_file)
                print(f"Extracted Episode {episode['episode_number']}: {output_file}")

            except Exception as e:
                print(f"Failed to extract episode {episode['episode_number']}: {e}")

        return extracted_files

    def _extract_video_segment(self, input_path: str, output_path: str, start_time: float, duration: float):
        """
        Extract a video segment using ffmpeg.

        Args:
            input_path: Path to input video
            output_path: Path for output video
            start_time: Start time in seconds
            duration: Duration in seconds
        """
        try:
            (
                ffmpeg
                .input(input_path, ss=start_time, t=duration)
                .output(output_path, vcodec='copy', acodec='copy')
                .overwrite_output()
                .run(capture_stdout=True, capture_stderr=True)
            )
        except ffmpeg.Error as e:
            raise RuntimeError(f"FFmpeg error during video extraction: {e.stderr.decode()}")

    def _generate_output_filename(self, episode: Dict[str, Any]) -> str:
        """
        Generate output filename for an episode.

        Args:
            episode: Episode dictionary

        Returns:
            Full path to output file
        """
        start_time = int(episode['start_time'])
        end_time = int(episode['end_time'])
        episode_num = episode['episode_number']

        filename = f"episode_{episode_num:03d}_{start_time}s-{end_time}s.mp4"
        return os.path.join(self.output_dir, filename)

    def create_episode_summary_file(self, episodes: List[Dict[str, Any]], summary_file: str = None) -> str:
        """
        Create a text summary file of all episodes.

        Args:
            episodes: List of episode dictionaries
            summary_file: Path to summary file (optional)

        Returns:
            Path to created summary file
        """
        if summary_file is None:
            summary_file = os.path.join(self.output_dir, "episodes_summary.txt")

        with open(summary_file, 'w') as f:
            f.write("Episode Summary\n")
            f.write("=" * 50 + "\n\n")

            for episode in episodes:
                status = " (INCOMPLETE)" if episode.get('incomplete', False) else ""
                f.write(f"Episode {episode['episode_number']}{status}\n")
                f.write(f"Time: {episode['start_time']:.2f}s - {episode['end_time']:.2f}s\n")
                f.write(f"Duration: {episode['duration']:.2f}s\n")
                f.write(f"Word count: {episode['word_count']}\n")
                f.write(f"Transcript: {episode['transcript']}\n")
                f.write("-" * 30 + "\n\n")

        return summary_file


# Testing utility function
def extract_and_save_episodes(video_path: str, episodes: List[Dict[str, Any]], output_dir: str = "test_episodes"):
    """
    Convenience function to extract episodes and create summary.

    Args:
        video_path: Path to the original video
        episodes: Episodes from VideoTranscriber
        output_dir: Directory for output files

    Returns:
        Dictionary with extracted file paths and summary
    """
    extractor = EpisodeVideoExtractor(output_dir)

    # Extract episode videos
    extracted_files = extractor.extract_episode_videos(video_path, episodes)

    # Create summary file
    summary_file = extractor.create_episode_summary_file(episodes)

    return {
        'extracted_files': extracted_files,
        'summary_file': summary_file,
        'total_episodes': len(episodes),
        'extracted_episodes': len(extracted_files)
    }