// Video Episode Annotation Tool
class VideoAnnotationApp {
    constructor() {
        this.baseUrl = 'http://localhost:8000';
        this.currentVideo = null;
        this.currentEpisodes = [];
        this.currentEpisodeIndex = 0;
        this.init();
    }

    async init() {
        this.bindEvents();
        await this.loadAnalytics();
        await this.loadVideos();
    }

    bindEvents() {
        // Navigation events
        document.getElementById('refreshBtn').addEventListener('click', () => this.loadVideos());
        document.getElementById('backToListBtn').addEventListener('click', () => this.showVideoList());
        document.getElementById('episodeListBtn').addEventListener('click', () => this.showEpisodeList());
        document.getElementById('episodeViewerBtn').addEventListener('click', () => this.showEpisodeViewer());

        // Episode viewer navigation
        document.getElementById('prevEpisodeBtn').addEventListener('click', () => this.previousEpisode());
        document.getElementById('nextEpisodeBtn').addEventListener('click', () => this.nextEpisode());

        // Annotation events
        document.querySelectorAll('.annotation-btn').forEach(btn => {
            btn.addEventListener('click', (e) => this.selectAnnotation(e.target.dataset.status));
        });
        document.getElementById('saveAnnotationBtn').addEventListener('click', () => this.saveAnnotation());
    }

    async apiCall(endpoint, method = 'GET', body = null) {
        this.showLoading();
        try {
            const config = {
                method,
                headers: {
                    'Content-Type': 'application/json',
                }
            };

            if (body) {
                config.body = JSON.stringify(body);
            }

            const response = await fetch(`${this.baseUrl}${endpoint}`, config);
            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.detail || 'API request failed');
            }

            return data;
        } catch (error) {
            console.error('API Error:', error);
            this.showError(error.message);
            return null;
        } finally {
            this.hideLoading();
        }
    }

    async loadAnalytics() {
        const analytics = await this.apiCall('/api/analytics/summary');
        if (analytics) {
            document.getElementById('totalVideos').textContent = analytics.analytics.total_videos || 0;
            document.getElementById('totalEpisodes').textContent = analytics.analytics.total_episodes || 0;
            document.getElementById('completedVideos').textContent = analytics.analytics.completed_videos || 0;
        }
    }

    async loadVideos() {
        const videosResponse = await this.apiCall('/api/videos');
        if (videosResponse) {
            this.renderVideoGrid(videosResponse.videos);
        }
    }

    renderVideoGrid(videos) {
        const grid = document.getElementById('videoGrid');
        grid.innerHTML = '';

        videos.forEach(video => {
            const card = this.createVideoCard(video);
            grid.appendChild(card);
        });
    }

    createVideoCard(video) {
        const card = document.createElement('div');
        card.className = 'video-card';
        card.addEventListener('click', () => this.showVideoDetail(video));

        const statusClass = `status-${video.processing_status}`;
        const duration = this.formatDuration(video.duration_seconds);

        card.innerHTML = `
            <div class="video-card-header">
                <div>
                    <div class="video-title">${video.filename}</div>
                    <div class="video-duration">${duration}</div>
                </div>
                <span class="video-status ${statusClass}">${video.processing_status}</span>
            </div>
            <div class="video-stats">
                <div class="video-stat">
                    <span class="video-stat-value">${video.total_episodes || 0}</span>
                    <span class="video-stat-label">Episodes</span>
                </div>
                <div class="video-stat">
                    <span class="video-stat-value">${video.successful_episodes || 0}</span>
                    <span class="video-stat-label">Success</span>
                </div>
                <div class="video-stat">
                    <span class="video-stat-value">${video.failed_episodes || 0}</span>
                    <span class="video-stat-label">Failed</span>
                </div>
            </div>
        `;

        return card;
    }

    async showVideoDetail(video) {
        this.currentVideo = video;
        document.getElementById('videoTitle').textContent = video.filename;

        // Load episodes for this video
        const episodesResponse = await this.apiCall(`/api/videos/${video.id}/episodes`);
        if (episodesResponse) {
            this.currentEpisodes = episodesResponse.episodes;
            this.renderEpisodeList();
            this.showView('videoDetailView');
            this.showEpisodeList();
        }
    }

    renderEpisodeList() {
        const list = document.getElementById('episodeList');
        list.innerHTML = '';

        this.currentEpisodes.forEach((episode, index) => {
            const card = this.createEpisodeCard(episode, index);
            list.appendChild(card);
        });
    }

    createEpisodeCard(episode, index) {
        const card = document.createElement('div');
        card.className = 'episode-card';
        card.addEventListener('click', () => this.showEpisodeInViewer(index));

        const duration = this.formatDuration(episode.duration);
        const annotation = episode.metadata?.annotation;
        const statusClass = annotation ? (annotation.status === 'success' ? 'status-success' : 'status-failure') : 'status-unknown';
        const statusText = annotation ? annotation.status : 'Unknown';

        card.innerHTML = `
            <div class="episode-header">
                <span class="episode-number">Episode ${episode.episode_number}</span>
                <span class="episode-duration">${duration}</span>
            </div>
            <div class="episode-transcript">${episode.transcript}</div>
            <div class="episode-footer">
                <span class="episode-word-count">${episode.word_count} words</span>
                <span class="status-badge ${statusClass}">${statusText}</span>
            </div>
        `;

        return card;
    }

    showEpisodeInViewer(index) {
        this.currentEpisodeIndex = index;
        this.showEpisodeViewer();
        this.loadCurrentEpisode();
    }

    showView(viewId) {
        document.querySelectorAll('.view').forEach(view => view.classList.remove('active'));
        document.getElementById(viewId).classList.add('active');
    }

    showVideoList() {
        this.showView('videoListView');
    }

    showEpisodeList() {
        document.getElementById('episodeList').classList.remove('hidden');
        document.getElementById('episodeViewer').classList.add('hidden');
        document.getElementById('episodeListBtn').classList.add('btn-primary');
        document.getElementById('episodeListBtn').classList.remove('btn-outline');
        document.getElementById('episodeViewerBtn').classList.remove('btn-primary');
        document.getElementById('episodeViewerBtn').classList.add('btn-outline');
    }

    showEpisodeViewer() {
        document.getElementById('episodeList').classList.add('hidden');
        document.getElementById('episodeViewer').classList.remove('hidden');
        document.getElementById('episodeViewerBtn').classList.add('btn-primary');
        document.getElementById('episodeViewerBtn').classList.remove('btn-outline');
        document.getElementById('episodeListBtn').classList.remove('btn-primary');
        document.getElementById('episodeListBtn').classList.add('btn-outline');

        if (this.currentEpisodes.length > 0) {
            this.loadCurrentEpisode();
        }
    }

    loadCurrentEpisode() {
        if (!this.currentEpisodes[this.currentEpisodeIndex]) return;

        const episode = this.currentEpisodes[this.currentEpisodeIndex];

        // Update episode info
        document.getElementById('currentEpisodeTitle').textContent = `Episode ${episode.episode_number}`;
        document.getElementById('episodeDuration').textContent = this.formatDuration(episode.duration);
        document.getElementById('episodeWordCount').textContent = episode.word_count;
        document.getElementById('transcriptText').textContent = episode.transcript;

        // Update episode counter
        document.getElementById('episodeCounter').textContent =
            `Episode ${this.currentEpisodeIndex + 1} of ${this.currentEpisodes.length}`;

        // Update navigation buttons
        document.getElementById('prevEpisodeBtn').disabled = this.currentEpisodeIndex === 0;
        document.getElementById('nextEpisodeBtn').disabled = this.currentEpisodeIndex === this.currentEpisodes.length - 1;

        // Load annotation
        this.loadEpisodeAnnotation(episode);

        // Update status
        const annotation = episode.metadata?.annotation;
        const statusElement = document.getElementById('episodeStatus');
        if (annotation) {
            statusElement.textContent = annotation.status;
            statusElement.className = `status-badge ${annotation.status === 'success' ? 'status-success' : 'status-failure'}`;
        } else {
            statusElement.textContent = 'Unknown';
            statusElement.className = 'status-badge status-unknown';
        }

        // Note: Video playback would require serving video files from the API
        // For now, we'll just show a placeholder
        const videoElement = document.getElementById('episodeVideo');
        videoElement.src = ''; // Would need proper video serving endpoint
    }

    loadEpisodeAnnotation(episode) {
        const annotation = episode.metadata?.annotation;
        const currentAnnotationDiv = document.getElementById('currentAnnotation');
        const notesTextarea = document.getElementById('annotationNotes');

        // Reset annotation buttons
        document.querySelectorAll('.annotation-btn').forEach(btn => btn.classList.remove('active'));

        if (annotation) {
            // Show current annotation
            currentAnnotationDiv.innerHTML = `
                <div class="annotation-item">
                    <strong>Status:</strong> ${annotation.status}
                </div>
                <div class="annotation-item">
                    <strong>Quality:</strong> ${annotation.quality || 'Not specified'}
                </div>
                <div class="annotation-item">
                    <strong>Notes:</strong> ${annotation.notes || 'No notes'}
                </div>
                <div class="annotation-item">
                    <strong>Date:</strong> ${new Date(episode.metadata.annotated_at).toLocaleString()}
                </div>
            `;

            // Set active button
            const activeBtn = document.querySelector(`[data-status="${annotation.status}"]`);
            if (activeBtn) {
                activeBtn.classList.add('active');
            }

            // Load notes
            notesTextarea.value = annotation.notes || '';
        } else {
            currentAnnotationDiv.innerHTML = '<p>No annotation yet</p>';
            notesTextarea.value = '';
        }
    }

    selectAnnotation(status) {
        document.querySelectorAll('.annotation-btn').forEach(btn => btn.classList.remove('active'));
        document.querySelector(`[data-status="${status}"]`).classList.add('active');
        this.selectedAnnotationStatus = status;
    }

    async saveAnnotation() {
        const episode = this.currentEpisodes[this.currentEpisodeIndex];
        const notes = document.getElementById('annotationNotes').value;

        if (!this.selectedAnnotationStatus) {
            alert('Please select a status (Success or Failure)');
            return;
        }

        const annotation = {
            status: this.selectedAnnotationStatus,
            notes: notes,
            quality: this.selectedAnnotationStatus === 'success' ? 'good' : 'poor'
        };

        const result = await this.apiCall(`/api/episodes/${episode.id}/annotation`, 'PUT', annotation);

        if (result) {
            // Update local episode data
            if (!episode.metadata) episode.metadata = {};
            episode.metadata.annotation = annotation;
            episode.metadata.annotated_at = new Date().toISOString();

            // Refresh the current episode display
            this.loadCurrentEpisode();

            // Refresh episode list if visible
            if (!document.getElementById('episodeList').classList.contains('hidden')) {
                this.renderEpisodeList();
            }

            this.showSuccess('Annotation saved successfully!');
        }
    }

    previousEpisode() {
        if (this.currentEpisodeIndex > 0) {
            this.currentEpisodeIndex--;
            this.loadCurrentEpisode();
        }
    }

    nextEpisode() {
        if (this.currentEpisodeIndex < this.currentEpisodes.length - 1) {
            this.currentEpisodeIndex++;
            this.loadCurrentEpisode();
        }
    }

    formatDuration(seconds) {
        const minutes = Math.floor(seconds / 60);
        const remainingSeconds = Math.floor(seconds % 60);
        return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
    }

    showLoading() {
        document.getElementById('loadingOverlay').classList.remove('hidden');
    }

    hideLoading() {
        document.getElementById('loadingOverlay').classList.add('hidden');
    }

    showError(message) {
        // Simple alert for now - could be enhanced with a toast system
        alert(`Error: ${message}`);
    }

    showSuccess(message) {
        // Simple alert for now - could be enhanced with a toast system
        alert(message);
    }
}

// Initialize the app when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    new VideoAnnotationApp();
});