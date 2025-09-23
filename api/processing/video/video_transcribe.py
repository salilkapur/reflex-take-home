import os
import tempfile
import json
import hashlib
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
import openai
import ffmpeg
import re

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

class VideoTranscriber:
    """
    A class for transcribing video files using OpenAI Whisper with word-level timestamps.
    """

    def __init__(self, api_key: Optional[str] = None, chunk_length_seconds: int = 600,
                 cache_dir: str = ".transcription_cache", db_client=None):
        """
        Initialize the VideoTranscriber.

        Args:
            api_key: OpenAI API key. If not provided, will use OPENAI_API_KEY environment variable.
            chunk_length_seconds: Length of each video chunk in seconds (default: 600 = 10 minutes)
            cache_dir: Directory to store transcription cache files
            db_client: ClickHouse database client instance
        """
        if api_key:
            openai.api_key = api_key
        elif os.getenv("OPENAI_API_KEY"):
            openai.api_key = os.getenv("OPENAI_API_KEY")
        else:
            raise ValueError("OpenAI API key must be provided either as parameter or OPENAI_API_KEY environment variable")

        self.chunk_length_seconds = chunk_length_seconds
        self.cache_dir = cache_dir
        self.db_client = db_client
        os.makedirs(cache_dir, exist_ok=True)

    def extract_audio_chunk(self, video_path: str, audio_path: str, start_time: float, duration: float) -> None:
        """
        Extract audio chunk from video file using ffmpeg.

        Args:
            video_path: Path to the input video file
            audio_path: Path where the extracted audio will be saved
            start_time: Start time in seconds
            duration: Duration in seconds
        """
        try:
            (
                ffmpeg
                .input(video_path, ss=start_time, t=duration)
                .output(
                    audio_path,
                    acodec='mp3',
                    ac=1,  # mono audio
                    ar='16000'  # 16kHz sample rate (optimal for Whisper)
                )
                .overwrite_output()
                .run(capture_stdout=True, capture_stderr=True)
            )
        except ffmpeg.Error as e:
            raise RuntimeError(f"FFmpeg error during audio extraction: {e.stderr.decode()}")
        except Exception as e:
            raise RuntimeError(f"Audio extraction failed: {str(e)}")

    def get_video_duration(self, video_path: str) -> float:
        """
        Get video duration in seconds using ffprobe.

        Args:
            video_path: Path to the video file

        Returns:
            Duration in seconds
        """
        try:
            probe = ffmpeg.probe(video_path)
            duration = float(probe['streams'][0]['duration'])
            return duration
        except Exception as e:
            raise RuntimeError(f"Failed to get video duration: {str(e)}")

    def transcribe_audio(self, audio_path: str, response_format: str = "verbose_json") -> Dict[str, Any]:
        """
        Transcribe audio file using OpenAI Whisper.

        Args:
            audio_path: Path to the audio file
            response_format: Format of the response ("json", "text", "srt", "verbose_json", "vtt")

        Returns:
            Transcription response from OpenAI Whisper
        """
        with open(audio_path, "rb") as audio_file:
            transcript = openai.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format=response_format,
                timestamp_granularities=["word"]
            )
        return transcript

    def transcribe_video_chunked(self, video_path: str, cleanup_temp: bool = True, max_chunks: Optional[int] = None,
                               save_to_db: bool = True, video_metadata: Dict[str, Any] = None) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Transcribe a video file in chunks with word-level timestamps.

        Args:
            video_path: Path to the video file
            cleanup_temp: Whether to clean up temporary audio files
            max_chunks: Maximum number of chunks to process (None for all)
            save_to_db: Whether to save results to database
            video_metadata: Custom metadata for the video

        Returns:
            Tuple of (video_id, chunk_results)
        """
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")

        # Create video record in database if enabled
        video_id = None
        if save_to_db and self.db_client:
            stat = os.stat(video_path)
            total_duration = self.get_video_duration(video_path)

            video_id = self.db_client.create_video_record(
                video_path=video_path,
                file_size=stat.st_size,
                duration=total_duration,
                chunk_length=self.chunk_length_seconds,
                metadata=video_metadata or {}
            )

            self.db_client.update_video_status(video_id, 'processing')
            print(f"Created video record: {video_id}")
        else:
            total_duration = self.get_video_duration(video_path)

        chunk_results = []
        chunk_num = 0
        current_time = 0.0

        while current_time < total_duration and (max_chunks is None or chunk_num < max_chunks):
            chunk_duration = min(self.chunk_length_seconds, total_duration - current_time)

            # Create temporary audio file for this chunk
            with tempfile.NamedTemporaryFile(suffix=f"_chunk_{chunk_num}.mp3", delete=False) as temp_audio:
                temp_audio_path = temp_audio.name

            try:
                print(f"Processing chunk {chunk_num + 1}: {current_time:.1f}s - {current_time + chunk_duration:.1f}s")

                # Generate cache key for this chunk
                cache_key = self._generate_cache_key(video_path, current_time, chunk_duration)

                # Try to load from cache first
                cached_data = self._load_from_cache(cache_key)
                is_cache_hit = cached_data is not None

                if cached_data:
                    # Use cached transcription
                    transcription = self._dict_to_transcription_like(cached_data)
                else:
                    # Extract audio chunk and transcribe
                    self.extract_audio_chunk(video_path, temp_audio_path, current_time, chunk_duration)
                    transcription = self.transcribe_audio(temp_audio_path)

                    # Save to cache (before adjusting timestamps)
                    transcription_dict = self._transcription_to_dict(transcription)
                    self._save_to_cache(cache_key, transcription_dict)

                # Save chunk processing info to database
                if save_to_db and self.db_client and video_id:
                    word_count = len(transcription.words) if hasattr(transcription, 'words') and transcription.words else 0
                    self.db_client.save_processing_chunk(
                        video_id=video_id,
                        chunk_number=chunk_num,
                        start_time=current_time,
                        end_time=current_time + chunk_duration,
                        cache_key=cache_key,
                        cache_hit=is_cache_hit,
                        word_count=word_count
                    )

                # Adjust timestamps to global video time
                transcription = self.adjust_chunk_timestamps(transcription, current_time)

                # Create chunk result dictionary with metadata
                chunk_result = {
                    'transcription': transcription,
                    'chunk_number': chunk_num,
                    'chunk_start_time': current_time,
                    'chunk_duration': chunk_duration
                }

                chunk_results.append(chunk_result)

            finally:
                # Clean up temporary file
                if cleanup_temp and os.path.exists(temp_audio_path):
                    os.unlink(temp_audio_path)

            current_time += chunk_duration
            chunk_num += 1

        # Update total chunks in database
        if save_to_db and self.db_client and video_id:
            self.db_client.update_video_status(video_id, 'processing', total_chunks=chunk_num)

        return video_id, chunk_results

    def adjust_chunk_timestamps(self, chunk_result: Dict[str, Any], chunk_start_time: float) -> Dict[str, Any]:
        """
        Adjust word timestamps in chunk result to global video time.

        Args:
            chunk_result: Transcription result from a chunk
            chunk_start_time: Start time of the chunk in the full video

        Returns:
            Chunk result with adjusted timestamps
        """
        if hasattr(chunk_result, 'words') and chunk_result.words:
            for word_data in chunk_result.words:
                word_data.start += chunk_start_time
                word_data.end += chunk_start_time

        return chunk_result

    def _generate_cache_key(self, video_path: str, start_time: float, duration: float) -> str:
        """
        Generate a unique cache key for a video chunk.

        Args:
            video_path: Path to the video file
            start_time: Start time of the chunk
            duration: Duration of the chunk

        Returns:
            Unique cache key string
        """
        # Get file stats for uniqueness
        stat = os.stat(video_path)
        file_info = f"{video_path}_{stat.st_size}_{stat.st_mtime}_{start_time}_{duration}"

        # Create hash of the info
        cache_key = hashlib.md5(file_info.encode()).hexdigest()
        return cache_key

    def _load_from_cache(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """
        Load transcription result from cache.

        Args:
            cache_key: Cache key to load

        Returns:
            Cached transcription result or None if not found
        """
        cache_file = os.path.join(self.cache_dir, f"{cache_key}.json")

        try:
            if os.path.exists(cache_file):
                with open(cache_file, 'r') as f:
                    cache_data = json.load(f)
                print(f"Loaded from cache: {cache_key}")
                return cache_data
        except Exception as e:
            print(f"Failed to load cache {cache_key}: {e}")

        return None

    def _save_to_cache(self, cache_key: str, transcription_data: Dict[str, Any]) -> None:
        """
        Save transcription result to cache.

        Args:
            cache_key: Cache key to save under
            transcription_data: Transcription result to cache
        """
        cache_file = os.path.join(self.cache_dir, f"{cache_key}.json")

        try:
            with open(cache_file, 'w') as f:
                json.dump(transcription_data, f, indent=2)
            print(f"Saved to cache: {cache_key}")
        except Exception as e:
            print(f"Failed to save cache {cache_key}: {e}")

    def _transcription_to_dict(self, transcription) -> Dict[str, Any]:
        """
        Convert OpenAI transcription object to dictionary for caching.

        Args:
            transcription: OpenAI transcription result

        Returns:
            Dictionary representation of transcription
        """
        result = {
            'text': transcription.text,
            'words': []
        }

        if hasattr(transcription, 'words') and transcription.words:
            for word in transcription.words:
                result['words'].append({
                    'word': word.word,
                    'start': word.start,
                    'end': word.end
                })

        return result

    def _dict_to_transcription_like(self, data: Dict[str, Any]):
        """
        Convert cached dictionary back to transcription-like object.

        Args:
            data: Cached transcription data

        Returns:
            Object that mimics OpenAI transcription structure
        """
        class MockWord:
            def __init__(self, word: str, start: float, end: float):
                self.word = word
                self.start = start
                self.end = end

        class MockTranscription:
            def __init__(self, text: str, words: List[MockWord]):
                self.text = text
                self.words = words

        words = [MockWord(w['word'], w['start'], w['end']) for w in data.get('words', [])]
        return MockTranscription(data['text'], words)

    def get_word_timestamps(self, transcription_result: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract word-level timestamps from transcription result.

        Args:
            transcription_result: Result from transcribe_video method

        Returns:
            List of dictionaries containing word and timestamp information
        """
        words = []

        if hasattr(transcription_result, 'words') and transcription_result.words:
            for word_data in transcription_result.words:
                words.append({
                    'word': word_data.word,
                    'start': word_data.start,
                    'end': word_data.end
                })

        return words

    def format_transcript_with_timestamps(self, transcription_result: Dict[str, Any]) -> str:
        """
        Format transcription with word-level timestamps.

        Args:
            transcription_result: Result from transcribe_video method

        Returns:
            Formatted string with words and their timestamps
        """
        words = self.get_word_timestamps(transcription_result)

        formatted_lines = []
        for word_data in words:
            timestamp = f"[{word_data['start']:.2f}s - {word_data['end']:.2f}s]"
            formatted_lines.append(f"{timestamp} {word_data['word']}")

        return "\n".join(formatted_lines)

    def find_delimiter_words(self, words: List[Dict[str, Any]], start_word: str = "start", end_word: str = "finish") -> List[Tuple[int, int]]:
        """
        Find positions of delimiter words in the transcript.

        Args:
            words: List of word dictionaries with 'word', 'start', 'end' keys
            start_word: Word that marks the beginning of an episode
            end_word: Word that marks the end of an episode

        Returns:
            List of tuples containing (start_index, end_index) pairs
        """
        delimiter_positions = []

        for i, word_data in enumerate(words):
            word = word_data['word'].strip().lower()
            if word == start_word.lower():
                delimiter_positions.append(('start', i))
            elif word == end_word.lower():
                delimiter_positions.append(('end', i))

        return delimiter_positions

    def extract_episodes_from_chunks(self, chunk_results: List[Dict[str, Any]], start_word: str = "start", end_word: str = "finish",
                                   save_to_db: bool = True, video_id: str = None) -> List[Dict[str, Any]]:
        """
        Extract episodes from chunked transcription results, handling cross-chunk episodes.

        Args:
            chunk_results: List of chunk transcription results
            start_word: Word that marks the beginning of an episode
            end_word: Word that marks the end of an episode
            save_to_db: Whether to save episodes to database
            video_id: Video ID for database operations

        Returns:
            List of episode dictionaries with episode data and timestamps
        """
        # Combine all words from all chunks
        all_words = []
        for chunk_result in chunk_results:
            chunk_words = self.get_word_timestamps(chunk_result['transcription'])
            all_words.extend(chunk_words)

        if not all_words:
            return []

        delimiter_positions = self.find_delimiter_words(all_words, start_word, end_word)
        episodes = []

        # Track current episode start
        current_start_idx = None
        episode_number = 1

        for delimiter_type, word_idx in delimiter_positions:
            if delimiter_type == 'start':
                # Close previous episode if it was left open
                if current_start_idx is not None:
                    episode = self._create_episode(
                        all_words, current_start_idx, word_idx - 1,
                        episode_number, incomplete=True
                    )
                    episodes.append(episode)
                    episode_number += 1

                # Start new episode
                current_start_idx = word_idx

            elif delimiter_type == 'end' and current_start_idx is not None:
                # Complete current episode
                episode = self._create_episode(
                    all_words, current_start_idx, word_idx, episode_number
                )
                episodes.append(episode)
                episode_number += 1
                current_start_idx = None

        # Handle unclosed episode at the end
        if current_start_idx is not None:
            episode = self._create_episode(
                all_words, current_start_idx, len(all_words) - 1,
                episode_number, incomplete=True
            )
            episodes.append(episode)

        # Save episodes to database
        if save_to_db and self.db_client and video_id and episodes:
            self.db_client.save_episodes(video_id, episodes)

        return episodes

    def extract_episodes(self, transcription_result: Dict[str, Any], start_word: str = "start", end_word: str = "finish") -> List[Dict[str, Any]]:
        """
        Extract episodes based on delimiter words from single transcription result.

        Args:
            transcription_result: Result from transcribe_video method
            start_word: Word that marks the beginning of an episode
            end_word: Word that marks the end of an episode

        Returns:
            List of episode dictionaries with episode data and timestamps
        """
        words = self.get_word_timestamps(transcription_result)

        if not words:
            return []

        delimiter_positions = self.find_delimiter_words(words, start_word, end_word)
        episodes = []

        # Track current episode start
        current_start_idx = None
        episode_number = 1

        for delimiter_type, word_idx in delimiter_positions:
            if delimiter_type == 'start':
                # Close previous episode if it was left open
                if current_start_idx is not None:
                    episode = self._create_episode(
                        words, current_start_idx, word_idx - 1,
                        episode_number, incomplete=True
                    )
                    episodes.append(episode)
                    episode_number += 1

                # Start new episode
                current_start_idx = word_idx

            elif delimiter_type == 'end' and current_start_idx is not None:
                # Complete current episode
                episode = self._create_episode(
                    words, current_start_idx, word_idx, episode_number
                )
                episodes.append(episode)
                episode_number += 1
                current_start_idx = None

        # Handle unclosed episode at the end
        if current_start_idx is not None:
            episode = self._create_episode(
                words, current_start_idx, len(words) - 1,
                episode_number, incomplete=True
            )
            episodes.append(episode)

        return episodes

    def _create_episode(self, words: List[Dict[str, Any]], start_idx: int, end_idx: int, episode_number: int, incomplete: bool = False) -> Dict[str, Any]:
        """
        Create episode dictionary from word range.

        Args:
            words: List of all words with timestamps
            start_idx: Starting word index
            end_idx: Ending word index
            episode_number: Episode number for identification
            incomplete: Whether the episode is incomplete (missing start or end delimiter)

        Returns:
            Episode dictionary with metadata and content
        """
        if start_idx >= len(words) or end_idx >= len(words) or start_idx > end_idx:
            return {
                'episode_number': episode_number,
                'start_time': 0,
                'end_time': 0,
                'duration': 0,
                'word_count': 0,
                'transcript': '',
                'words': [],
                'incomplete': True,
                'error': 'Invalid word indices',
                'metadata': {
                    'annotation': {
                        'status': 'not_classified'
                    }
                }
            }

        episode_words = words[start_idx:end_idx + 1]

        start_time = episode_words[0]['start']
        end_time = episode_words[-1]['end']
        duration = end_time - start_time

        # Create transcript text
        transcript_words = [word_data['word'] for word_data in episode_words]
        transcript = ' '.join(transcript_words).strip()

        return {
            'episode_number': episode_number,
            'start_time': start_time,
            'end_time': end_time,
            'duration': duration,
            'word_count': len(episode_words),
            'transcript': transcript,
            'words': episode_words,
            'incomplete': incomplete,
            'metadata': {
                'annotation': {
                    'status': 'not_classified'
                }
            }
        }

    def get_episode_summary(self, episodes: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Get summary statistics for all episodes.

        Args:
            episodes: List of episode dictionaries

        Returns:
            Summary dictionary with episode statistics
        """
        if not episodes:
            return {
                'total_episodes': 0,
                'total_duration': 0,
                'average_duration': 0,
                'incomplete_episodes': 0
            }

        total_duration = sum(ep['duration'] for ep in episodes)
        incomplete_count = sum(1 for ep in episodes if ep.get('incomplete', False))

        return {
            'total_episodes': len(episodes),
            'total_duration': total_duration,
            'average_duration': total_duration / len(episodes) if episodes else 0,
            'incomplete_episodes': incomplete_count,
            'complete_episodes': len(episodes) - incomplete_count
        }


# Example usage
if __name__ == "__main__":
    from episode_extractor import extract_and_save_episodes
    import sys
    import os

    # Add database module to path
    sys.path.append(os.path.join(os.path.dirname(__file__), '../../database'))
    from clickhouse_client import ClickHouseVideoDatabase

    # Initialize database client
    db_client = ClickHouseVideoDatabase()

    # Initialize transcriber with database integration
    transcriber = VideoTranscriber(
        api_key=OPENAI_API_KEY,
        chunk_length_seconds=15,
        db_client=db_client
    )

    # Transcribe video
    video_file = "/Users/salilkapur/work/reflex/api/processing/video/test_data/ReflexVideoData.mp4"

    try:
        # Custom video metadata
        video_metadata = {
            "source": "demo",
            "quality": "high",
            "tags": ["test", "reflex"],
            "description": "Test video for episode extraction"
        }

        # Transcribe video in chunks (process only first 3 chunks for testing)
        video_id, chunk_results = transcriber.transcribe_video_chunked(
            video_file,
            save_to_db=True,
            video_metadata=video_metadata
        )

        print(f"Video ID: {video_id}")
        print(f"Processed {len(chunk_results)} chunks")

        # Extract episodes from all chunks (handles cross-chunk episodes)
        episodes = transcriber.extract_episodes_from_chunks(
            chunk_results,
            start_word="start",
            end_word="finish",
            save_to_db=True,
            video_id=video_id
        )

        # Get episode summary
        summary = transcriber.get_episode_summary(episodes)
        print(f"\nEpisode Summary:")
        print(f"Total episodes: {summary['total_episodes']}")
        print(f"Complete episodes: {summary['complete_episodes']}")
        print(f"Incomplete episodes: {summary['incomplete_episodes']}")
        print(f"Average duration: {summary['average_duration']:.2f} seconds")

        # Display each episode
        for episode in episodes:
            status = " (INCOMPLETE)" if episode.get('incomplete') else ""
            print(f"\nEpisode {episode['episode_number']}{status}:")
            print(f"  Time: {episode['start_time']:.2f}s - {episode['end_time']:.2f}s")
            print(f"  Duration: {episode['duration']:.2f}s")
            print(f"  Word count: {episode['word_count']}")
            print(f"  Transcript: {episode['transcript'][:100]}...")

        # Extract episode videos for testing (only if episodes found)
        if episodes:
            print(f"\nExtracting episode videos for testing...")
            extraction_result = extract_and_save_episodes(video_file, episodes, "test_episodes")
            print(f"Extracted {extraction_result['extracted_episodes']} complete episodes")
            print(f"Summary file: {extraction_result['summary_file']}")
            for file_path in extraction_result['extracted_files']:
                print(f"  - {file_path}")

        # Display database analytics
        print(f"\nDatabase Analytics:")
        analytics = db_client.get_analytics_summary()
        for key, value in analytics.items():
            print(f"  {key}: {value}")

        episode_analytics = db_client.get_episode_analytics()
        for key, value in episode_analytics.items():
            print(f"  {key}: {value}")

        # Display chunk information
        print(f"\nChunk Information:")
        for i, chunk in enumerate(chunk_results):
            print(f"Chunk {i + 1}: {chunk['chunk_start_time']:.1f}s - {chunk['chunk_start_time'] + chunk['chunk_duration']:.1f}s")

    except FileNotFoundError as e:
        print(f"Error: {e}")
    except Exception as e:
        print(f"Transcription error: {e}")
    finally:
        # Close database connection
        if 'db_client' in locals():
            db_client.close()
