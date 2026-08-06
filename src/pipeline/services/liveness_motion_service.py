# -*- coding: utf-8 -*-
"""
Landmark Motion Analysis & Motion Uniformity Service
------------------------------------------------------
Lightweight CPU-optimized temporal landmark geometric analysis across consecutive candidate video frames:
1. Track motion for specific facial landmark groups:
   - Left Eye
   - Right Eye
   - Nose Tip
   - Mouth Corners
   - Chin / Jawline
2. For every consecutive frame compute:
   - X displacement
   - Y displacement
   - Euclidean distance
   - Motion variance
   - Motion velocity
   - Motion consistency
3. Motion Uniformity Analysis (Rigid-body vs Independent Local Motion):
   - Replay Attack (Photo / Phone Screen): Bounding box translation moves all landmarks uniformly (high correlation, zero covariance difference).
   - Genuine Human Face: Exhibits independent non-rigid micro-deformations (eye blinks, mouth flex, skin micro-shifts).
"""

import math
import numpy as np
import logging
from typing import List, Dict, Any, Tuple, Optional

logger = logging.getLogger("pipeline.liveness_motion")


class LivenessMotionService:
    """
    Computes temporal landmark motion analysis and motion uniformity (rigid-body vs organic non-rigid motion).
    """

    @staticmethod
    def analyze_landmark_motion(
        landmarks_list: List[Optional[List[List[float]]]]
    ) -> Dict[str, Any]:
        """
        Performs Landmark Motion Analysis and Motion Uniformity Analysis across candidate frames.

        Args:
            landmarks_list: List of facial landmark arrays per frame (supports 5-point or 106-point landmarks).

        Returns:
            Dict containing:
                - landmark_motion_score: float (0.0 to 1.0)
                - motion_uniformity_score: float (0.0 to 1.0, high = rigid replay attack)
                - is_rigid_replay: bool
                - motion_detected: bool
                - avg_displacement_px: float
                - motion_variance: float
                - motion_velocity: float
                - motion_consistency: float
                - motion_correlation: float
                - landmark_covariance: float
                - independent_displacement: float
                - rigid_body_score: float
                - message: str
        """
        valid_landmarks = [lm for lm in landmarks_list if lm is not None and len(lm) >= 5]
        num_frames = len(valid_landmarks)

        if num_frames < 2:
            return {
                "landmark_motion_score": 0.50,
                "motion_uniformity_score": 0.50,
                "is_rigid_replay": False,
                "motion_detected": False,
                "avg_displacement_px": 0.0,
                "motion_variance": 0.0,
                "motion_velocity": 0.0,
                "motion_consistency": 0.50,
                "motion_correlation": 0.50,
                "landmark_covariance": 0.0,
                "independent_displacement": 0.0,
                "rigid_body_score": 0.50,
                "message": "Insufficient valid landmark frames for temporal motion analysis"
            }

        try:
            # Standardize landmark arrays: shape (num_frames, N_points, 2)
            # Map key facial regions (left eye, right eye, nose tip, mouth corners, chin/jaw)
            lm_frames = []
            for lm in valid_landmarks:
                arr = np.array(lm, dtype=np.float32)
                if arr.shape[0] >= 106:
                    # Select key 106-point landmark indices for [LeftEye, RightEye, NoseTip, LeftMouth, RightMouth, Chin]
                    key_indices = [36, 45, 30, 48, 54, 8]
                    pts = arr[key_indices]
                elif arr.shape[0] >= 5:
                    # Standard 5-landmark format: [RightEye, LeftEye, NoseTip, RightMouth, LeftMouth]
                    pts = arr[:5]
                else:
                    pts = arr
                lm_frames.append(pts)

            lm_arr = np.array(lm_frames, dtype=np.float32)  # shape: (num_frames, K, 2)
            n_frames, k_points, _ = lm_arr.shape

            # ---------------------------------------------------------------------------------
            # 1. TEMPORAL LANDMARK MOTION ANALYSIS
            # ---------------------------------------------------------------------------------
            # Consecutive frame displacements per landmark point
            frame_diffs = np.diff(lm_arr, axis=0)  # shape: (num_frames-1, K, 2)
            x_disp = frame_diffs[:, :, 0]  # X displacements
            y_disp = frame_diffs[:, :, 1]  # Y displacements
            euc_dists = np.linalg.norm(frame_diffs, axis=2)  # shape: (num_frames-1, K)

            avg_disp_per_frame = np.mean(euc_dists, axis=1)  # shape: (num_frames-1,)
            avg_displacement_px = float(np.mean(avg_disp_per_frame))

            motion_variance = float(np.var(avg_disp_per_frame)) if len(avg_disp_per_frame) > 1 else 0.0
            motion_velocity = float(avg_displacement_px)  # Pixels per frame delta
            motion_detected = bool(avg_displacement_px >= 0.80)

            # Motion consistency (lower variance in frame-to-frame velocity indicates smooth human motion)
            motion_consistency = float(max(0.0, min(1.0, 1.0 - (motion_variance / (avg_displacement_px + 1e-5)))))

            # Normalized landmark motion score (0.0 to 1.0)
            landmark_motion_score = float(max(0.0, min(1.0, (avg_displacement_px / 12.0) * 0.5 + motion_consistency * 0.5)))

            # ---------------------------------------------------------------------------------
            # 2. MOTION UNIFORMITY ANALYSIS (RIGID-BODY REPLAY DETECTION)
            # ---------------------------------------------------------------------------------
            # A 2D photo or phone screen replay attack moves all landmarks uniformly (correlation ~ 1.0).
            # Genuine faces have independent local landmark movement (eye blinks, mouth flex, skin stretch).

            # Scale and centroid normalization (eliminate overall 2D rigid translation & scale)
            norm_lm_frames = []
            ear_list = []
            mouth_width_list = []

            for t in range(n_frames):
                pts = lm_arr[t]
                centroid = np.mean(pts, axis=0)
                # Inter-ocular distance scale factor
                r_eye = pts[0]
                l_eye = pts[1]
                interocular = max(1.0, float(np.linalg.norm(r_eye - l_eye)))

                norm_pts = (pts - centroid) / interocular
                norm_lm_frames.append(norm_pts)

                # Track internal feature ratios
                nose = pts[2] if k_points > 2 else centroid
                ear_proxy = float((np.linalg.norm(r_eye - nose) + np.linalg.norm(l_eye - nose)) / (2.0 * interocular))
                ear_list.append(ear_proxy)

                if k_points >= 5:
                    mouth_w = float(np.linalg.norm(pts[3] - pts[4]) / interocular)
                else:
                    mouth_w = 0.50
                mouth_width_list.append(mouth_w)

            norm_arr = np.array(norm_lm_frames, dtype=np.float32)  # shape: (num_frames, K, 2)
            norm_diffs = np.diff(norm_arr, axis=0)  # shape: (num_frames-1, K, 2)
            norm_euc = np.linalg.norm(norm_diffs, axis=2)  # shape: (num_frames-1, K)

            # Measure Independent Landmark Displacement (variance across landmark points' normalized motion)
            indep_displacement_var = float(np.mean(np.var(norm_euc, axis=1))) if norm_euc.shape[1] > 1 else 0.0
            independent_displacement = float(min(1.0, indep_displacement_var * 500.0))

            # Motion Correlation across landmark points
            # If all landmarks move in lockstep, pairwise correlation of displacement vectors is ~ 1.0
            flat_diffs = frame_diffs.reshape(n_frames - 1, -1)  # shape: (num_frames-1, K*2)
            if flat_diffs.shape[1] >= 2 and n_frames > 2:
                corr_matrix = np.corrcoef(flat_diffs.T)
                corr_matrix = np.nan_to_num(corr_matrix, nan=0.0)
                motion_correlation = float(np.mean(np.abs(corr_matrix)))
            else:
                motion_correlation = 0.85

            # Landmark Covariance (Covariance of normalized internal landmark positions over time)
            flat_norm = norm_arr.reshape(n_frames, -1)  # shape: (num_frames, K*2)
            cov_matrix = np.cov(flat_norm.T) if n_frames > 1 else np.zeros((1, 1))
            landmark_covariance = float(np.mean(np.abs(cov_matrix)))

            # Internal Deformability Index
            ear_var = float(np.var(ear_list)) if len(ear_list) > 1 else 0.0
            mouth_var = float(np.var(mouth_width_list)) if len(mouth_width_list) > 1 else 0.0
            internal_deformability = float(min(1.0, (landmark_covariance * 150.0) + (ear_var * 200.0) + (mouth_var * 150.0)))

            # Motion Uniformity Score (0.0 = organic non-rigid face, 1.0 = highly rigid 2D photo/replay)
            if avg_displacement_px > 1.0:
                motion_uniformity_score = float(max(0.0, min(1.0, (motion_correlation * 0.6) + (1.0 - internal_deformability) * 0.4)))
            else:
                motion_uniformity_score = 0.50

            rigid_body_score = motion_uniformity_score

            # Rigid Replay Decision:
            # Requires rapid external displacement (photo/phone held & moved in hand: avg_displacement >= 4.0px)
            # COMBINED with near 100% rigid motion correlation (motion_correlation >= 0.92) and static internal deformability (< 0.05).
            is_rigid_replay = bool(
                avg_displacement_px >= 4.0 and
                motion_correlation >= 0.92 and
                internal_deformability < 0.05
            )

            log_msg = (
                f"[LANDMARK MOTION LOG] Frames: {n_frames} | MotionScore: {landmark_motion_score:.3f} | "
                f"AvgDisp: {avg_displacement_px:.2f}px | MotionVar: {motion_variance:.4f} | "
                f"UniformityScore: {motion_uniformity_score:.3f} | MotionCorr: {motion_correlation:.3f} | "
                f"InternalDeformability: {internal_deformability:.4f} | IsRigidReplay: {is_rigid_replay}"
            )
            logger.info(log_msg)

            return {
                "landmark_motion_score": round(landmark_motion_score, 4),
                "motion_uniformity_score": round(motion_uniformity_score, 4),
                "is_rigid_replay": is_rigid_replay,
                "motion_detected": motion_detected,
                "avg_displacement_px": round(avg_displacement_px, 2),
                "motion_variance": round(motion_variance, 4),
                "motion_velocity": round(motion_velocity, 2),
                "motion_consistency": round(motion_consistency, 4),
                "motion_correlation": round(motion_correlation, 4),
                "landmark_covariance": round(landmark_covariance, 6),
                "independent_displacement": round(independent_displacement, 4),
                "rigid_body_score": round(rigid_body_score, 4),
                "internal_deformability": round(internal_deformability, 4),
                "message": "Rigid 2D photo / screen replay attack detected" if is_rigid_replay else "Organic facial motion verified"
            }

        except Exception as e:
            logger.warning(f"Error in landmark motion analysis: {e}")
            return {
                "landmark_motion_score": 0.50,
                "motion_uniformity_score": 0.50,
                "is_rigid_replay": False,
                "motion_detected": False,
                "avg_displacement_px": 0.0,
                "motion_variance": 0.0,
                "motion_velocity": 0.0,
                "motion_consistency": 0.50,
                "motion_correlation": 0.50,
                "landmark_covariance": 0.0,
                "independent_displacement": 0.0,
                "rigid_body_score": 0.50,
                "internal_deformability": 0.50,
                "message": f"Motion analysis error: {e}"
            }


liveness_motion_service = LivenessMotionService()
