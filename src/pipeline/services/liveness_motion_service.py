# -*- coding: utf-8 -*-
"""
Landmark Kinematic Motion Analysis & Head Pose Service
-------------------------------------------------------
Temporal landmark geometric and kinematic motion analysis across candidate video frames:
1. Face-Width Normalized Kinematics:
   - Normalized Landmark Displacement (delta_d / FaceWidth)
   - Normalized Landmark Velocity (px / frame / FaceWidth)
   - Normalized Landmark Acceleration (px / frame^2 / FaceWidth)
2. 3D Head Pose via cv2.solvePnP:
   - Perspective-n-Point estimation using canonical 3D facial geometry
   - Precise 3D Yaw, Pitch, and Roll angles (degrees)
3. Facial Entropy & Stability:
   - Motion Entropy (shannon entropy of velocity distribution)
   - Motion Stability & Local Facial Deformation Index
   - Eye Aspect Ratio (EAR) & Mouth Aspect Ratio (MAR)
4. Rigid-Body Transformation Residuals & Replay Detection
"""

import cv2
import math
import logging
import numpy as np
from typing import List, Dict, Any, Tuple, Optional

logger = logging.getLogger("pipeline.liveness_motion")

# Canonical 3D facial model points for solvePnP (mm in 3D face space)
CANONICAL_3D_POINTS_5 = np.array([
    [ -30.0,  30.0,  -30.0],  # Right eye center
    [  30.0,  30.0,  -30.0],  # Left eye center
    [   0.0,   0.0,    0.0],  # Nose tip
    [ -25.0, -35.0,  -20.0],  # Right mouth corner
    [  25.0, -35.0,  -20.0]   # Left mouth corner
], dtype=np.float32)

CANONICAL_3D_POINTS_106 = np.array([
    [ -30.0,  30.0,  -30.0],  # 36: Left eye center / outer
    [  30.0,  30.0,  -30.0],  # 45: Right eye center
    [   0.0,   0.0,    0.0],  # 54: Nose tip
    [ -25.0, -35.0,  -20.0],  # 48: Left mouth corner
    [  25.0, -35.0,  -20.0],  # 90: Right mouth corner
    [   0.0, -60.0,  -30.0],  # 16: Chin bottom
    [ -35.0,  30.0,  -30.0],  # 33: Left eye outer
    [  35.0,  30.0,  -30.0],  # 46: Right eye outer
    [   0.0, -30.0,  -15.0],  # 87: Upper lip center
    [   0.0, -40.0,  -15.0]   # 93: Lower lip center
], dtype=np.float32)


class LivenessMotionService:
    """
    Computes face-size normalized temporal kinematics, cv2.solvePnP 3D head pose, EAR/MAR, and rigid-body motion.
    """

    @staticmethod
    def _compute_solvepnp_head_pose(pts: np.ndarray, img_w: int = 640, img_h: int = 480) -> Dict[str, float]:
        """
        Estimates 3D Yaw, Pitch, and Roll angles in degrees using OpenCV solvePnP.
        """
        try:
            if len(pts) >= 106:
                key_indices = [36, 45, 54, 48, 90 if len(pts) > 90 else 54, 16 if len(pts) > 16 else 8, 33, 46, 87 if len(pts) > 87 else 48, 93 if len(pts) > 93 else 90]
                image_points = pts[key_indices].astype(np.float32)
                model_points = CANONICAL_3D_POINTS_106
            elif len(pts) >= 5:
                image_points = pts[:5].astype(np.float32)
                model_points = CANONICAL_3D_POINTS_5
            else:
                return {"yaw": 0.0, "pitch": 0.0, "roll": 0.0}

            focal_length = img_w
            center = (img_w / 2.0, img_h / 2.0)
            camera_matrix = np.array([
                [focal_length, 0, center[0]],
                [0, focal_length, center[1]],
                [0, 0, 1]
            ], dtype=np.float32)

            dist_coeffs = np.zeros((4, 1), dtype=np.float32)

            success, rot_vec, trans_vec = cv2.solvePnP(
                model_points, image_points, camera_matrix, dist_coeffs, flags=cv2.SOLVEPNP_ITERATIVE
            )

            if not success:
                return {"yaw": 0.0, "pitch": 0.0, "roll": 0.0}

            # Convert rotation vector to rotation matrix
            rot_mat, _ = cv2.Rodrigues(rot_vec)
            pose_mat = cv2.hconcat((rot_mat, trans_vec))
            _, _, _, _, _, _, euler_angles = cv2.decomposeProjectionMatrix(pose_mat)

            pitch_deg = float(euler_angles[0][0])
            yaw_deg = float(euler_angles[1][0])
            roll_deg = float(euler_angles[2][0])

            return {
                "yaw": round(float(np.clip(yaw_deg, -90.0, 90.0)), 2),
                "pitch": round(float(np.clip(pitch_deg, -90.0, 90.0)), 2),
                "roll": round(float(np.clip(roll_deg, -90.0, 90.0)), 2)
            }
        except Exception:
            return {"yaw": 0.0, "pitch": 0.0, "roll": 0.0}

    @staticmethod
    def _compute_ear(pts: np.ndarray) -> float:
        """
        Computes Eye Aspect Ratio (EAR).
        """
        try:
            if len(pts) >= 106:
                l_v1 = np.linalg.norm(pts[37] - pts[41])
                l_v2 = np.linalg.norm(pts[38] - pts[40])
                l_h = np.linalg.norm(pts[33] - pts[39])
                ear_left = (l_v1 + l_v2) / (2.0 * max(1e-5, l_h))

                r_v1 = np.linalg.norm(pts[43] - pts[47])
                r_v2 = np.linalg.norm(pts[44] - pts[46])
                r_h = np.linalg.norm(pts[42] - pts[46])
                ear_right = (r_v1 + r_v2) / (2.0 * max(1e-5, r_h))

                return float((ear_left + ear_right) / 2.0)
            elif len(pts) >= 5:
                interocular = max(1.0, float(np.linalg.norm(pts[1] - pts[0])))
                eye_center = (pts[0] + pts[1]) / 2.0
                nose_dist = float(np.linalg.norm(pts[2] - eye_center))
                return float(nose_dist / interocular)
            return 0.30
        except Exception:
            return 0.30

    @staticmethod
    def _compute_mar(pts: np.ndarray) -> float:
        """
        Computes Mouth Aspect Ratio (MAR).
        """
        try:
            if len(pts) >= 106 and len(pts) > 93:
                mar_v = np.linalg.norm(pts[87] - pts[93])
                mar_h = np.linalg.norm(pts[84] - pts[90])
                return float(mar_v / max(1e-5, mar_h))
            elif len(pts) >= 5:
                interocular = max(1.0, float(np.linalg.norm(pts[1] - pts[0])))
                mouth_width = float(np.linalg.norm(pts[4] - pts[3]))
                return float(mouth_width / interocular)
            return 0.50
        except Exception:
            return 0.50

    @classmethod
    def analyze_landmark_motion(
        cls,
        landmarks_list: List[Optional[List[List[float]]]]
    ) -> Dict[str, Any]:
        """
        Performs comprehensive multi-frame temporal motion analysis, computing face-size normalized kinematics,
        solvePnP 3D head pose, EAR/MAR, motion entropy, and rigid-body motion scores.
        """
        valid_landmarks = [lm for lm in landmarks_list if lm is not None and len(lm) >= 5]
        num_frames = len(valid_landmarks)

        if num_frames < 2:
            return {
                "landmark_motion_score": 0.50,
                "motion_uniformity_score": 0.50,
                "is_rigid_replay": False,
                "motion_detected": False,
                "landmark_displacement": 0.0,
                "normalized_displacement": 0.0,
                "landmark_velocity": 0.0,
                "landmark_acceleration": 0.0,
                "motion_variance": 0.0,
                "motion_correlation": 0.50,
                "motion_entropy": 0.0,
                "motion_stability": 1.0,
                "head_pose": {"yaw": 0.0, "pitch": 0.0, "roll": 0.0},
                "head_pose_stability": 1.0,
                "ear": 0.30,
                "mar": 0.50,
                "rigid_body_score": 0.50,
                "avg_displacement_px": 0.0,
                "internal_deformability": 0.50,
                "message": "Insufficient valid landmark frames for temporal motion analysis"
            }

        try:
            # ---------------------------------------------------------------------------------
            # 1. LANDMARK DATA STANDARDIZATION & solvePnP HEAD POSE / EAR / MAR EVALUATION
            # ---------------------------------------------------------------------------------
            lm_frames = []
            ear_history = []
            mar_history = []
            head_poses = []
            face_widths = []

            for lm in valid_landmarks:
                pts = np.array(lm, dtype=np.float32)
                lm_frames.append(pts)

                # Bounding box FaceWidth for distance-independent normalization
                x_min, y_min = np.min(pts, axis=0)
                x_max, y_max = np.max(pts, axis=0)
                fw = max(10.0, float(x_max - x_min))
                face_widths.append(fw)

                # SolvePnP 3D Head Pose, EAR, and MAR
                hp = cls._compute_solvepnp_head_pose(pts)
                ear = cls._compute_ear(pts)
                mar = cls._compute_mar(pts)

                head_poses.append(hp)
                ear_history.append(ear)
                mar_history.append(mar)

            avg_face_width = float(np.mean(face_widths))

            # Average Head Pose & Pose Stability across sequence
            yaws = [hp["yaw"] for hp in head_poses]
            pitches = [hp["pitch"] for hp in head_poses]
            rolls = [hp["roll"] for hp in head_poses]

            avg_yaw = float(np.mean(yaws))
            avg_pitch = float(np.mean(pitches))
            avg_roll = float(np.mean(rolls))

            pose_var = float(np.var(yaws) + np.var(pitches) + np.var(rolls)) if num_frames > 1 else 0.0
            head_pose_stability = float(max(0.0, min(1.0, 1.0 - (pose_var / 25.0))))

            latest_ear = float(ear_history[-1])
            latest_mar = float(mar_history[-1])
            ear_variance = float(np.var(ear_history)) if num_frames > 1 else 0.0
            mar_variance = float(np.var(mar_history)) if num_frames > 1 else 0.0

            # ---------------------------------------------------------------------------------
            # 2. FACE-SIZE NORMALIZED KINEMATIC MOTION ANALYSIS
            # ---------------------------------------------------------------------------------
            # ---------------------------------------------------------------------------------
            # 2. FACE-SIZE NORMALIZED KINEMATIC MOTION ANALYSIS (ALL 106 LANDMARKS)
            # ---------------------------------------------------------------------------------
            lm_arr = np.array(lm_frames, dtype=np.float32)  # shape: (n_frames, K, 2)
            n_frames, k_points, _ = lm_arr.shape

            # 1. Overall Landmark Displacement & Resolution-Independent Normalization
            frame_diffs = np.diff(lm_arr, axis=0)  # shape: (n_frames-1, K, 2)
            euc_dists = np.linalg.norm(frame_diffs, axis=2)  # shape: (n_frames-1, K)
            frame_avg_displacements = np.mean(euc_dists, axis=1)

            raw_displacement = float(np.mean(frame_avg_displacements))
            normalized_displacement = float(raw_displacement / avg_face_width)

            # 2. Region Breakdown across 106 Facial Landmarks
            if k_points >= 106:
                jaw_disp = float(np.mean(euc_dists[:, 0:33])) if n_frames > 1 else 0.0
                eyebrow_disp = float(np.mean(euc_dists[:, 33:52])) if n_frames > 1 else 0.0
                eye_disp = float(np.mean(euc_dists[:, 52:72])) if n_frames > 1 else 0.0
                nose_disp = float(np.mean(euc_dists[:, 72:84])) if n_frames > 1 else 0.0
                lip_disp = float(np.mean(euc_dists[:, 84:106])) if n_frames > 1 else 0.0
            else:
                jaw_disp = raw_displacement
                eyebrow_disp = raw_displacement
                eye_disp = raw_displacement
                nose_disp = raw_displacement
                lip_disp = raw_displacement

            # 3. Normalized Velocity & Acceleration
            velocities = frame_avg_displacements / avg_face_width
            normalized_velocity = float(np.mean(velocities))

            if len(velocities) > 1:
                accelerations = np.diff(velocities)
                normalized_acceleration = float(np.mean(np.abs(accelerations)))
            else:
                normalized_acceleration = 0.0

            motion_variance = float(np.var(velocities)) if len(velocities) > 1 else 0.0
            motion_detected = bool(normalized_displacement >= 0.005)

            # Motion Entropy (Shannon entropy of velocity distribution)
            if len(velocities) > 1 and np.sum(velocities) > 1e-5:
                prob_dist = velocities / np.sum(velocities)
                prob_dist = prob_dist[prob_dist > 0]
                motion_entropy = float(-np.sum(prob_dist * np.log2(prob_dist)))
            else:
                motion_entropy = 0.0

            motion_stability = float(max(0.0, min(1.0, 1.0 - (motion_variance * 50.0))))

            # ---------------------------------------------------------------------------------
            # 3. MOTION CORRELATION & RIGID-BODY REPLAY RESIDUALS
            # ---------------------------------------------------------------------------------
            flat_diffs = frame_diffs.reshape(n_frames - 1, -1)
            if flat_diffs.shape[1] >= 2 and n_frames > 2:
                corr_matrix = np.corrcoef(flat_diffs.T)
                corr_matrix = np.nan_to_num(corr_matrix, nan=0.0)
                motion_correlation = float(np.mean(np.abs(corr_matrix)))
            else:
                motion_correlation = 0.85

            norm_lm_frames = []
            for t in range(n_frames):
                pts = lm_arr[t]
                centroid = np.mean(pts, axis=0)
                interocular = max(1.0, float(np.linalg.norm(pts[1] - pts[0])))
                norm_pts = (pts - centroid) / interocular
                norm_lm_frames.append(norm_pts)

            norm_arr = np.array(norm_lm_frames, dtype=np.float32)
            flat_norm = norm_arr.reshape(n_frames, -1)
            cov_matrix = np.cov(flat_norm.T) if n_frames > 1 else np.zeros((1, 1))
            landmark_covariance = float(np.mean(np.abs(cov_matrix)))

            internal_deformability = float(min(1.0, (landmark_covariance * 150.0) + (ear_variance * 250.0) + (mar_variance * 200.0)))

            if normalized_displacement > 0.008:
                rigid_body_score = float(max(0.0, min(1.0, (motion_correlation * 0.60) + (1.0 - internal_deformability) * 0.40)))
            else:
                rigid_body_score = 0.50

            motion_uniformity_score = rigid_body_score

            is_rigid_replay = bool(
                (normalized_displacement >= 0.008 and rigid_body_score >= 0.70 and internal_deformability < 0.25) or
                (motion_correlation >= 0.88 and internal_deformability < 0.10)
            )

            disp_factor = min(1.0, normalized_displacement * 25.0)
            deform_factor = max(0.0, min(1.0, (1.0 - rigid_body_score) * 0.6 + internal_deformability * 0.4))
            landmark_motion_score = float(max(0.0, min(1.0, disp_factor * deform_factor)))

            status_msg = "Rigid 2D photo / screen replay attack detected" if is_rigid_replay else "Organic facial motion verified"

            log_lines = [
                "\n==================== [INSIGHTFACE 106-POINT KINEMATIC MOTION ANALYSIS LOG] ====================",
                f"[FRAME EVALUATION] Candidate Frames: {n_frames} | Total Tracked Landmarks: {k_points} Points | Avg FaceWidth: {avg_face_width:.1f}px",
                f"[106-PT KINEMATICS] Norm Disp: {normalized_displacement:.4f} | Norm Vel: {normalized_velocity:.4f} | Norm Accel: {normalized_acceleration:.4f} | Raw Disp: {raw_displacement:.2f}px",
                f"[106 REGION METRICS]",
                f"  - Jaw Contour (0..32)  : Disp = {jaw_disp:.2f}px | Norm = {jaw_disp/avg_face_width:.4f}",
                f"  - Eyebrows    (33..51) : Disp = {eyebrow_disp:.2f}px | Norm = {eyebrow_disp/avg_face_width:.4f}",
                f"  - Eyes Region (52..71) : Disp = {eye_disp:.2f}px | Norm = {eye_disp/avg_face_width:.4f} | EAR = {latest_ear:.4f} (var={ear_variance:.6f})",
                f"  - Nose Bridge (72..83) : Disp = {nose_disp:.2f}px | Norm = {nose_disp/avg_face_width:.4f}",
                f"  - Lip Contour (84..105): Disp = {lip_disp:.2f}px | Norm = {lip_disp/avg_face_width:.4f} | MAR = {latest_mar:.4f} (var={mar_variance:.6f})",
                f"[VARIANCE & CORR]   Motion Variance: {motion_variance:.6f} | Shannon Entropy: {motion_entropy:.3f} | Pairwise Correlation: {motion_correlation:.4f}",
                f"[SOLVEPNP 3D POSE]  Yaw: {avg_yaw:+.1f}° | Pitch: {avg_pitch:+.1f}° | Roll: {avg_roll:+.1f}° | Pose Stability: {head_pose_stability:.4f}",
                f"[RIGID REPLAY CHECK] Internal Deformability: {internal_deformability:.4f} | Rigid Body Score: {rigid_body_score:.4f}",
                f"[MOTION VERDICT]     Is Rigid Replay = {is_rigid_replay} | Motion Score = {landmark_motion_score:.4f} | {status_msg}",
                "================================================================================================\n"
            ]
            log_text = "\n".join(log_lines)
            print(log_text)
            try:
                debug_file = os.path.join(os.getcwd(), "debug", "pipeline_logs.txt")
                os.makedirs(os.path.dirname(debug_file), exist_ok=True)
                with open(debug_file, "a", encoding="utf-8") as f:
                    f.write(log_text + "\n")
            except Exception:
                pass

            logger.info(f"Kinematic Motion Analysis: norm_disp={normalized_displacement:.4f}, rigid={is_rigid_replay}")

            return {
                "landmark_motion_score": round(landmark_motion_score, 4),
                "motion_uniformity_score": round(motion_uniformity_score, 4),
                "is_rigid_replay": is_rigid_replay,
                "motion_detected": motion_detected,

                # Normalized Kinematic & Geometric Metrics:
                "landmark_displacement": round(raw_displacement, 2),
                "normalized_displacement": round(normalized_displacement, 4),
                "landmark_velocity": round(normalized_velocity, 4),
                "landmark_acceleration": round(normalized_acceleration, 4),
                "motion_variance": round(motion_variance, 6),
                "motion_correlation": round(motion_correlation, 4),
                "motion_entropy": round(motion_entropy, 4),
                "motion_stability": round(motion_stability, 4),
                "head_pose": {
                    "yaw": round(avg_yaw, 2),
                    "pitch": round(avg_pitch, 2),
                    "roll": round(avg_roll, 2)
                },
                "head_pose_stability": round(head_pose_stability, 4),
                "ear": round(latest_ear, 4),
                "mar": round(latest_mar, 4),
                "rigid_body_score": round(rigid_body_score, 4),

                "avg_displacement_px": round(raw_displacement, 2),
                "landmark_covariance": round(landmark_covariance, 6),
                "internal_deformability": round(internal_deformability, 4),
                "message": status_msg
            }

        except Exception as e:
            logger.warning(f"Error in landmark kinematic motion analysis: {e}")
            return {
                "landmark_motion_score": 0.50,
                "motion_uniformity_score": 0.50,
                "is_rigid_replay": False,
                "motion_detected": False,
                "landmark_displacement": 0.0,
                "normalized_displacement": 0.0,
                "landmark_velocity": 0.0,
                "landmark_acceleration": 0.0,
                "motion_variance": 0.0,
                "motion_correlation": 0.50,
                "motion_entropy": 0.0,
                "motion_stability": 1.0,
                "head_pose": {"yaw": 0.0, "pitch": 0.0, "roll": 0.0},
                "head_pose_stability": 1.0,
                "ear": 0.30,
                "mar": 0.50,
                "rigid_body_score": 0.50,
                "avg_displacement_px": 0.0,
                "internal_deformability": 0.50,
                "message": f"Kinematic motion analysis error: {e}"
            }


liveness_motion_service = LivenessMotionService()
