const getApiBaseUrl = (): string => {
  // Check if we're in the browser
  if (typeof window !== 'undefined') {
    // Browser environment - check hostname
    const hostname = window.location.hostname

    if (hostname === 'localhost' || hostname === '127.0.0.1') {
      return 'http://localhost:8000'
    } else {
      return `http://${hostname}:8000`
    }
  }

  // Server-side rendering - use environment variable or default to localhost
  return process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000'
}

export const API_BASE_URL = getApiBaseUrl()

export const API_ENDPOINTS = {
  videos: `${API_BASE_URL}/api/videos`,
  analytics: `${API_BASE_URL}/api/analytics/summary`,
  videoEpisodes: (videoId: string) => `${API_BASE_URL}/api/videos/${videoId}/episodes`,
  episodeDetail: (videoId: string, episodeId: string) => `${API_BASE_URL}/api/episodes/${episodeId}`,
  startProcessing: (filename: string, chunkLength: number = 15, maxChunks: number | null = null) =>
    `${API_BASE_URL}/api/videos/start-processing?filename=${encodeURIComponent(filename)}&chunk_length=${chunkLength}${maxChunks ? `&max_chunks=${maxChunks}` : ''}`,
  videoStream: (videoId: string, episodeId: string) => `${API_BASE_URL}/api/episodes/${episodeId}/stream`,
  updateAnnotation: (videoId: string, episodeId: string) => `${API_BASE_URL}/api/episodes/${episodeId}/annotation`,
  updateCaptions: (videoId: string, episodeId: string) => `${API_BASE_URL}/api/episodes/${episodeId}/captions`,
  captionEpisodes: (videoId: string) => `${API_BASE_URL}/api/videos/${videoId}/episodes/caption`
}