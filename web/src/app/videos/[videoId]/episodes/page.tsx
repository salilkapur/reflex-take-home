'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { useParams } from 'next/navigation'
import { Video, Episode } from '@/types'
import { Play, Clock, ArrowLeft, MessageSquare, TrendingUp, AlertTriangle, Camera } from 'lucide-react'
import { API_ENDPOINTS } from '@/config/api'

export default function EpisodesPage() {
  const params = useParams()
  const videoId = params.videoId as string

  const [video, setVideo] = useState<Video | null>(null)
  const [episodes, setEpisodes] = useState<Episode[]>([])
  const [loading, setLoading] = useState(true)
  const [captioning, setCaptioning] = useState(false)

  useEffect(() => {
    if (videoId) {
      const controller = new AbortController()
      loadData(controller.signal)

      return () => {
        controller.abort()
      }
    }
  }, [videoId])

  const loadData = async (signal?: AbortSignal) => {
    try {
      // Load episodes first, then get video info from episodes response or fallback
      const episodesRes = await fetch(API_ENDPOINTS.videoEpisodes(videoId), { signal })

      if (signal?.aborted) return

      if (!episodesRes.ok) {
        throw new Error('Failed to fetch episodes')
      }

      const episodesData = await episodesRes.json()

      if (signal?.aborted) return

      setEpisodes(episodesData.episodes || [])

      // Try to get video info from the first episode or fetch all videos as fallback
      if (episodesData.episodes?.length > 0) {
        // If we have episodes, we can get video info from the episode
        const firstEpisode = episodesData.episodes[0]
        setVideo({
          id: videoId,
          filename: firstEpisode.video_file_path ? firstEpisode.video_file_path.split('/').pop() : 'Unknown',
          processing_status: 'completed', // If episodes exist, video is processed
          duration_seconds: firstEpisode.duration || 0,
          file_size: 0 // Not available from episode data
        } as Video)
      } else {
        // Fallback: fetch all videos to find this one (only if no episodes)
        const videosRes = await fetch(API_ENDPOINTS.videos, { signal })
        if (videosRes.ok && !signal?.aborted) {
          const videosData = await videosRes.json()
          const selectedVideo = videosData.videos.find((v: Video) => v.id === videoId)
          setVideo(selectedVideo || null)
        }
      }
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') {
        console.log('Request cancelled')
        return
      }
      console.error('Failed to load data:', error)
      setVideo(null)
      setEpisodes([])
    } finally {
      if (!signal?.aborted) {
        setLoading(false)
      }
    }
  }

  const formatTime = (seconds: number) => {
    const hours = Math.floor(seconds / 3600)
    const minutes = Math.floor((seconds % 3600) / 60)
    const remainingSeconds = Math.floor(seconds % 60)

    if (hours > 0) {
      return `${hours}:${minutes.toString().padStart(2, '0')}:${remainingSeconds.toString().padStart(2, '0')}`
    }
    return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`
  }


  const processVideo = async (filename: string) => {
    try {
      setLoading(true)
      const response = await fetch(API_ENDPOINTS.startProcessing(filename, 15), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
      })

      if (response.ok) {
        const data = await response.json()
        console.log('Background processing started:', data)

        // Start simple polling - just refresh data periodically
        const pollInterval = setInterval(async () => {
          try {
            await loadData() // No signal for polling
            // If video exists and is not processing, stop polling
            if (video && video.processing_status !== 'processing') {
              clearInterval(pollInterval)
            }
          } catch (error) {
            console.error('Polling error:', error)
            clearInterval(pollInterval)
          }
        }, 5000)

        // Stop polling after 5 minutes to prevent infinite polling
        setTimeout(() => {
          clearInterval(pollInterval)
        }, 300000)
      } else {
        const errorData = await response.json()
        console.error('Failed to start processing:', errorData.detail)
        alert(`Failed to start processing: ${errorData.detail}`)
      }
    } catch (error) {
      console.error('Error starting video processing:', error)
      alert('Error starting video processing')
    } finally {
      setLoading(false)
    }
  }

  const captionEpisodes = async () => {
    try {
      setCaptioning(true)
      console.log('Starting episode captioning for video:', videoId)

      const response = await fetch(API_ENDPOINTS.captionEpisodes(videoId), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
      })

      if (response.ok) {
        const data = await response.json()
        console.log('Caption result:', data)

        // Show result to user
        console.log(`Captioning completed! Processed: ${data.processed}, Skipped: ${data.skipped}${data.errors?.length ? `, Errors: ${data.errors.length}` : ''}`)

        // Refresh episodes to show updated captions
        await loadData()
      } else {
        const errorData = await response.json()
        console.error('Failed to caption episodes:', errorData)
      }
    } catch (error) {
      console.error('Error captioning episodes:', error)
    } finally {
      setCaptioning(false)
    }
  }

  if (!video && !loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-gray-900 mb-4">Video not found</h1>
          <Link href="/videos" className="text-blue-600 hover:text-blue-800">
            Back to Videos
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen" style={{
      background: 'linear-gradient(135deg, #f8fafc 0%, #f1f5f9 30%, #e2e8f0 70%, #f0f9ff 100%)'
    }}>
      {/* Header */}
      <header className="relative px-8 py-6">
        <div className="max-w-7xl mx-auto">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-4">
              <Link
                href="/videos"
                className="glass rounded-2xl p-3 text-gray-700 hover:bg-white/80 transition-all"
              >
                <ArrowLeft className="w-5 h-5" />
              </Link>
              <div>
                <h1 className="text-3xl font-bold text-gray-900">
                  Episodes - {video?.filename}
                </h1>
                <p className="text-gray-600 mt-1">
                  {episodes.length} episodes found
                </p>
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* Analytics Cards */}
      <section className="px-8 mb-8">
        <div className="max-w-7xl mx-auto">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            {/* Episodes Count Card */}
            <div className="glass rounded-3xl p-6 card-hover">
              <div className="flex items-center justify-center w-16 h-16 rounded-2xl mb-4"
                   style={{background: 'linear-gradient(135deg, #10b981 0%, #059669 100%)'}}>
                <div className="text-white text-2xl font-bold">
                  {episodes.length}
                </div>
              </div>
              <h3 className="text-gray-600 text-sm font-medium mb-1">Total Episodes</h3>
              <p className="text-gray-500 text-xs">
                {episodes.length} episodes found
              </p>
            </div>

            {/* Complete Episodes Card */}
            <div className="glass rounded-3xl p-6 card-hover">
              <div className="flex items-center justify-center w-16 h-16 rounded-2xl mb-4"
                   style={{background: 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)'}}>
                <div className="text-white text-2xl font-bold">
                  {episodes.filter(ep => !ep.incomplete).length}
                </div>
              </div>
              <h3 className="text-gray-600 text-sm font-medium mb-1">Complete Episodes</h3>
              <p className="text-gray-500 text-xs">
                Episodes with proper delimiters
              </p>
            </div>

            {/* Incomplete Episodes Card */}
            <div className="glass rounded-3xl p-6 card-hover">
              <div className="flex items-center justify-center w-16 h-16 rounded-2xl mb-4"
                   style={{background: 'linear-gradient(135deg, #f59e0b 0%, #f97316 100%)'}}>
                <div className="text-white text-2xl font-bold">
                  {episodes.filter(ep => ep.incomplete).length}
                </div>
              </div>
              <h3 className="text-gray-600 text-sm font-medium mb-1">Incomplete Episodes</h3>
              <p className="text-gray-500 text-xs">
                Episodes missing delimiters
              </p>
            </div>

            {/* Processing Status Card */}
            <div className="glass rounded-3xl p-6 card-hover">
              <div className="flex items-center justify-center w-16 h-16 rounded-2xl mb-4"
                   style={{background: 'linear-gradient(135deg, #8b5cf6 0%, #7c3aed 100%)'}}>
                <TrendingUp className="w-8 h-8 text-white" />
              </div>
              <h3 className="text-gray-600 text-sm font-medium mb-1">Processing Status</h3>
              <p className="text-gray-500 text-xs">
                {video?.processing_status || 'Unknown'}
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Episodes Grid */}
      <section className="px-8 pb-8">
        <div className="max-w-7xl mx-auto">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-2xl font-bold text-gray-900">Episodes</h2>
            <div className="flex items-center gap-4">
              <span className="text-gray-500">{episodes.length} episodes</span>
              {episodes.length > 0 && (
                <button
                  onClick={captionEpisodes}
                  disabled={captioning}
                  className="rounded-2xl px-4 py-2 text-white font-medium shadow-lg transition-all hover:shadow-xl disabled:opacity-50 disabled:cursor-not-allowed"
                  style={{background: 'linear-gradient(135deg, #8b5cf6 0%, #7c3aed 100%)'}}
                >
                  <Camera className="w-4 h-4 inline mr-2" />
                  {captioning ? 'Captioning...' : 'Caption Episodes'}
                </button>
              )}
            </div>
          </div>

          {loading ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="glass rounded-3xl p-6 animate-pulse">
                  <div className="h-4 bg-gray-300 rounded w-3/4 mb-4"></div>
                  <div className="h-3 bg-gray-300 rounded w-1/2 mb-2"></div>
                  <div className="h-3 bg-gray-300 rounded w-2/3"></div>
                </div>
              ))}
            </div>
          ) : episodes.length === 0 ? (
            <div className="glass rounded-3xl p-12 text-center">
              <div className="w-16 h-16 rounded-3xl mx-auto mb-6 flex items-center justify-center"
                   style={{background: 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)'}}>
                <MessageSquare className="w-8 h-8 text-white" />
              </div>
              <h3 className="text-xl font-semibold text-gray-900 mb-2">No episodes found</h3>
              <p className="text-gray-500 mb-6">
                {video?.processing_status === 'unprocessed'
                  ? 'This video hasn\'t been processed yet. Click "Process Video" to start transcription.'
                  : video?.processing_status === 'failed'
                  ? 'Video processing failed. Click "Reprocess Video" to try again.'
                  : 'This video doesn\'t have any episodes yet or they haven\'t been processed.'
                }
              </p>
              <div className="flex justify-center space-x-4">
                <Link
                  href="/videos"
                  className="rounded-2xl px-6 py-3 text-white font-medium shadow-lg transition-all hover:shadow-xl"
                  style={{background: 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)'}}
                >
                  <ArrowLeft className="w-4 h-4 inline mr-2" />
                  Back to Videos
                </Link>
                {(video?.processing_status === 'unprocessed' || video?.processing_status === 'failed') && (
                  <button
                    onClick={() => video && processVideo(video.filename)}
                    className="rounded-2xl px-6 py-3 text-white font-medium shadow-lg transition-all hover:shadow-xl"
                    style={{background: 'linear-gradient(135deg, #f59e0b 0%, #f97316 100%)'}}
                  >
                    <Play className="w-4 h-4 inline mr-2" />
                    {video?.processing_status === 'failed' ? 'Reprocess Video' : 'Process Video'}
                  </button>
                )}
              </div>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {episodes.map((episode) => (
                <Link
                  key={episode.id}
                  href={`/videos/${videoId}/episodes/${episode.id}`}
                  className="glass rounded-3xl overflow-hidden card-hover cursor-pointer group block"
                >
                  {/* Episode Header */}
                  <div
                    className="p-6 relative"
                    style={{
                      background: episode.incomplete
                        ? 'linear-gradient(135deg, #fed7d7 0%, #fbb6ce 50%, #f9a8d4 100%)'
                        : 'linear-gradient(135deg, #ddd6fe 0%, #c7d2fe 50%, #bfdbfe 100%)'
                    }}
                  >
                    <div className="flex items-start justify-between mb-4">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-2">
                          <h3 className="font-semibold text-lg text-gray-900">
                            Episode {episode.episode_number}
                          </h3>
                          {episode.incomplete && (
                            <div className="flex items-center gap-1 px-2 py-1 bg-orange-100 text-orange-700 rounded-full text-xs font-medium">
                              <AlertTriangle className="w-3 h-3" />
                              <span>Incomplete</span>
                            </div>
                          )}
                        </div>
                        <div className="flex items-center space-x-3 text-sm text-gray-700">
                          <div className="flex items-center space-x-1">
                            <Clock className="w-3 h-3" />
                            <span>{formatTime(episode.start_time)} - {formatTime(episode.end_time)}</span>
                          </div>
                          <span>•</span>
                          <span>{formatTime(episode.duration)}</span>
                        </div>
                      </div>

                      {/* Classification Status */}
                      {episode.metadata?.annotation?.status && (
                        <div className={`px-3 py-1 rounded-full text-xs font-medium ${
                          episode.metadata?.annotation?.status === 'success'
                            ? 'bg-emerald-100 text-emerald-700'
                            : 'bg-red-100 text-red-700'
                        }`}>
                          {episode.metadata?.annotation?.status === 'success' ? 'Success' : 'Failure'}
                        </div>
                      )}
                    </div>

                    {/* Play button */}
                    <div className="absolute bottom-4 right-6">
                      <div className={`w-12 h-12 bg-white/90 rounded-2xl flex items-center justify-center shadow-lg group-hover:scale-110 transition-transform ${
                        episode.incomplete ? 'ring-2 ring-orange-300' : ''
                      }`}>
                        {episode.incomplete ? (
                          <AlertTriangle className="w-5 h-5 text-orange-600" />
                        ) : (
                          <Play className="w-5 h-5 text-indigo-600 ml-0.5" />
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Episode Stats */}
                  <div className="p-6">
                    {episode.incomplete && (
                      <div className="mb-4 p-3 bg-orange-50 border border-orange-200 rounded-xl">
                        <div className="flex items-center gap-2 text-orange-700">
                          <AlertTriangle className="w-4 h-4" />
                          <span className="text-sm font-medium">This episode is incomplete</span>
                        </div>
                        <p className="text-xs text-orange-600 mt-1">
                          Missing start or end delimiter in the transcript
                        </p>
                      </div>
                    )}

                    <div className="grid grid-cols-2 gap-4 mb-4">
                      <div className="text-center">
                        <div className={`text-xl font-bold ${
                          episode.incomplete ? 'text-orange-600' : 'text-indigo-600'
                        }`}>
                          {episode.word_count}
                        </div>
                        <div className="text-xs text-gray-500">Words</div>
                      </div>
                      <div className="text-center">
                        <div className={`text-xl font-bold ${
                          episode.incomplete ? 'text-orange-600' : 'text-purple-600'
                        }`}>
                          {Math.round(episode.transcription_confidence * 100)}%
                        </div>
                        <div className="text-xs text-gray-500">Confidence</div>
                      </div>
                    </div>

                    {/* Classification */}
                    <div className="mt-4 pt-4 border-t border-gray-200">
                      <div className="flex items-center justify-between">
                        <span className="text-sm text-gray-600">Status</span>
                        <div className="flex gap-2">
                          {episode.incomplete && (
                            <span className="px-2 py-1 rounded-full text-xs font-medium bg-orange-100 text-orange-700">
                              Incomplete
                            </span>
                          )}
                          <span className={`px-3 py-1 rounded-full text-sm font-medium ${
                            episode.metadata?.annotation?.status === 'success'
                              ? 'bg-emerald-100 text-emerald-700'
                              : episode.metadata?.annotation?.status === 'failure'
                              ? 'bg-red-100 text-red-700'
                              : 'bg-gray-100 text-gray-600'
                          }`}>
                            {episode.metadata?.annotation?.status === 'success'
                              ? 'Success'
                              : episode.metadata?.annotation?.status === 'failure'
                              ? 'Failure'
                              : 'Not Classified'
                            }
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </div>
      </section>
    </div>
  )
}