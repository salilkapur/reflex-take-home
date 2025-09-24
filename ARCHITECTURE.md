# Video Processing Platform - System Architecture

## Overview

This is an annotation platform designed to analyze videos containing structured content. The system automatically transcribes video audio, extracts discrete episodes based on delimiter words, and generates visual captions using advanced Vision Language Models. The architecture is modular to scale components independently.

## High-Level Architecture

```mermaid
graph TB
    subgraph "Presentation Layer"
        WEB[Next.js Frontend<br/>TypeScript + Tailwind]
    end

    subgraph "Gateway Layer"
        NGINX[Nginx Reverse Proxy<br/>Load Balancing + SSL]
    end

    subgraph "Application Layer"
        API[FastAPI Backend<br/>Async Python Services]
    end

    subgraph "AI Processing Layer"
        STT[Speech-to-Text<br/>OpenAI Whisper]
        VLM[Vision Language Model<br/>Google Gemini]
    end

    subgraph "Data Layer"
        DB[(Analytics Database<br/>ClickHouse)]
        STORAGE[Video Storage<br/>File System]
    end

    subgraph "Infrastructure"
        PM2[Process Management<br/>PM2 Ecosystem]
    end

    WEB --> NGINX
    NGINX --> API
    API --> STT
    API --> VLM
    API --> DB
    API --> STORAGE
    PM2 -.-> WEB
    PM2 -.-> API
```

## Architectural Design Principles

### Layered Architecture Pattern
The system follows a clean layered architecture with clear separation of concerns:

- **Presentation Layer**: React-based UI with server-side rendering
- **Gateway Layer**: Reverse proxy handling routing and SSL
- **Application Layer**: Business logic and API orchestration
- **AI Processing Layer**: External AI service integrations (OpenAI, Google Gemini)
- **Data Layer**: Persistent storage and analytics database

### Key Design Patterns

**Service-Oriented Architecture (SOA)**
- Microservice-like separation of video processing, episode management, and analytics
- Each service handles specific domain responsibilities
- Loose coupling between components

**Event-Driven Processing**
- Asynchronous video processing workflows
- Background task execution for resource-intensive operations
- Real-time status updates and progress tracking

**Connection Pooling**
- Database connection pool management for high-concurrency scenarios
- Configurable pool sizes and connection lifecycle management

**Caching Strategy**
- Intelligent caching of transcription results to avoid reprocessing
- Hash-based cache keys for video segments

## Video Processing Architecture

### Core Processing Pipeline

```mermaid
flowchart TD
    A[Video Upload] --> B[Metadata Extraction]
    B --> C[Chunking Strategy]
    C --> D[Parallel Audio Processing]
    D --> E[Transcription Aggregation]
    E --> F[Episode Detection Algorithm]
    F --> G[Data Persistence]
    G --> H[VLM Captioning Pipeline]

    subgraph "Chunking Layer"
        C1[Chunk 1<br/>0-600s]
        C2[Chunk 2<br/>600-1200s]
        CN[Chunk N<br/>...]
    end

    subgraph "AI Processing"
        T1[Whisper API]
        T2[Whisper API]
        TN[Whisper API]
    end

    subgraph "Episode Extraction"
        EP1[Episode Detection]
        EP2[Boundary Validation]
        EP3[Cross-chunk Handling]
    end

    C --> C1
    C --> C2
    C --> CN

    C1 --> T1
    C2 --> T2
    CN --> TN

    T1 --> EP1
    T2 --> EP1
    TN --> EP1

    EP1 --> EP2
    EP2 --> EP3
    EP3 --> F
```

### Video Chunking Strategy

The system employs an intelligent chunking strategy to handle videos of arbitrary length while maintaining processing efficiency and memory constraints.

```mermaid
gantt
    title Video Chunking Timeline (90-minute video example)
    dateFormat X
    axisFormat %M:%S

    section Audio Extraction
    Chunk 1 (0-10min)      :chunk1, 0, 600
    Chunk 2 (10-20min)     :chunk2, 600, 600
    Chunk 3 (20-30min)     :chunk3, 1200, 600
    Chunk 4 (30-40min)     :chunk4, 1800, 600
    Chunk 5 (40-50min)     :chunk5, 2400, 600

    section Transcription
    Whisper API Call 1     :whisper1, 0, 200
    Whisper API Call 2     :whisper2, 600, 200
    Whisper API Call 3     :whisper3, 1200, 200
    Whisper API Call 4     :whisper4, 1800, 200
    Whisper API Call 5     :whisper5, 2400, 200

    section Processing
    Timestamp Adjustment   :timestamp, 1000, 500
    Episode Detection      :episode, 1500, 800
    Database Storage       :storage, 2300, 200
```

### Episode Extraction Algorithm

The core innovation lies in the intelligent episode detection algorithm that can handle delimiter words spanning across multiple chunks.

```mermaid
flowchart TD
    A[Combined Word Timeline] --> B{Scan for 'start'}
    B -->|Found| C[Mark Episode Start]
    B -->|Not Found| D[Continue Scanning]
    C --> E{Scan for 'finish'}
    E -->|Found| F[Complete Episode]
    E -->|Not Found| G{End of Chunk?}
    G -->|Yes| H[Incomplete Episode Flag]
    G -->|No| I[Continue in Current Chunk]
    F --> J[Save Episode to Database]
    H --> K[Continue in Next Chunk]
    D --> B
    I --> E
    K --> E
    J --> B

    subgraph "Episode Validation"
        L[Check Duration]
        M[Validate Word Count]
        N[Cross-reference Timestamps]
    end

    F --> L
    L --> M
    M --> N
    N --> J
```

### Cross-Chunk Episode Handling

One of the most complex architectural challenges is handling episodes that span multiple processing chunks.

```mermaid
timeline
    title Episode Boundary Management

    section Chunk 1 (0-600s)
        Audio Transcript : Word timestamps
                        : "start project alpha..."
                        : No "finish" found

    section Chunk 2 (600-1200s)
        Audio Transcript : Continuing episode
                        : "...implementation complete"
                        : "finish project alpha"
                        : Episode boundary detected

    section Episode Assembly
        Timestamp Merge  : Adjust all timestamps to global timeline
        Boundary Validation : Confirm start/finish pair integrity
        Episode Creation : Generate complete episode record
```

## Data Architecture

### Database Design (ClickHouse)

The system uses ClickHouse as its primary database due to its exceptional performance with time-series data, analytics queries, and JSON metadata support.

```mermaid
erDiagram
    VIDEOS {
        String id PK
        String filename
        String file_path
        UInt64 file_size
        Float64 duration_seconds
        Enum processing_status
        String metadata
        DateTime created_at
    }

    EPISODES {
        String id PK
        String video_id FK
        UInt32 episode_number
        Float64 start_time
        Float64 end_time
        String transcript
        String captions
        String metadata
    }

    PROCESSING_CHUNKS {
        String id PK
        String video_id FK
        UInt32 chunk_number
        Float64 start_time
        Float64 end_time
        String cache_key
        UInt8 cache_hit
    }

    VIDEOS ||--o{ EPISODES : contains
    VIDEOS ||--o{ PROCESSING_CHUNKS : processed_as
```

### Connection Architecture
- **Connection Pooling**: Thread-safe connection pool with configurable size limits
- **Query Optimization**: Async query execution with timeout handling
- **Analytics Optimization**: Specialized queries for dashboard metrics

## Vision Language Model Integration

### VLM Architecture Pattern

The system integrates Google Gemini VLM to generate visual captions for extracted video episodes, providing a complete multimodal understanding of the content.

```mermaid
sequenceDiagram
    participant UI as Frontend
    participant API as Backend API
    participant VLM as Episode Captioner
    participant FFmpeg as Video Processor
    participant Gemini as Google Gemini VLM
    participant Storage as File Storage

    UI->>API: Trigger Episode Captioning
    API->>Storage: Retrieve Episodes without Captions

    loop For Each Episode
        API->>VLM: Process Episode
        VLM->>FFmpeg: Extract Video Segment
        FFmpeg-->>VLM: Video Segment File
        VLM->>Gemini: Upload + Vision Prompt

        Note over Gemini: "Provide detailed but concise<br/>caption for this video.<br/>Describe objects and actions."

        Gemini-->>VLM: Generated Caption
        VLM->>Storage: Update Episode Record
        VLM-->>API: Processing Status
    end

    API-->>UI: Captioning Complete
```

### VLM Processing Strategy

**Smart Episode Selection:**
- Skip episodes with existing captions
- Prioritize recent or high-importance episodes
- Batch processing with rate limiting

**Error Resilience:**
- Automatic retry mechanisms
- Fallback handling for API failures
- Graceful degradation when VLM unavailable

**Resource Management:**
- Temporary file cleanup
- Memory-efficient video segment processing
- API quota management

## API Design

### RESTful Architecture

The system follows RESTful principles with clear resource-oriented endpoints:

| Resource | Operations | Purpose |
|----------|------------|---------|
| **Videos** | GET, POST | Video management and processing |
| **Episodes** | GET, PUT | Episode retrieval and annotation |
| **Analytics** | GET | System metrics and insights |
| **Captioning** | POST | VLM visual caption generation |

### API Characteristics

- **Async Processing**: Long-running operations handled via background tasks
- **Pagination Support**: Efficient data retrieval for large datasets
- **Status Tracking**: Real-time processing status updates
- **Error Handling**: Comprehensive error responses with actionable messages

## Performance & Scalability

### Architectural Optimizations

**Connection Pool Management**
- Thread-safe database connection pooling
- Configurable pool sizes and connection lifecycles
- Automatic connection cleanup and recovery

**Intelligent Caching Strategy**
- Hash-based cache keys for transcription segments
- Avoid reprocessing identical video chunks
- Memory-efficient cache management

**Asynchronous Processing**
- Background task execution for CPU-intensive operations
- Non-blocking API responses
- Real-time status updates through database polling

### Scalability Design

**Horizontal Scaling Capabilities**
- Stateless API design enables load balancing
- ClickHouse supports distributed clustering
- Configurable storage backends (local, cloud)

**Resource Management**
- Chunked processing prevents memory overflow
- Configurable processing limits
- Smart episode selection for VLM processing

## Technology Stack Overview

| Layer | Technology | Key Benefits |
|-------|------------|--------------|
| **Frontend** | Next.js, TypeScript | Server-side rendering, type safety |
| **Backend** | FastAPI, Python | High performance async API |
| **Database** | ClickHouse | Analytics-optimized, time-series data |
| **AI/ML** | OpenAI Whisper, Google Gemini | Speech-to-text, vision understanding |
| **Infrastructure** | Nginx, PM2, Docker-ready | Production scalability |

## Architectural Design Choices

### Intelligent Episode Detection
- **Cross-chunk Boundary Handling**: Episodes can span multiple processing chunks
- **Incomplete Episode Management**: Handles missing start/end delimiters gracefully
- **Timestamp Synchronization**: Maintains accurate timing across chunk boundaries

### Multimodal AI Integration
- **Dual AI Pipeline**: Combines audio transcription with visual understanding
- **Smart Processing**: Skip logic prevents redundant VLM processing
- **Resource Optimization**: Efficient video segment extraction and cleanup

### Scalable Data Architecture
- **Caching Strategy**: Hash-based transcription result caching
- **Analytics Optimization**: ClickHouse enables complex real-time queries

## Future Architecture Considerations

**Scalability Enhancements:**
- Message queue integration (Redis/RabbitMQ) for new video or asynchronous episode processing
- Cloud storage abstraction layer

**Dataset Management:**
- Materialize episodes into individual video files
- Add motor sequences with each episode and create a multimodal dataset
- For each episode assign tags for filtering or training on specific events/episodes

**Analytics/Enrichment:**
- Assign episode quality (blurry video, incomplete video)

**Operational Excellence:**
- Comprehensive monitoring and alerting
- Performance metrics and optimization
