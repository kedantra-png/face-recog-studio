export interface PerModelScore {
  model_type: string;
  scale: number | null;
  real_score: number;
  fake_score: number;
  latency_ms: number;
}

export interface BoundingBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface RecognitionSession {
  session_id: string;
  client_secret: string;
  nonce: string;
  ttl_seconds: number;
  expires_at: number;
}

export interface FrameQualityMetrics {
  blur_score: number;
  brightness: number;
  contrast: number;
  face_size_ratio: number;
  motion_stability: number;
  overall_score: number;
  usable: boolean;
  guidance_message: string;
}

export interface CandidateFrame {
  frame_b64: str;
  quality_score: number;
  blur_score: number;
}

export interface PersonMetadata {
  person_id?: string;
  person_name?: string;
  role?: string;
  department?: string;
  thumbnail_url?: string;
  enrollment_quality?: number;
}

export interface TopMatch {
  image_id: string;
  person_id: string;
  person_name: string;
  role: string;
  department: string;
  similarity_score: number;
  re_ranked_confidence: number;
  thumbnail_url: string;
}

export interface LatencyBreakdown {
  security_ms: number;
  quality_ms: number;
  anti_spoof_ms: number;
  alignment_ms: number;
  embedding_ms: number;
  qdrant_search_ms: number;
  total_ms: number;
}

export interface RecognitionResult {
  success: boolean;
  match_found: boolean;
  person_id?: string | null;
  person_metadata?: PersonMetadata | null;
  similarity_score: number;
  overall_confidence: number;
  anti_spoof_confidence?: number;
  face_quality_score?: number;
  detected_face_b64?: string;
  processing_time_ms?: LatencyBreakdown;
  queue_wait_time_ms?: number;
  top_matches: TopMatch[];
  recognition_status: 'MATCH_FOUND' | 'NO_MATCH' | 'POOR_QUALITY' | 'SPOOF_DETECTED' | 'REJECTED_SECURITY';
  message?: string;
  error?: string;
}


export interface BackendConfig {
  real_threshold: number;
  device_id: number;
  model_dir: string;
  available_models: string[];
  num_models: number;
  cors_origins: string[];
}

export interface RecognitionProgressEvent {
  stage: 'SESSION' | 'VALIDATING' | 'QUALITY_CHECK' | 'ANTI_SPOOFING' | 'ALIGNMENT' | 'EMBEDDING' | 'VECTOR_SEARCH' | 'RE_RANKING' | 'FINISHED' | 'POOR_QUALITY' | 'SPOOF_DETECTED';
  message: string;
  payload?: any;
}
