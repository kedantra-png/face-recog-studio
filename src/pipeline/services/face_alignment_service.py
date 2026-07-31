# -*- coding: utf-8 -*-
"""
Face Alignment & Illumination Normalization Service Module
-----------------------------------------------------------
1. 5-landmark affine similarity transformation (Umeyama alignment to 112x112).
2. Illumination normalization using CLAHE (Contrast Limited Adaptive Histogram Equalization).
3. Pose angle calculation (yaw, pitch, roll).
"""

import cv2
import numpy as np
import logging
from typing import Tuple, Optional, List, Dict, Any

logger = logging.getLogger("pipeline.face_alignment")

# ArcFace standard 112x112 5-point landmark template
ARC_FACE_5POINT_TEMPLATE = np.array([
    [38.2946, 51.6963],  # Left Eye
    [73.5318, 51.5014],  # Right Eye
    [56.0252, 71.7366],  # Nose Tip
    [41.5493, 92.3655],  # Left Mouth Corner
    [70.7299, 92.2041]   # Right Mouth Corner
], dtype=np.float32)


class FaceAlignmentService:
    def __init__(self):
        self.clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))

    def align_and_normalize(self, img: np.ndarray, landmarks: Optional[np.ndarray]) -> np.ndarray:
        """
        Aligns raw BGR face image using 5 landmarks to 112x112 standard ArcFace crop.
        Returns the pristine natural image without artificial pixel mutation.
        """
        if img is None or img.size == 0:
            return np.zeros((112, 112, 3), dtype=np.uint8)

        # 1. Landmark affine warp
        if landmarks is not None and len(landmarks) >= 5:
            aligned = self.align_face_5landmarks(img, landmarks)
        else:
            aligned = cv2.resize(img, (112, 112))

        return aligned


    def align_face_5landmarks(self, img: np.ndarray, landmarks: np.ndarray, crop_size: int = 112) -> np.ndarray:
        """
        Computes 2D similarity transform matrix via Umeyama algorithm and warps face crop.
        """
        try:
            src = np.array(landmarks, dtype=np.float32)
            dst = ARC_FACE_5POINT_TEMPLATE.copy()

            M = self._umeyama(src, dst, estimate_scale=True)
            aligned = cv2.warpAffine(img, M[:2], (crop_size, crop_size), borderMode=cv2.BORDER_REFLECT_101)
            return aligned

        except Exception as e:
            logger.warning(f"Face alignment warp failed: {e}. Falling back to direct resize.")
            return cv2.resize(img, (crop_size, crop_size))


    def normalize_illumination(self, img: np.ndarray) -> np.ndarray:
        """
        Applies CLAHE on Luminance channel of LAB color space to stabilize uneven lighting.
        """
        try:
            lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)
            cl = self.clahe.apply(l)
            limg = cv2.merge((cl, a, b))
            final_bgr = cv2.cvtColor(limg, cv2.COLOR_LAB2BGR)
            return final_bgr
        except Exception as e:
            logger.warning(f"Illumination normalization failed: {e}")
            return img

    def _umeyama(self, src: np.ndarray, dst: np.ndarray, estimate_scale: bool = True) -> np.ndarray:
        """
        Computes 2D similarity transformation matrix mapping src to dst.
        """
        num = src.shape[0]
        dim = src.shape[1]

        src_mean = src.mean(axis=0)
        dst_mean = dst.mean(axis=0)

        src_demean = src - src_mean
        dst_demean = dst - dst_mean

        A = np.dot(dst_demean.T, src_demean) / num
        d = np.ones((dim,), dtype=np.float64)
        if np.linalg.det(A) < 0:
            d[dim - 1] = -1

        T = np.eye(dim + 1, dtype=np.float64)

        U, S, V = np.linalg.svd(A)

        rank = np.linalg.matrix_rank(A)
        if rank < dim - 1:
            return T

        if rank == dim - 1:
            if np.linalg.det(U) * np.linalg.det(V) < 0:
                d[dim - 1] = -1

        T[:dim, :dim] = np.dot(U, np.dot(np.diag(d), V))

        if estimate_scale:
            scale = 1.0 / src_demean.var(axis=0).sum() * np.dot(S, d)
        else:
            scale = 1.0

        T[:dim, dim] = dst_mean - scale * np.dot(T[:dim, :dim], src_mean)
        T[:dim, :dim] *= scale

        return T


face_alignment_service = FaceAlignmentService()
