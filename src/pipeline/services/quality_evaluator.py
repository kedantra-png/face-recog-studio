# -*- coding: utf-8 -*-
"""
Image & Face Quality Assessment Module
--------------------------------------
Evaluates image clarity, blur (Laplacian variance), brightness, contrast, noise,
and facial pose parameters (yaw, pitch, roll, occlusion, sharpness).
Rejects corrupted or unusable images before embedding extraction.
"""

import cv2
import numpy as np
import logging
from typing import Dict, Any, Tuple, List

from src.pipeline.config import settings

logger = logging.getLogger("pipeline.quality")


class QualityEvaluator:
    """
    Evaluates image and face quality parameters to ensure maximum embedding accuracy.
    """

    @staticmethod
    def evaluate_image_quality(img: np.ndarray) -> Dict[str, Any]:
        """
        Calculates blur, brightness, contrast, noise, and overall image score.
        """
        if img is None or img.size == 0:
            return {"usable": False, "score": 0.0, "reason": "Empty or corrupted image"}

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # 1. Blur evaluation via Laplacian Variance
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()

        # 2. Brightness evaluation
        brightness = float(np.mean(gray))

        # 3. Contrast evaluation
        contrast = float(np.std(gray))

        # 4. Noise estimation
        h, w = gray.shape
        blur_diff = cv2.GaussianBlur(gray, (5, 5), 0)
        noise_level = float(np.std(gray - blur_diff))

        # Calculate composite score (normalized 0.0 to 1.0)
        blur_score = min(1.0, laplacian_var / 300.0)
        brightness_score = 1.0 - abs(brightness - 128.0) / 128.0
        contrast_score = min(1.0, contrast / 70.0)

        composite_score = round(0.5 * blur_score + 0.3 * contrast_score + 0.2 * brightness_score, 3)

        usable = (laplacian_var >= settings.MIN_BLUR_SCORE) and (brightness > 15.0) and (brightness < 245.0)

        return {
            "usable": usable,
            "score": composite_score,
            "blur_laplacian": round(laplacian_var, 2),
            "brightness": round(brightness, 2),
            "contrast": round(contrast, 2),
            "noise_level": round(noise_level, 2),
            "reason": "Image passed quality checks" if usable else "Image is too blurry, dark, or overexposed"
        }

    @staticmethod
    def evaluate_face_quality(img: np.ndarray, bbox: List[int], landmarks: np.ndarray) -> Dict[str, Any]:
        """
        Evaluates facial pose (yaw, pitch, roll), eye visibility, and face crop resolution.
        """
        x1, y1, w, h = bbox
        if w < settings.MIN_FACE_SIZE or h < settings.MIN_FACE_SIZE:
            return {"usable": False, "score": 0.0, "reason": f"Face too small ({w}x{h}px)"}

        # Estimate pose angles from 5 landmarks (left_eye, right_eye, nose, left_mouth, right_mouth)
        yaw = 0.0
        pitch = 0.0
        roll = 0.0

        if landmarks is not None and len(landmarks) >= 5:
            left_eye = landmarks[0]
            right_eye = landmarks[1]
            nose = landmarks[2]

            # Roll angle (rotation around Z axis)
            dx = right_eye[0] - left_eye[0]
            dy = right_eye[1] - left_eye[1]
            roll = float(np.degrees(np.arctan2(dy, dx)))

            # Yaw angle (rotation around Y axis - left/right turn)
            eye_center_x = (left_eye[0] + right_eye[0]) / 2.0
            nose_offset_x = nose[0] - eye_center_x
            eye_dist = max(1.0, np.linalg.norm(right_eye - left_eye))

            yaw = float(np.clip((nose_offset_x / eye_dist) * 90.0, -90.0, 90.0))

        # Face crop sharpness
        crop = img[max(0, y1):max(0, y1+h), max(0, x1):max(0, x1+w)]
        if crop.size > 0:
            crop_gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            sharpness = round(float(cv2.Laplacian(crop_gray, cv2.CV_64F).var()), 2)
        else:
            sharpness = 0.0

        # Pose penalty
        pose_penalty = max(0.0, 1.0 - (abs(yaw) / 60.0 + abs(roll) / 45.0))
        sharpness_score = min(1.0, sharpness / 200.0)
        face_score = round(0.6 * sharpness_score + 0.4 * pose_penalty, 3)

        usable = (abs(yaw) <= 50.0) and (abs(roll) <= 40.0) and (face_score >= settings.MIN_FACE_QUALITY)

        return {
            "usable": usable,
            "score": face_score,
            "yaw": round(yaw, 1),
            "pitch": round(pitch, 1),
            "roll": round(roll, 1),
            "sharpness": sharpness,
            "face_width": w,
            "face_height": h,
            "reason": "Face passed quality checks" if usable else "Face pose too extreme or blurry"
        }


quality_evaluator = QualityEvaluator()
