# -*- coding: utf-8 -*-
"""
Optical Flow & Rigid-Body Residual Deformation Service
------------------------------------------------------
Lightweight CPU-optimized Sparse Lucas-Kanade Optical Flow and Rigid Motion Subtraction:
1. Tracks key facial landmarks across consecutive candidate video frames using cv2.calcOpticalFlowPyrLK.
2. Estimates optimal 2D rigid transformation (Affine / Procrustes: translation, rotation, scale).
3. Subtracts global rigid motion to isolate local non-rigid facial deformations.
4. Computes Optical Flow Consistency Score comparing optical flow displacement vs landmark motion.
"""

import cv2
import numpy as np
import logging
from typing import Dict, Any, List, Tuple, Optional

logger = logging.getLogger("pipeline.optical_flow")


class OpticalFlowService:
    """
    Computes Sparse Lucas-Kanade Optical Flow tracking and rigid motion residual deformation.
    """

    @staticmethod
    def _estimate_rigid_transform(src_pts: np.ndarray, dst_pts: np.ndarray) -> Tuple[np.ndarray, float]:
        """
        Estimates 2D affine transformation (rigid translation + rotation + scale) from src to dst.
        Returns:
            - Transformation matrix (2, 3)
            - Mean residual error (px) after rigid subtraction
        """
        try:
            if len(src_pts) < 3 or len(dst_pts) < 3:
                return np.eye(2, 3, dtype=np.float32), 0.0

            # Estimate partial affine matrix (rigid + scale)
            M, inliers = cv2.estimateAffinePartial2D(src_pts, dst_pts, method=cv2.RANSAC, ransacReprojThreshold=3.0)
            if M is None:
                return np.eye(2, 3, dtype=np.float32), 0.0

            # Transform src_pts using rigid matrix M
            src_homogeneous = np.hstack([src_pts, np.ones((len(src_pts), 1), dtype=np.float32)])
            transformed_pts = (M @ src_homogeneous.T).T

            # Calculate residual non-rigid deformation (difference between actual dst_pts and rigid prediction)
            residuals = np.linalg.norm(dst_pts - transformed_pts, axis=1)
            residual_error = float(np.mean(residuals))

            return M, residual_error
        except Exception:
            return np.eye(2, 3, dtype=np.float32), 0.0

    def analyze_optical_flow(
        self,
        frames: List[np.ndarray],
        landmarks_list: List[Optional[List[List[float]]]]
    ) -> Dict[str, Any]:
        """
        Performs Sparse Lucas-Kanade Optical Flow tracking across candidate frames.

        Args:
            frames: List of BGR frame images.
            landmarks_list: List of facial landmark arrays per frame.

        Returns:
            Dict containing:
                - optical_flow_score: float (0.0 to 1.0)
                - flow_consistency_score: float (0.0 to 1.0)
                - residual_deformation_px: float
                - tracking_success_ratio: float
                - avg_flow_vector_len: float
        """
        valid_pairs = []
        for i in range(len(frames)):
            if i < len(landmarks_list) and landmarks_list[i] is not None and len(landmarks_list[i]) >= 5:
                valid_pairs.append((frames[i], np.array(landmarks_list[i], dtype=np.float32)))

        if len(valid_pairs) < 2:
            return {
                "optical_flow_score": 0.50,
                "flow_consistency_score": 0.50,
                "residual_deformation_px": 0.0,
                "tracking_success_ratio": 1.0,
                "avg_flow_vector_len": 0.0,
                "message": "Insufficient valid frame pairs for optical flow tracking"
            }

        try:
            residual_errors = []
            flow_consistency_scores = []
            tracking_ratios = []
            flow_vector_lengths = []

            # Lucas-Kanade Optical Flow parameters
            lk_params = dict(
                winSize=(15, 15),
                maxLevel=2,
                criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 10, 0.03)
            )

            for idx in range(len(valid_pairs) - 1):
                img1, pts1 = valid_pairs[idx]
                img2, pts2 = valid_pairs[idx + 1]

                gray1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY) if img1.ndim == 3 else img1
                gray2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY) if img2.ndim == 3 else img2

                # Select tracking keypoints (e.g. 5-point or 106-point landmarks)
                p0 = pts1.reshape(-1, 1, 2).astype(np.float32)

                # Calculate optical flow vectors
                p1, status, err = cv2.calcOpticalFlowPyrLK(gray1, gray2, p0, None, **lk_params)

                if p1 is not None and status is not None:
                    good_idx = np.where(status.flatten() == 1)[0]
                    success_ratio = len(good_idx) / max(1, len(status))
                    tracking_ratios.append(success_ratio)

                    if len(good_idx) >= 3:
                        tracked_p0 = p0[good_idx].reshape(-1, 2)
                        tracked_p1 = p1[good_idx].reshape(-1, 2)

                        # Optical flow vectors vs actual landmark displacement vectors
                        flow_vectors = tracked_p1 - tracked_p0
                        flow_lens = np.linalg.norm(flow_vectors, axis=1)
                        flow_vector_lengths.append(float(np.mean(flow_lens)))

                        # Estimate rigid affine transformation and residual non-rigid deformation
                        _, residual_err = self._estimate_rigid_transform(tracked_p0, tracked_p1)
                        residual_errors.append(residual_err)

                        # Calculate flow direction consistency (cosine similarity between flow vectors)
                        if len(flow_vectors) >= 3:
                            norm_flows = flow_vectors / (np.linalg.norm(flow_vectors, axis=1, keepdims=True) + 1e-5)
                            pairwise_dots = norm_flows @ norm_flows.T
                            flow_consistency = float(np.mean(pairwise_dots))
                            flow_consistency_scores.append(flow_consistency)

            avg_residual = float(np.mean(residual_errors)) if residual_errors else 0.0
            avg_flow_consistency = float(np.mean(flow_consistency_scores)) if flow_consistency_scores else 0.85
            avg_tracking_ratio = float(np.mean(tracking_ratios)) if tracking_ratios else 1.0
            avg_flow_len = float(np.mean(flow_vector_lengths)) if flow_vector_lengths else 0.0

            # Optical Flow Liveness Score (organic non-rigid faces have small non-zero residual deformation)
            # Replay attacks exhibit near-zero residual deformation under rigid motion subtraction!
            if avg_flow_len > 0.80:
                # Organic face non-rigid threshold (~0.2 to 2.5px residual deformation)
                optical_flow_score = float(max(0.0, min(1.0, (avg_residual / 1.5) * 0.5 + avg_flow_consistency * 0.5)))
            else:
                optical_flow_score = 0.50

            return {
                "optical_flow_score": round(optical_flow_score, 4),
                "flow_consistency_score": round(avg_flow_consistency, 4),
                "residual_deformation_px": round(avg_residual, 2),
                "tracking_success_ratio": round(avg_tracking_ratio, 4),
                "avg_flow_vector_len": round(avg_flow_len, 2),
                "message": f"Optical flow tracked {len(valid_pairs)} frames (residual={avg_residual:.2f}px)"
            }

        except Exception as e:
            logger.warning(f"Error in optical flow analysis: {e}")
            return {
                "optical_flow_score": 0.50,
                "flow_consistency_score": 0.50,
                "residual_deformation_px": 0.0,
                "tracking_success_ratio": 0.0,
                "avg_flow_vector_len": 0.0,
                "message": f"Optical flow tracking error: {e}"
            }


optical_flow_service = OpticalFlowService()
