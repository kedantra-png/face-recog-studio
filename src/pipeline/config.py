# -*- coding: utf-8 -*-
"""
Pipeline Central Configuration Module
-------------------------------------
Loads environment variables and system parameters for the Image Upload,
Quality Assessment, InsightFace Embedding, MongoDB, Qdrant gRPC, and Google Drive pipeline.
"""

import os
from pydantic import Field
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Ensure .env environment variables are loaded
load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"))


class PipelineConfig(BaseSettings):
    # App Settings
    APP_NAME: str = Field(default="AuraFace Pipeline", env="APP_NAME")
    APP_ENV: str = Field(default="development", env="APP_ENV")
    DEBUG: bool = Field(default=True, env="DEBUG")

    # MongoDB Settings
    DATABASE_URL: str = Field(default="mongodb://localhost:27017", env="DATABASE_URL")
    DATABASE_NAME: str = Field(default="face_recog_db_v2", env="DATABASE_NAME")

    # Qdrant Vector DB Settings
    QDRANT_HOST: str = Field(default="187.127.189.238", env="QDRANT_HOST")
    QDRANT_PORT: int = Field(default=6334, env="QDRANT_PORT")
    QDRANT_COLLECTION: str = Field(default="faces_embed_v2", env="QDRANT_COLLECTION")

    # Storage & Temp Settings
    TEMP_DIR: str = Field(default="temp_uploads", env="TEMP_DIR")
    TEMP_UPLOAD_DIR: str = Field(default="temp_uploads", env="TEMP_UPLOAD_DIR")
    NUM_WORKERS: int = Field(default=4, env="NUM_WORKERS")
    CHUNK_SIZE: int = 5 * 1024 * 1024  # 5 MB Chunk Size

    # Google Drive Settings
    GOOGLE_DRIVE_CLIENT_ID: str = Field(default="", env="GOOGLE_DRIVE_CLIENT_ID")
    GOOGLE_DRIVE_CLIENT_SECRET: str = Field(default="", env="GOOGLE_DRIVE_CLIENT_SECRET")
    GOOGLE_DRIVE_REFRESH_TOKEN: str = Field(default="", env="GOOGLE_DRIVE_REFRESH_TOKEN")
    GOOGLE_DRIVE_PARENT_FOLDER_ID: str = Field(default="", env="GOOGLE_DRIVE_PARENT_FOLDER_ID")

    # InsightFace & Quality Thresholds
    FACE_DETECTION_THRESHOLD: float = 0.30  # Sensitive threshold to capture faces reliably
    MIN_FACE_SIZE: int = 20  # Minimum face size in pixels
    EMBEDDING_DIMENSION: int = 512
    MODEL_NAME: str = "buffalo_l"
    
    # Image Quality Thresholds
    MIN_BLUR_SCORE: float = 10.0  # Laplacian variance threshold
    MIN_FACE_QUALITY: float = 0.25

    # Security & Recognition Gateway Settings
    RECOGNITION_SECRET_KEY: str = Field(default="auraface_sec_key_production_grade_98372", env="RECOGNITION_SECRET_KEY")
    SESSION_TTL_SECONDS: int = Field(default=60, env="SESSION_TTL_SECONDS")
    MAX_FRAME_AGE_SECONDS: int = Field(default=30, env="MAX_FRAME_AGE_SECONDS")
    RATE_LIMIT_RPM: int = Field(default=30, env="RATE_LIMIT_RPM")
    REPLAY_NONCE_TTL_SECONDS: int = Field(default=120, env="REPLAY_NONCE_TTL_SECONDS")

    # Recognition & Anti-Spoof Thresholds
    RECOGNITION_SIMILARITY_THRESHOLD: float = Field(default=0.42, env="RECOGNITION_SIMILARITY_THRESHOLD")

    MINI_FASNET_REAL_THRESHOLD: float = Field(default=0.35, env="MINI_FASNET_REAL_THRESHOLD")
    MINI_FASNET_CROP_SCALE: float = Field(default=2.7, env="MINI_FASNET_CROP_SCALE")
    CROP_SCALE: float = Field(default=2.7, env="CROP_SCALE")
    MINI_FASNET_MIN_FRAMES: int = Field(default=2, env="MINI_FASNET_MIN_FRAMES")
    MINI_FASNET_AGGREGATION_METHOD: str = Field(default="mean", env="MINI_FASNET_AGGREGATION_METHOD")

    MAX_TOP_MATCHES: int = Field(default=10, env="MAX_TOP_MATCHES")
    JOB_TIMEOUT_SECONDS: int = Field(default=300, env="JOB_TIMEOUT_SECONDS")

    # Modular Liveness-First Thresholds & Multi-Frame Voting Weights
    LIVENESS_PASS_THRESHOLD: float = Field(default=0.65, env="LIVENESS_PASS_THRESHOLD")
    LIVENESS_UNCERTAIN_LOW: float = Field(default=0.25, env="LIVENESS_UNCERTAIN_LOW")
    LIVENESS_UNCERTAIN_HIGH: float = Field(default=0.65, env="LIVENESS_UNCERTAIN_HIGH")

    # Weighted Multi-Factor Fusion Weights (8 Factors)
    WEIGHT_MINIFASNET_V1SE: float = Field(default=0.15, env="WEIGHT_MINIFASNET_V1SE")
    WEIGHT_MINIFASNET_V2: float = Field(default=0.35, env="WEIGHT_MINIFASNET_V2")
    WEIGHT_LANDMARK_MOTION: float = Field(default=0.15, env="WEIGHT_LANDMARK_MOTION")
    WEIGHT_MOTION_UNIFORMITY: float = Field(default=0.10, env="WEIGHT_MOTION_UNIFORMITY")
    WEIGHT_OPTICAL_FLOW: float = Field(default=0.10, env="WEIGHT_OPTICAL_FLOW")
    WEIGHT_TEMPORAL_CONSISTENCY: float = Field(default=0.05, env="WEIGHT_TEMPORAL_CONSISTENCY")
    WEIGHT_FACE_QUALITY: float = Field(default=0.05, env="WEIGHT_FACE_QUALITY")
    WEIGHT_POSE_STABILITY: float = Field(default=0.05, env="WEIGHT_POSE_STABILITY")

    # Model File Paths
    MINIFASNET_V1SE_MODEL_PATH: str = Field(default="resources/anti_spoof_models/4_0_0_80x80_MiniFASNetV1SE.pth", env="MINIFASNET_V1SE_MODEL_PATH")
    MINIFASNET_V2_MODEL_PATH: str = Field(default="resources/anti_spoof_models/2.7_80x80_MiniFASNetV2.pth", env="MINIFASNET_V2_MODEL_PATH")
    TINY_LIVENESS_MODEL_PATH: str = Field(default="resources/anti_spoof_models/tiny_liveness.onnx", env="TINY_LIVENESS_MODEL_PATH")

    # Simple, Globally Understandable Quality Guidance Messages
    MSG_LOW_LIGHT: str = Field(default="Please move to a brighter area.", env="MSG_LOW_LIGHT")
    MSG_TOO_FAR: str = Field(default="Please move closer to the camera.", env="MSG_TOO_FAR")
    MSG_TOO_CLOSE: str = Field(default="Please step back slightly.", env="MSG_TOO_CLOSE")
    MSG_OFF_CENTER: str = Field(default="Please center your face in the frame.", env="MSG_OFF_CENTER")
    MSG_BLURRY: str = Field(default="Please hold steady.", env="MSG_BLURRY")

    # Lightweight Quality Thresholds (O(1) Evaluation)
    MIN_FACE_AREA_RATIO: float = Field(default=0.05, env="MIN_FACE_AREA_RATIO")
    MAX_FACE_AREA_RATIO: float = Field(default=0.45, env="MAX_FACE_AREA_RATIO")
    MAX_UNDEREXPOSURE_RATIO: float = Field(default=0.25, env="MAX_UNDEREXPOSURE_RATIO")
    MIN_BRIGHTNESS_MEAN: float = Field(default=40.0, env="MIN_BRIGHTNESS_MEAN")
    MAX_CENTER_OFFSET_PX: int = Field(default=100, env="MAX_CENTER_OFFSET_PX")


    # Intelligent Resource Scheduler Settings (VPS 2 vCPU / 4 GB RAM)
    TARGET_RECOGNITION_LATENCY_MS: float = Field(default=800.0, env="TARGET_RECOGNITION_LATENCY_MS")
    MAX_CPU_PERCENT: float = Field(default=85.0, env="MAX_CPU_PERCENT")
    RECOGNITION_WORKER_CONCURRENCY: int = Field(default=2, env="RECOGNITION_WORKER_CONCURRENCY")
    UPLOAD_WORKER_CONCURRENCY: int = Field(default=2, env="UPLOAD_WORKER_CONCURRENCY")

    # Server Settings
    BACKEND_BASE_URL: str = Field(default="http://127.0.0.1:8000", env="BACKEND_BASE_URL")
    CORS_ORIGINS: str = Field(default="http://localhost:3000,http://127.0.0.1:3000,http://localhost:8000,*", env="CORS_ORIGINS")

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = PipelineConfig()

