'use client'

import { useState, useEffect, useRef } from 'react'
import { Video, Analytics, Episode } from '@/types'
import { Play, Clock, FileText, BarChart3, Calendar, TrendingUp, Users, Database, ArrowLeft, MessageSquare, Check, X, ChevronLeft, ChevronRight, Save } from 'lucide-react'

export default function HomePage() {
  const [videos, setVideos] = useState<Video[]>([])
  const [analytics, setAnalytics] = useState<Analytics | null>(null)
  const [episodes, setEpisodes] = useState<Episode[]>([])
  const [selectedVideo, setSelectedVideo] = useState<Video | null>(null)
  const [selectedEpisode, setSelectedEpisode] = useState<Episode | null>(null)
  const [currentView, setCurrentView] = useState<'videos' | 'episodes' | 'episode-detail'>('videos')
  const [loading, setLoading] = useState(true)
  const [episodesLoading, setEpisodesLoading] = useState(false)
  const [markingStatus, setMarkingStatus] = useState<'success' | 'failure' | null>(null)
  const markingTimeoutRef = useRef<NodeJS.Timeout | null>(null)
  const videoRef = useRef<HTMLVideoElement>(null)
  const [editingCaptions, setEditingCaptions] = useState(false)
  const [captionsText, setCaptionsText] = useState('')
  const [savingCaptions, setSavingCaptions] = useState(false)

  useEffect(() => {
    loadData()
  }, [])

  const loadData = async () => {
    try {
      // Load analytics and videos from API
      const [analyticsRes, videosRes] = await Promise.all([
        fetch('http://localhost:8000/api/analytics/summary'),
        fetch('http://localhost:8000/api/videos')
      ])

      const analyticsData = await analyticsRes.json()
      const videosData = await videosRes.json()

      console.log('Analytics data:', analyticsData)
      console.log('Videos data:', videosData)
      console.log('Setting analytics:', analyticsData.analytics)
      console.log('Setting videos:', videosData.videos)

      setAnalytics(analyticsData.analytics)
      setVideos(videosData.videos)
    } catch (error) {
      console.error('Failed to load data:', error)
    } finally {
      setLoading(false)
    }
  }

  const formatDuration = (seconds: number) => {
    const hours = Math.floor(seconds / 3600)
    const minutes = Math.floor((seconds % 3600) / 60)
    if (hours > 0) {
      return `${hours}h ${minutes}m`
    }
    return `${minutes}m`
  }

  const formatFileSize = (bytes: number) => {
    const sizes = ['B', 'KB', 'MB', 'GB']
    if (bytes === 0) return '0 B'
    const i = Math.floor(Math.log(bytes) / Math.log(1024))
    return Math.round(bytes / Math.pow(1024, i) * 100) / 100 + ' ' + sizes[i]
  }

  const getSuccessRate = (video: Video) => {
    if (!video.total_episodes || video.total_episodes === 0) return 0
    return Math.round((video.successful_episodes / video.total_episodes) * 100)
  }

  const loadEpisodes = async (videoId: string) => {
    setEpisodesLoading(true)
    try {
      const response = await fetch(`http://localhost:8000/api/videos/${videoId}/episodes`)
      const data = await response.json()
      setEpisodes(data.episodes || [])
    } catch (error) {
      console.error('Failed to load episodes:', error)
      setEpisodes([])
    } finally {
      setEpisodesLoading(false)
    }
  }

  const handleVideoClick = async (video: Video) => {
    setSelectedVideo(video)
    setCurrentView('episodes')
    await loadEpisodes(video.id)
  }

  const processVideo = async (filename: string) => {
    try {
      setLoading(true)
      const response = await fetch(`http://localhost:8000/api/videos/start-processing?filename=${encodeURIComponent(filename)}&chunk_length=15&max_chunks=10`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
      })

      if (response.ok) {
        const data = await response.json()
        console.log('Background processing started:', data)
        // Reload data to update video status immediately
        await loadData()

        // Start polling for status updates every 5 seconds
        const pollInterval = setInterval(async () => {
          await loadData()

          // Check if any video is still processing
          const videosRes = await fetch('http://localhost:8000/api/videos')
          const videosData = await videosRes.json()
          const hasProcessingVideos = videosData.videos.some((v: any) => v.processing_status === 'processing')

          if (!hasProcessingVideos) {
            clearInterval(pollInterval)
          }
        }, 5000)

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

  const handleBackToVideos = () => {
    setCurrentView('videos')
    setSelectedVideo(null)
    setSelectedEpisode(null)
    setEpisodes([])
  }

  const handleEpisodeClick = (episode: Episode) => {
    setSelectedEpisode(episode)
    setCurrentView('episode-detail')
  }

  const handleBackToEpisodes = () => {
    setCurrentView('episodes')
    setSelectedEpisode(null)
  }

  const markEpisodeAsSuccess = async () => {
    if (!selectedEpisode || markingStatus) return

    try {
      setMarkingStatus('success')
      console.log('Marking episode as success:', selectedEpisode.id)

      // Set a timeout to clear the marking status if it takes too long
      markingTimeoutRef.current = setTimeout(() => {
        console.log('Marking timeout - clearing status')
        setMarkingStatus(null)
      }, 10000) // 10 second timeout

      const response = await fetch(`http://localhost:8000/api/episodes/${selectedEpisode.id}/mark-success`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
      })

      console.log('Mark success response:', response.status, response.ok)

      if (response.ok) {
        console.log('Updating episode state...')
        const updatedEpisode = {
          ...selectedEpisode,
          metadata: {
            ...selectedEpisode.metadata,
            annotation: {
              status: 'success',
              quality: 'high',
              notes: 'Manually marked as success'
            },
            annotated_at: new Date().toISOString()
          }
        }
        setSelectedEpisode(updatedEpisode)

        // Update the episodes list without reloading from server
        setEpisodes(episodes.map(ep =>
          ep.id === selectedEpisode.id ? updatedEpisode : ep
        ))
        console.log('Episode updated successfully')
      } else {
        console.error('Failed to mark success:', await response.text())
      }
    } catch (error) {
      console.error('Failed to mark episode as success:', error)
    } finally {
      console.log('Clearing marking status')
      if (markingTimeoutRef.current) {
        clearTimeout(markingTimeoutRef.current)
        markingTimeoutRef.current = null
      }
      setMarkingStatus(null)
    }
  }

  const markEpisodeAsFailure = async () => {
    if (!selectedEpisode || markingStatus) return

    try {
      setMarkingStatus('failure')
      console.log('Marking episode as failure:', selectedEpisode.id)

      // Set a timeout to clear the marking status if it takes too long
      markingTimeoutRef.current = setTimeout(() => {
        console.log('Marking timeout - clearing status')
        setMarkingStatus(null)
      }, 10000) // 10 second timeout

      const response = await fetch(`http://localhost:8000/api/episodes/${selectedEpisode.id}/mark-failure`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
      })

      console.log('Mark failure response:', response.status, response.ok)

      if (response.ok) {
        console.log('Updating episode state...')
        const updatedEpisode = {
          ...selectedEpisode,
          metadata: {
            ...selectedEpisode.metadata,
            annotation: {
              status: 'failure',
              quality: 'low',
              notes: 'Manually marked as failure'
            },
            annotated_at: new Date().toISOString()
          }
        }
        setSelectedEpisode(updatedEpisode)

        // Update the episodes list without reloading from server
        setEpisodes(episodes.map(ep =>
          ep.id === selectedEpisode.id ? updatedEpisode : ep
        ))
        console.log('Episode updated successfully')
      } else {
        console.error('Failed to mark failure:', await response.text())
      }
    } catch (error) {
      console.error('Failed to mark episode as failure:', error)
    } finally {
      console.log('Clearing marking status')
      if (markingTimeoutRef.current) {
        clearTimeout(markingTimeoutRef.current)
        markingTimeoutRef.current = null
      }
      setMarkingStatus(null)
    }
  }

  const goToPreviousEpisode = () => {
    if (!selectedEpisode) return

    const currentIndex = episodes.findIndex(ep => ep.id === selectedEpisode.id)
    if (currentIndex > 0) {
      const previousEpisode = episodes[currentIndex - 1]
      console.log('Switching to previous episode:', previousEpisode.episode_number)
      setSelectedEpisode(previousEpisode)
      // Reset and play the video for the new episode
      setTimeout(() => {
        if (videoRef.current) {
          console.log('Loading previous episode video...')
          try {
            videoRef.current.load()
            // Wait for video to be ready before trying to play
            videoRef.current.addEventListener('canplay', () => {
              videoRef.current?.play().catch(e => console.log('Autoplay prevented:', e))
            }, { once: true })
          } catch (error) {
            console.error('Error loading previous episode:', error)
          }
        }
      }, 100)
    }
  }

  const goToNextEpisode = () => {
    if (!selectedEpisode) return

    const currentIndex = episodes.findIndex(ep => ep.id === selectedEpisode.id)
    if (currentIndex < episodes.length - 1) {
      const nextEpisode = episodes[currentIndex + 1]
      console.log('Switching to next episode:', nextEpisode.episode_number)
      setSelectedEpisode(nextEpisode)
      // Reset and play the video for the new episode
      setTimeout(() => {
        if (videoRef.current) {
          console.log('Loading next episode video...')
          try {
            videoRef.current.load()
            // Wait for video to be ready before trying to play
            videoRef.current.addEventListener('canplay', () => {
              videoRef.current?.play().catch(e => console.log('Autoplay prevented:', e))
            }, { once: true })
          } catch (error) {
            console.error('Error loading next episode:', error)
          }
        }
      }, 100)
    }
  }

  const getCurrentEpisodeIndex = () => {
    if (!selectedEpisode) return { current: 0, total: 0 }
    const currentIndex = episodes.findIndex(ep => ep.id === selectedEpisode.id)
    return { current: currentIndex + 1, total: episodes.length }
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

  // Set captions text when episode changes
  useEffect(() => {
    if (selectedEpisode) {
      setCaptionsText(selectedEpisode.captions || '')
      setEditingCaptions(false)
    }
  }, [selectedEpisode])

  const startEditingCaptions = () => {
    setEditingCaptions(true)
  }

  const cancelEditingCaptions = () => {
    setEditingCaptions(false)
    setCaptionsText(selectedEpisode?.captions || '')
  }

  const saveCaptions = async () => {
    if (!selectedEpisode) return

    try {
      setSavingCaptions(true)
      const response = await fetch(`http://localhost:8000/api/episodes/${selectedEpisode.id}/captions`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ captions: captionsText.trim() }),
      })

      if (response.ok) {
        // Update the episode locally
        const updatedEpisode = {
          ...selectedEpisode,
          captions: captionsText.trim()
        }
        setSelectedEpisode(updatedEpisode)

        // Update episodes list
        setEpisodes(episodes.map(ep =>
          ep.id === selectedEpisode.id ? updatedEpisode : ep
        ))

        setEditingCaptions(false)
      } else {
        console.error('Failed to save captions:', await response.text())
        alert('Failed to save captions')
      }
    } catch (error) {
      console.error('Error saving captions:', error)
      alert('Error saving captions')
    } finally {
      setSavingCaptions(false)
    }
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
              {(currentView === 'episodes' || currentView === 'episode-detail') && (
                <button
                  onClick={currentView === 'episodes' ? handleBackToVideos : handleBackToEpisodes}
                  className="glass rounded-2xl p-3 text-gray-700 hover:bg-white/80 transition-all"
                >
                  <ArrowLeft className="w-5 h-5" />
                </button>
              )}
              <div>
                <h1 className="text-3xl font-bold text-gray-900">
                  {currentView === 'videos'
                    ? 'Video Processing Dashboard'
                    : currentView === 'episodes'
                    ? `Episodes - ${selectedVideo?.filename}`
                    : `Episode ${selectedEpisode?.episode_number} - ${selectedVideo?.filename}`
                  }
                </h1>
                <p className="text-gray-600 mt-1">
                  {currentView === 'videos'
                    ? 'Manage and analyze your video collection'
                    : currentView === 'episodes'
                    ? `${episodes.length} episodes found`
                    : `${formatTime(selectedEpisode?.start_time || 0)} - ${formatTime(selectedEpisode?.end_time || 0)}`
                  }
                </p>
              </div>
            </div>
            <div className="flex items-center space-x-4">
              <button className="glass rounded-2xl px-6 py-3 text-gray-700 hover:bg-white/80 transition-all">
                <Database className="w-5 h-5 inline mr-2" />
                Export Data
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Analytics Cards - Show for videos view and episodes view */}
      {(currentView === 'videos' || currentView === 'episodes') && (
        <section className="px-8 mb-8">
          <div className="max-w-7xl mx-auto">
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {/* Success Rate Card */}
            <div className="glass rounded-3xl p-6 card-hover">
              <div className="flex items-center justify-center w-16 h-16 rounded-2xl mb-4"
                   style={{background: 'linear-gradient(135deg, #10b981 0%, #059669 100%)'}}>
                <div className="text-white text-2xl font-bold">
                  {currentView === 'videos'
                    ? (analytics ? Math.round((analytics.successful_episodes / analytics.total_episodes) * 100) || 0 : 0)
                    : selectedVideo ? getSuccessRate(selectedVideo) : 0
                  }%
                </div>
              </div>
              <h3 className="text-gray-600 text-sm font-medium mb-1">Success Rate</h3>
              <p className="text-gray-500 text-xs">
                {currentView === 'videos'
                  ? `${analytics?.successful_episodes || 0}/${analytics?.total_episodes || 0} episodes processed`
                  : `${selectedVideo?.successful_episodes || 0}/${selectedVideo?.total_episodes || 0} episodes processed`
                }
              </p>
            </div>

            {/* Total Videos/Episodes Card */}
            <div className="glass rounded-3xl p-6 card-hover">
              <h3 className="text-gray-900 text-sm font-medium mb-2">
                {currentView === 'videos' ? 'Total Videos' : 'Total Episodes'}
              </h3>
              <div className="text-3xl font-bold text-gray-900">
                {currentView === 'videos'
                  ? (analytics?.total_videos || 0)
                  : (selectedVideo?.total_episodes || 0)
                }
              </div>
            </div>

            {/* Processing Time/Video Duration Card */}
            <div className="glass rounded-3xl p-6 card-hover">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-gray-900 font-semibold">
                  {currentView === 'videos' ? 'Avg Duration' : 'Video Duration'}
                </h3>
                <TrendingUp className="w-5 h-5 text-gray-500" />
              </div>
              <div className="text-2xl font-bold text-gray-900 mb-1">
                {currentView === 'videos'
                  ? `${analytics ? Math.round(analytics.avg_video_duration / 60) : 0}`
                  : `${selectedVideo ? Math.round(selectedVideo.duration_seconds / 60) : 0}`
                }
                <span className="text-sm font-normal text-gray-500 ml-1">min</span>
              </div>
              <div className="flex items-center space-x-2 mt-4">
                <div className="w-2 h-2 rounded-full" style={{backgroundColor: '#8b5cf6'}}></div>
                <span className="text-xs text-gray-600">
                  {currentView === 'videos' ? 'Average' : 'Total'}
                </span>
                <span className="text-xs text-gray-500 ml-auto">
                  {currentView === 'videos' ? '85%' : formatFileSize(selectedVideo?.file_size || 0)}
                </span>
              </div>
            </div>
          </div>
        </div>
      </section>
      )}

      {/* Main Content Grid */}
      <section className="px-8 pb-8">
        <div className="max-w-7xl mx-auto">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-2xl font-bold text-gray-900">
              {currentView === 'videos' ? 'Video Collection' : 'Episodes'}
            </h2>
            <span className="text-gray-500">
              {currentView === 'videos' ? `${videos.length} videos` : `${episodes.length} episodes`}
            </span>
          </div>

          {(currentView === 'videos' ? loading : episodesLoading) ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="glass rounded-3xl p-6 animate-pulse">
                  <div className="h-4 bg-gray-300 rounded w-3/4 mb-4"></div>
                  <div className="h-3 bg-gray-300 rounded w-1/2 mb-2"></div>
                  <div className="h-3 bg-gray-300 rounded w-2/3"></div>
                </div>
              ))}
            </div>
          ) : currentView === 'videos' && videos.length === 0 ? (
            <div className="glass rounded-3xl p-12 text-center">
              <div className="w-16 h-16 rounded-3xl mx-auto mb-6 flex items-center justify-center"
                   style={{background: 'linear-gradient(135deg, #fb7185 0%, #f59e0b 100%)'}}>
                <FileText className="w-8 h-8 text-white" />
              </div>
              <h3 className="text-xl font-semibold text-gray-900 mb-2">No videos found</h3>
              <p className="text-gray-500">Videos from the data folder will appear here once they are processed.</p>
            </div>
          ) : currentView === 'episodes' && episodes.length === 0 ? (
            <div className="glass rounded-3xl p-12 text-center">
              <div className="w-16 h-16 rounded-3xl mx-auto mb-6 flex items-center justify-center"
                   style={{background: 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)'}}>
                <MessageSquare className="w-8 h-8 text-white" />
              </div>
              <h3 className="text-xl font-semibold text-gray-900 mb-2">No episodes found</h3>
              <p className="text-gray-500 mb-6">
                {selectedVideo?.processing_status === 'unprocessed'
                  ? 'This video hasn\'t been processed yet. Click "Process Video" to start transcription.'
                  : 'This video doesn\'t have any episodes yet or they haven\'t been processed.'
                }
              </p>
              <div className="flex justify-center space-x-4">
                <button
                  onClick={handleBackToVideos}
                  className="rounded-2xl px-6 py-3 text-white font-medium shadow-lg transition-all hover:shadow-xl"
                  style={{background: 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)'}}
                >
                  <ArrowLeft className="w-4 h-4 inline mr-2" />
                  Back to Videos
                </button>
                {selectedVideo?.processing_status === 'unprocessed' && (
                  <button
                    onClick={() => selectedVideo && processVideo(selectedVideo.filename)}
                    className="rounded-2xl px-6 py-3 text-white font-medium shadow-lg transition-all hover:shadow-xl"
                    style={{background: 'linear-gradient(135deg, #f59e0b 0%, #f97316 100%)'}}
                  >
                    <Play className="w-4 h-4 inline mr-2" />
                    Process Video
                  </button>
                )}
              </div>
            </div>
          ) : currentView === 'videos' ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {videos.map((video) => {
                const successRate = getSuccessRate(video)

                return (
                  <div
                    key={video.id}
                    className="glass rounded-3xl overflow-hidden card-hover cursor-pointer group"
                    onClick={() => handleVideoClick(video)}
                  >
                    {/* Header with gradient */}
                    <div
                      className="p-6 relative"
                      style={{background: 'linear-gradient(135deg, #e2e8f0 0%, #cbd5e1 50%, #94a3b8 100%)'}}
                    >
                      <div className="flex items-start justify-between mb-4">
                        <div className="flex-1">
                          <h3 className="font-semibold text-lg text-gray-900 truncate mb-2" title={video.filename}>
                            {video.filename}
                          </h3>
                          <div className="flex items-center space-x-3 text-sm text-gray-700">
                            <div className="flex items-center space-x-1">
                              <Clock className="w-3 h-3" />
                              <span>
                                {video.processing_status === 'unprocessed'
                                  ? 'Unknown'
                                  : formatDuration(video.duration_seconds)
                                }
                              </span>
                            </div>
                            <span>•</span>
                            <span>{formatFileSize(video.file_size)}</span>
                          </div>
                        </div>

                        <div className={`px-3 py-1 rounded-full text-xs font-medium ${
                          video.processing_status === 'completed'
                            ? 'bg-green-100 text-green-700'
                            : video.processing_status === 'processing'
                            ? 'bg-blue-100 text-blue-700'
                            : video.processing_status === 'failed'
                            ? 'bg-red-100 text-red-700'
                            : video.processing_status === 'unprocessed'
                            ? 'bg-orange-100 text-orange-700'
                            : 'bg-gray-100 text-gray-700'
                        }`}>
                          {video.processing_status}
                        </div>
                      </div>

                    </div>

                    {/* Stats */}
                    <div className="p-6">
                      <div className="grid grid-cols-3 gap-4 mb-4">
                        <div className="text-center">
                          <div className="text-xl font-bold text-blue-600">
                            {video.total_episodes || 0}
                          </div>
                          <div className="text-xs text-gray-500">Episodes</div>
                        </div>
                        <div className="text-center">
                          <div className="text-xl font-bold text-green-600">
                            {video.successful_episodes || 0}
                          </div>
                          <div className="text-xs text-gray-500">Success</div>
                        </div>
                        <div className="text-center">
                          <div className="text-xl font-bold text-red-600">
                            {video.failed_episodes || 0}
                          </div>
                          <div className="text-xs text-gray-500">Failed</div>
                        </div>
                      </div>

                      {/* Success rate progress */}
                      {video.total_episodes > 0 && (
                        <div className="space-y-2">
                          <div className="flex justify-between text-sm">
                            <span className="text-gray-600">Success Rate</span>
                            <span className="font-medium text-gray-900">{successRate}%</span>
                          </div>
                          <div className="w-full bg-gray-200 rounded-full h-2">
                            <div
                              className={`h-2 rounded-full transition-all duration-500 ${
                                successRate >= 80 ? 'bg-green-500' :
                                successRate >= 60 ? 'bg-yellow-500' : 'bg-red-500'
                              }`}
                              style={{ width: `${successRate}%` }}
                            ></div>
                          </div>
                        </div>
                      )}

                      {/* Tags */}
                      {video.metadata?.tags && Array.isArray(video.metadata.tags) && (
                        <div className="mt-4 pt-4 border-t border-gray-200">
                          <div className="flex flex-wrap gap-2">
                            {video.metadata.tags.slice(0, 3).map((tag: string, index: number) => (
                              <span
                                key={index}
                                className="px-2 py-1 bg-gray-100 text-gray-700 rounded-full text-xs"
                              >
                                {tag}
                              </span>
                            ))}
                            {video.metadata.tags.length > 3 && (
                              <span className="px-2 py-1 bg-gray-100 text-gray-500 rounded-full text-xs">
                                +{video.metadata.tags.length - 3}
                              </span>
                            )}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          ) : currentView === 'episodes' ? (
            // Episodes Grid
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {episodes.map((episode) => (
                <div
                  key={episode.id}
                  className="glass rounded-3xl overflow-hidden card-hover cursor-pointer group"
                  onClick={() => handleEpisodeClick(episode)}
                >
                  {/* Episode Header */}
                  <div
                    className="p-6 relative"
                    style={{background: 'linear-gradient(135deg, #ddd6fe 0%, #c7d2fe 50%, #bfdbfe 100%)'}}
                  >
                    <div className="flex items-start justify-between mb-4">
                      <div className="flex-1">
                        <h3 className="font-semibold text-lg text-gray-900 mb-2">
                          Episode {episode.episode_number}
                        </h3>
                        <div className="flex items-center space-x-3 text-sm text-gray-700">
                          <div className="flex items-center space-x-1">
                            <Clock className="w-3 h-3" />
                            <span>{formatTime(episode.start_time)} - {formatTime(episode.end_time)}</span>
                          </div>
                          <span>•</span>
                          <span>{formatTime(episode.duration)}</span>
                        </div>
                      </div>

                      {/* Classification Status - Only show if classified */}
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
                      <div className="w-12 h-12 bg-white/90 rounded-2xl flex items-center justify-center shadow-lg group-hover:scale-110 transition-transform">
                        <Play className="w-5 h-5 text-indigo-600 ml-0.5" />
                      </div>
                    </div>
                  </div>

                  {/* Episode Stats */}
                  <div className="p-6">
                    <div className="grid grid-cols-2 gap-4 mb-4">
                      <div className="text-center">
                        <div className="text-xl font-bold text-indigo-600">
                          {episode.word_count}
                        </div>
                        <div className="text-xs text-gray-500">Words</div>
                      </div>
                      <div className="text-center">
                        <div className="text-xl font-bold text-purple-600">
                          {Math.round(episode.transcription_confidence * 100)}%
                        </div>
                        <div className="text-xs text-gray-500">Confidence</div>
                      </div>
                    </div>

                    {/* Video Caption */}
                    <div className="mt-4 pt-4 border-t border-gray-200">
                      <h4 className="text-sm font-medium text-gray-900 mb-2">Caption</h4>
                      <p className="text-xs text-gray-500 italic">
                        Caption will be generated automatically...
                      </p>
                    </div>

                    {/* Classification */}
                    <div className="mt-4 pt-4 border-t border-gray-200">
                      <div className="flex items-center justify-between">
                        <span className="text-sm text-gray-600">Classification</span>
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
              ))}
            </div>
          ) : (
            // Episode Detail View
            <div className="flex items-center space-x-6">
              {/* Previous Episode Button */}
              <button
                onClick={goToPreviousEpisode}
                disabled={getCurrentEpisodeIndex().current <= 1}
                className="glass rounded-2xl p-4 hover:bg-white/80 transition-all disabled:opacity-30 disabled:cursor-not-allowed flex-shrink-0"
              >
                <ChevronLeft className="w-8 h-8 text-gray-700" />
              </button>

              {/* Main Episode Card */}
              <div className="glass rounded-3xl overflow-hidden flex-1">
                <div className="grid grid-cols-1 lg:grid-cols-2 min-h-[600px]">
                  {/* Video Player Section - Left Side */}
                  <div className="p-8 flex flex-col">
                    <div className="flex-1 bg-black rounded-2xl overflow-hidden relative">
                      {/* Video Player */}
                      {selectedEpisode ? (
                        <video
                          ref={videoRef}
                          key={selectedEpisode.id}
                          controls
                          className="w-full h-full object-contain"
                          poster=""
                          preload="metadata"
                          onLoadStart={() => console.log('Video load started')}
                          onCanPlay={() => console.log('Video can play')}
                          onError={(e) => {
                            console.error('Video error:', e)
                            console.error('Episode ID:', selectedEpisode.id)
                            console.error('Video source:', `http://localhost:8000/api/episodes/${selectedEpisode.id}/stream`)
                          }}
                          onLoadedData={() => console.log('Video data loaded')}
                          onAbort={() => console.log('Video loading aborted')}
                          onStalled={() => console.log('Video loading stalled')}
                        >
                          <source
                            src={`http://localhost:8000/api/episodes/${selectedEpisode.id}/stream`}
                            type="video/mp4"
                          />
                          Your browser does not support the video tag.
                        </video>
                      ) : (
                        <div className="w-full h-full flex items-center justify-center">
                          <div className="text-center">
                            <div className="w-20 h-20 bg-white/20 rounded-full flex items-center justify-center mx-auto mb-4">
                              <Play className="w-8 h-8 text-white ml-1" />
                            </div>
                            <p className="text-white/80 text-lg font-medium">No episode selected</p>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Metadata Section - Right Side */}
                  <div className="p-8 border-l border-gray-200/50">
                    <div className="space-y-6">
                    {/* Episode Info */}
                    <div>
                      <div className="flex items-center justify-between mb-2">
                        <h2 className="text-2xl font-bold text-gray-900">
                          Episode {selectedEpisode?.episode_number}
                        </h2>

                        {/* Episode Counter */}
                        <span className="text-sm text-gray-600">
                          {getCurrentEpisodeIndex().current} of {getCurrentEpisodeIndex().total}
                        </span>
                      </div>

                      <p className="text-gray-600 mb-2">
                        {selectedVideo?.filename}
                      </p>

                      {/* Classification Status */}
                      <div className="flex items-center justify-between mb-4 py-2 px-3 bg-gray-50 rounded-lg">
                        <span className="text-gray-600 text-sm">Classification</span>
                        <span className={`px-3 py-1 rounded-full text-sm font-medium ${
                          selectedEpisode?.metadata?.annotation?.status === 'success'
                            ? 'bg-emerald-100 text-emerald-700'
                            : selectedEpisode?.metadata?.annotation?.status === 'failure'
                            ? 'bg-red-100 text-red-700'
                            : 'bg-gray-100 text-gray-600'
                        }`}>
                          {selectedEpisode?.metadata?.annotation?.status === 'success'
                            ? 'Success'
                            : selectedEpisode?.metadata?.annotation?.status === 'failure'
                            ? 'Failure'
                            : 'Not Classified'
                          }
                        </span>
                      </div>

                      {/* Success/Failure Buttons */}
                      <div className="flex space-x-4">
                        <div
                          onClick={markEpisodeAsSuccess}
                          className={`glass rounded-2xl p-4 transition-all flex-1 ${
                            markingStatus ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'
                          } ${
                            selectedEpisode?.metadata?.annotation?.status === 'success'
                              ? 'bg-green-100 border-2 border-green-300 hover:bg-green-200'
                              : 'hover:bg-white/80'
                          }`}
                        >
                          <div className="text-center">
                            <div className={`text-2xl font-bold mb-1 ${
                              selectedEpisode?.metadata?.annotation?.status === 'success'
                                ? 'text-green-700'
                                : 'text-green-600'
                            }`}>
                              {markingStatus === 'success' ? (
                                <div className="w-6 h-6 mx-auto animate-spin rounded-full border-2 border-green-600 border-t-transparent"></div>
                              ) : (
                                <Check className="w-6 h-6 mx-auto" />
                              )}
                            </div>
                            <div className={`text-sm ${
                              selectedEpisode?.metadata?.annotation?.status === 'success'
                                ? 'text-green-800 font-semibold'
                                : 'text-gray-600'
                            }`}>
                              {markingStatus === 'success' ? 'Marking...' : 'Success'}
                              {selectedEpisode?.metadata?.annotation?.status === 'success' && markingStatus !== 'success' && ' ✓'}
                            </div>
                          </div>
                        </div>
                        <div
                          onClick={markEpisodeAsFailure}
                          className={`glass rounded-2xl p-4 transition-all flex-1 ${
                            markingStatus ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'
                          } ${
                            selectedEpisode?.metadata?.annotation?.status === 'failure'
                              ? 'bg-red-100 border-2 border-red-300 hover:bg-red-200'
                              : 'hover:bg-white/80'
                          }`}
                        >
                          <div className="text-center">
                            <div className={`text-2xl font-bold mb-1 ${
                              selectedEpisode?.metadata?.annotation?.status === 'failure'
                                ? 'text-red-700'
                                : 'text-red-600'
                            }`}>
                              {markingStatus === 'failure' ? (
                                <div className="w-6 h-6 mx-auto animate-spin rounded-full border-2 border-red-600 border-t-transparent"></div>
                              ) : (
                                <X className="w-6 h-6 mx-auto" />
                              )}
                            </div>
                            <div className={`text-sm ${
                              selectedEpisode?.metadata?.annotation?.status === 'failure'
                                ? 'text-red-800 font-semibold'
                                : 'text-gray-600'
                            }`}>
                              {markingStatus === 'failure' ? 'Marking...' : 'Failure'}
                              {selectedEpisode?.metadata?.annotation?.status === 'failure' && markingStatus !== 'failure' && ' ✓'}
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Stats Grid */}
                    <div className="grid grid-cols-1 gap-4">
                      <div className="glass rounded-2xl p-4">
                        <div className="text-center">
                          <div className="text-2xl font-bold text-blue-600">
                            {formatTime(selectedEpisode?.duration || 0)}
                          </div>
                          <div className="text-sm text-gray-600 mt-1">Duration</div>
                        </div>
                      </div>
                    </div>

                    {/* Captions */}
                    <div className="glass rounded-2xl p-6">
                      <div className="flex items-center justify-between mb-4">
                        <h3 className="text-lg font-semibold text-gray-900">Captions</h3>
                        {!editingCaptions && (
                          <button
                            onClick={startEditingCaptions}
                            className="text-sm text-blue-600 hover:text-blue-800 transition-colors"
                          >
                            Edit
                          </button>
                        )}
                      </div>

                      {editingCaptions ? (
                        <div className="space-y-4">
                          <textarea
                            value={captionsText}
                            onChange={(e) => setCaptionsText(e.target.value)}
                            className="w-full h-32 p-3 border border-gray-300 rounded-lg resize-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                            placeholder="Enter captions text..."
                          />
                          <div className="flex space-x-2 justify-end">
                            <button
                              onClick={cancelEditingCaptions}
                              className="px-4 py-2 text-sm text-gray-600 hover:text-gray-800 transition-colors"
                              disabled={savingCaptions}
                            >
                              Cancel
                            </button>
                            <button
                              onClick={saveCaptions}
                              disabled={savingCaptions}
                              className="flex items-center space-x-2 px-4 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                            >
                              {savingCaptions ? (
                                <div className="w-4 h-4 animate-spin rounded-full border-2 border-white border-t-transparent"></div>
                              ) : (
                                <Save className="w-4 h-4" />
                              )}
                              <span>{savingCaptions ? 'Saving...' : 'Save'}</span>
                            </button>
                          </div>
                        </div>
                      ) : (
                        <div className="bg-gray-50 rounded-lg p-4">
                          {selectedEpisode?.captions ? (
                            <p className="text-gray-800 text-sm whitespace-pre-wrap">
                              {selectedEpisode.captions}
                            </p>
                          ) : (
                            <p className="text-gray-500 text-sm italic text-center">
                              No captions available
                            </p>
                          )}
                        </div>
                      )}
                    </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Next Episode Button */}
              <button
                onClick={goToNextEpisode}
                disabled={getCurrentEpisodeIndex().current >= getCurrentEpisodeIndex().total}
                className="glass rounded-2xl p-4 hover:bg-white/80 transition-all disabled:opacity-30 disabled:cursor-not-allowed flex-shrink-0"
              >
                <ChevronRight className="w-8 h-8 text-gray-700" />
              </button>
            </div>
          )}
        </div>
      </section>
    </div>
  )
}
