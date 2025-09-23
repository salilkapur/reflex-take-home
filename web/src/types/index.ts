export interface Video {
  id: string
  filename: string
  file_path: string
  file_size: number
  duration_seconds: number
  chunk_length_seconds: number
  total_chunks: number
  processing_status: 'pending' | 'processing' | 'completed' | 'failed'
  created_at: string
  updated_at: string
  processing_started_at?: string
  processing_completed_at?: string
  metadata?: Record<string, any>
  file_hash: string
  total_episodes: number
  successful_episodes: number
  failed_episodes: number
  not_classified_episodes: number
}

export interface Episode {
  id: string
  video_id: string
  episode_number: number
  start_time: number
  end_time: number
  duration: number
  transcript: string
  captions: string
  word_count: number
  created_at: string
  updated_at: string
  metadata?: {
    annotation?: {
      status: 'success' | 'failure' | 'not_classified'
      quality?: string
      notes?: string
    }
    annotated_at?: string
    [key: string]: any
  }
  video_file_path: string
  audio_file_path: string
  processing_time_seconds: number
  transcription_confidence: number
}

export interface Analytics {
  total_videos: number
  total_episodes: number
  successful_episodes: number
  failed_episodes: number
  not_classified_episodes: number
  avg_video_duration: number
  completed_videos: number
  pending_videos: number
  processing_videos: number
  failed_videos: number
}