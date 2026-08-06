# -*- coding: utf-8 -*-
"""
Modular Anti-Spoofing & Risk Fusion Engine Service
---------------------------------------------------
Production-grade CPU-optimized Face Liveness & Anti-Spoofing Pipeline based on Minivision Silent-Face-Anti-Spoofing:
1. Exact Multi-Scale Crop Generation (CropImage):
   - MiniFASNetV1SE (4_0_0_80x80_MiniFASNetV1SE.pth): scale = 4.0, size = 80x80 BGR
   - MiniFASNetV2   (2.7_80x80_MiniFASNetV2.pth)   : scale = 2.7, size = 80x80 BGR
2. PyTorch Model Forward Pass & Softmax Accumulation:
   - Tensor normalization: x.float().div(255.0)
   - 3-Class Softmax Output: Class 0 (Spoof/Print), Class 1 (Real), Class 2 (Spoof/Screen)
3. Multi-Frame Ensemble Voting across 4 Frames:
   - Sums & averages 3-class softmax predictions across all 4 candidate frames.
   - argmax(prediction) == 1 indicates Real Face; argmax(prediction) in {0, 2} indicates Spoof Attack.
4. Risk Fusion Engine & Secondary Verification (TinyLiveness):
   - PASS      : argmax == 1 and Real Confidence >= 0.65.
   - UNCERTAIN : argmax == 1 and 0.35 <= Real Confidence < 0.65 -> Triggers TinyLiveness secondary check.
   - FAIL      : argmax in {0, 2} or Real Confidence < 0.35 or Rigid Replay.
"""

import os
import cv2
import time
import torch
import torch.nn as nn
import logging
import numpy as np
import torch.nn.functional as F
from typing import Dict, Any, Tuple, Optional, List

from src.pipeline.config import settings
from src.model_lib.minifasnet_models import MiniFASNetV1SE, MiniFASNetV2
from src.model_lib.tiny_liveness_model import tiny_liveness_model

logger = logging.getLogger("pipeline.anti_spoof")


class CropImage:
    """
    Exact Minivision Silent-Face-Anti-Spoofing crop generator.
    Scales bounding box without black padding by adjusting boundary shifts.
    """
    @staticmethod
    def crop(img: np.ndarray, bbox: List[int], scale: float, out_w: int = 80, out_h: int = 80) -> np.ndarray:
        if img is None or img.size == 0 or not bbox or len(bbox) < 4:
            return cv2.resize(img, (out_w, out_h)) if (img is not None and img.size > 0) else np.zeros((out_h, out_w, 3), dtype=np.uint8)

        src_h, src_w, _ = img.shape
        x, y, box_w, box_h = bbox[:4]

        # Apply minivision scale constraint
        eff_scale = min((src_h - 1) / max(1.0, float(box_h)), min((src_w - 1) / max(1.0, float(box_w)), float(scale)))

        new_width = box_w * eff_scale
        new_height = box_h * eff_scale
        center_x = box_w / 2.0 + x
        center_y = box_h / 2.0 + y

        left_top_x = center_x - new_width / 2.0
        left_top_y = center_y - new_height / 2.0
        right_bottom_x = center_x + new_width / 2.0
        right_bottom_y = center_y + new_height / 2.0

        if left_top_x < 0:
            right_bottom_x -= left_top_x
            left_top_x = 0
        if left_top_y < 0:
            right_bottom_y -= left_top_y
            left_top_y = 0
        if right_bottom_x >= src_w:
            left_top_x -= (right_bottom_x - src_w + 1)
            right_bottom_x = src_w - 1
        if right_bottom_y >= src_h:
            left_top_y -= (right_bottom_y - src_h + 1)
            right_bottom_y = src_h - 1

        x1, y1, x2, y2 = int(left_top_x), int(left_top_y), int(right_bottom_x), int(right_bottom_y)
        crop = img[y1:y2, x1:x2]

        if crop.size == 0:
            return cv2.resize(img, (out_w, out_h))

        return cv2.resize(crop, (out_w, out_h), interpolation=cv2.INTER_LINEAR)


def _resolve_model_path(path_str: str) -> str:
    if path_str and os.path.exists(path_str):
        return path_str
    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    candidate = os.path.join(root_dir, path_str)
    if os.path.exists(candidate):
        return candidate
    # Fallback check under resources/anti_spoof_models
    filename = os.path.basename(path_str)
    candidate2 = os.path.join(root_dir, "resources", "anti_spoof_models", filename)
    if os.path.exists(candidate2):
        return candidate2
    return path_str


class AntiSpoofService:
    """
    Modular Liveness Verification & Risk Fusion Engine.
    """

    def __init__(self):
        self.v1se_model = None
        self.v2_model = None
        self.is_loaded = False
        self._initialized = False

    def _init_models(self) -> None:
        """Loads PyTorch model weights for MiniFASNetV1SE and MiniFASNetV2 on CPU once."""
        if self._initialized:
            return

        start_t = time.time()

        # Load MiniFASNetV1SE (scale 4.0)
        try:
            v1se_path = _resolve_model_path(settings.MINIFASNET_V1SE_MODEL_PATH)
            if os.path.exists(v1se_path):
                self.v1se_model = MiniFASNetV1SE(conv6_kernel=(5, 5), num_classes=3, img_channel=3)
                state_dict = torch.load(v1se_path, map_location='cpu')
                cleaned_state = {k.replace('module.', ''): v for k, v in state_dict.items()}
                self.v1se_model.load_state_dict(cleaned_state, strict=True)
                self.v1se_model.eval()
                print(f"[MODEL LOAD SUCCESS] MiniFASNetV1SE loaded strictly from '{v1se_path}'.")
                logger.info(f"MiniFASNetV1SE loaded successfully from '{v1se_path}'.")
            else:
                print(f"[MODEL LOAD ERROR] CRITICAL: MiniFASNetV1SE weight file not found at '{v1se_path}'.")
                logger.error(f"CRITICAL: MiniFASNetV1SE weight file not found at '{v1se_path}'.")
        except Exception as e:
            print(f"[MODEL LOAD FAILED] MiniFASNetV1SE error: {e}")
            import traceback; traceback.print_exc()
            logger.error(f"Failed to load MiniFASNetV1SE model: {e}")
            self.v1se_model = None

        # Load MiniFASNetV2 (scale 2.7)
        try:
            v2_path = _resolve_model_path(settings.MINIFASNET_V2_MODEL_PATH)
            if os.path.exists(v2_path):
                self.v2_model = MiniFASNetV2(conv6_kernel=(5, 5), num_classes=3, img_channel=3)
                state_dict = torch.load(v2_path, map_location='cpu')
                cleaned_state = {k.replace('module.', ''): v for k, v in state_dict.items()}
                self.v2_model.load_state_dict(cleaned_state, strict=True)
                self.v2_model.eval()
                print(f"[MODEL LOAD SUCCESS] MiniFASNetV2 loaded strictly from '{v2_path}'.")
                logger.info(f"MiniFASNetV2 loaded successfully from '{v2_path}'.")
            else:
                print(f"[MODEL LOAD ERROR] CRITICAL: MiniFASNetV2 weight file not found at '{v2_path}'.")
                logger.error(f"CRITICAL: MiniFASNetV2 weight file not found at '{v2_path}'.")
        except Exception as e:
            print(f"[MODEL LOAD FAILED] MiniFASNetV2 error: {e}")
            import traceback; traceback.print_exc()
            logger.error(f"Failed to load MiniFASNetV2 model: {e}")
            self.v2_model = None

        # Initialize TinyLiveness ONNX/PyTorch secondary verification model
        try:
            tiny_path = _resolve_model_path(settings.TINY_LIVENESS_MODEL_PATH)
            tiny_liveness_model.load_model(tiny_path)
        except Exception as e:
            logger.warning(f"Failed to initialize TinyLiveness: {e}")

        self.is_loaded = True
        self._initialized = True
        logger.info(f"AntiSpoofService initialized in {round((time.time() - start_t) * 1000, 2)}ms. Models: v1se={self.v1se_model is not None}, v2={self.v2_model is not None}")

    def warmup(self) -> None:
        """Warmup handler."""
        self._init_models()

    def _predict_single_model(self, model: nn.Module, crop_bgr: np.ndarray) -> np.ndarray:
        """
        Executes model forward pass on an 80x80 BGR face crop and returns 3-class softmax probabilities.
        Returns:
            softmax array of shape (3,): [prob_class0_spoof, prob_class1_real, prob_class2_spoof]
        """
        if crop_bgr is None or crop_bgr.shape[:2] != (80, 80):
            crop_bgr = cv2.resize(crop_bgr, (80, 80)) if (crop_bgr is not None and crop_bgr.size > 0) else np.zeros((80, 80, 3), dtype=np.uint8)

        # Minivision input tensor normalization: HxWxC [0, 255] -> CxHxW [0.0, 1.0]
        tensor = torch.from_numpy(crop_bgr.transpose((2, 0, 1))).unsqueeze(0).float().div(255.0)

        with torch.no_grad():
            try:
                out = model(tensor)
                softmax = F.softmax(out, dim=1).numpy()[0]  # shape (3,)
                return softmax
            except Exception as e:
                logger.warning(f"Error in MiniFASNet model forward pass: {e}")
                return np.array([0.33, 0.34, 0.33], dtype=np.float32)

    def predict_multi_frame(
        self,
        frames: List[np.ndarray],
        face_bboxes: Optional[List[Optional[List[int]]]] = None,
        motion_analysis: Optional[Dict[str, Any]] = None,
        quality_scores: Optional[List[float]] = None
    ) -> Dict[str, Any]:
        """
        Executes MiniFASNetV1SE (scale 4.0) and MiniFASNetV2 (scale 2.7) across 4 candidate frames,
        performs 3-class softmax accumulation, landmark motion risk fusion, and conditional TinyLiveness verification.
        """
        start_time = time.time()
        if not self._initialized:
            self._init_models()

        n_eval = len(frames)
        if n_eval == 0:
            return {
                "is_real": False,
                "liveness_decision": "FAIL",
                "real_confidence": 0.0,
                "spoof_confidence": 1.0,
                "voting_result": 0.0,
                "minifasnet_v1se_score": 0.0,
                "minifasnet_v2_score": 0.0,
                "landmark_motion_score": 0.0,
                "motion_uniformity_score": 0.50,
                "quality_score": 0.0,
                "tiny_liveness_executed": False,
                "latency_ms": 0.0,
                "message": "No candidate frames provided"
            }

        # Motion analysis scores
        motion_res = motion_analysis or {}
        landmark_motion_score = float(motion_res.get("landmark_motion_score", 0.50))
        motion_uniformity_score = float(motion_res.get("motion_uniformity_score", 0.50))
        is_rigid_replay = bool(motion_res.get("is_rigid_replay", False))

        avg_quality_score = float(np.mean(quality_scores)) if quality_scores else 0.80

        # -------------------------------------------------------------------------------------
        # 1. SILENT-FACE MULTI-MODEL ENSEMBLE PREDICTION ACROSS 4 CANDIDATE FRAMES
        # -------------------------------------------------------------------------------------
        # Accumulate 3-class prediction matrix of shape (1, 3)
        accumulated_predictions = np.zeros((1, 3), dtype=np.float32)
        v1se_real_probs = []
        v2_real_probs = []

        num_valid_models = 0
        if self.v1se_model is not None:
            num_valid_models += 1
        if self.v2_model is not None:
            num_valid_models += 1
        num_valid_models = max(1, num_valid_models)

        eval_frames = frames[:4]
        for idx, frame in enumerate(eval_frames):
            bbox = face_bboxes[idx] if (face_bboxes and idx < len(face_bboxes)) else [0, 0, frame.shape[1], frame.shape[0]]

            # Model 1: MiniFASNetV1SE with scale 4.0
            if self.v1se_model is not None:
                crop_v1se = CropImage.crop(frame, bbox, scale=4.0, out_w=80, out_h=80)
                sm_v1se = self._predict_single_model(self.v1se_model, crop_v1se)
                accumulated_predictions[0] += sm_v1se
                v1se_real_probs.append(float(sm_v1se[1]))

            # Model 2: MiniFASNetV2 with scale 2.7
            if self.v2_model is not None:
                crop_v2 = CropImage.crop(frame, bbox, scale=2.7, out_w=80, out_h=80)
                sm_v2 = self._predict_single_model(self.v2_model, crop_v2)
                accumulated_predictions[0] += sm_v2
                v2_real_probs.append(float(sm_v2[1]))

        # Normalize accumulated predictions across (n_frames * num_models)
        total_evals = len(eval_frames) * num_valid_models
        normalized_probs = (accumulated_predictions[0] / total_evals)  # shape (3,): [prob_class0, prob_class1, prob_class2]

        pred_label = int(np.argmax(normalized_probs))
        model_real_confidence = float(normalized_probs[1])
        model_spoof_confidence = float(normalized_probs[0] + normalized_probs[2])

        avg_v1se = float(np.mean(v1se_real_probs)) if v1se_real_probs else 0.50
        avg_v2 = float(np.mean(v2_real_probs)) if v2_real_probs else 0.50

        # -------------------------------------------------------------------------------------
        # 2. WEIGHTED MULTI-FACTOR FUSION SCORE
        # -------------------------------------------------------------------------------------
        w_v1se = settings.WEIGHT_MINIFASNET_V1SE
        w_v2 = settings.WEIGHT_MINIFASNET_V2
        w_motion = settings.WEIGHT_LANDMARK_MOTION
        w_unif = settings.WEIGHT_MOTION_UNIFORMITY
        w_qual = settings.WEIGHT_FACE_QUALITY

        weighted_score = (
            (w_v1se * avg_v1se) +
            (w_v2 * avg_v2) +
            (w_motion * landmark_motion_score) +
            (w_unif * (1.0 - motion_uniformity_score)) +
            (w_qual * avg_quality_score)
        )
        weighted_score = float(max(0.0, min(1.0, weighted_score)))

        # -------------------------------------------------------------------------------------
        # 3. RISK FUSION ENGINE CRITERIA (PASS / UNCERTAIN / FAIL)
        # -------------------------------------------------------------------------------------
        # Minivision Silent-Face-Anti-Spoofing classification criteria:
        # pred_label == 1 means REAL face class has maximum probability.
        # pred_label in {0, 2} means SPOOF (Print or Screen) class has maximum probability!
        tiny_liveness_executed = False
        tiny_liveness_score = None

        if is_rigid_replay or pred_label != 1 or model_real_confidence < 0.35 or weighted_score < 0.35:
            initial_decision = "FAIL"
        elif pred_label == 1 and model_real_confidence >= 0.65 and weighted_score >= 0.65:
            initial_decision = "PASS"
        else:
            initial_decision = "UNCERTAIN"

        final_decision = initial_decision

        # -------------------------------------------------------------------------------------
        # 4. SECONDARY VERIFICATION (TinyLiveness) - EXECUTED FOR UNCERTAIN CASES
        # -------------------------------------------------------------------------------------
        if initial_decision == "UNCERTAIN":
            tiny_liveness_executed = True
            best_crop = CropImage.crop(frames[0], bbox=face_bboxes[0] if face_bboxes else [0, 0, frames[0].shape[1], frames[0].shape[0]], scale=2.7, out_w=112, out_h=112)
            sec_res = tiny_liveness_model.predict(best_crop)
            tiny_liveness_score = float(sec_res.get("liveness_score", 0.50))

            if sec_res.get("is_real", False) and tiny_liveness_score >= 0.55 and model_real_confidence >= 0.40:
                final_decision = "PASS"
                weighted_score = float(max(0.85, weighted_score + 0.30))
                status_msg = "Liveness verified via Secondary TinyLiveness check."
            else:
                final_decision = "FAIL"
                weighted_score = float(max(0.05, weighted_score - 0.25))
                status_msg = "Secondary TinyLiveness check failed. Presentation attack detected."
        elif final_decision == "PASS":
            status_msg = f"High-confidence liveness verified across {n_eval} frame(s)."
        else:
            status_msg = f"Presentation spoof attack detected (Silent-Face label={pred_label}, real_prob={model_real_confidence*100:.1f}%). Verification rejected."

        is_real = bool(final_decision == "PASS")
        real_confidence = round(model_real_confidence if final_decision == "PASS" else min(model_real_confidence, weighted_score), 4)
        spoof_confidence = round(1.0 - real_confidence, 4)
        total_latency = round((time.time() - start_time) * 1000, 2)

        # -------------------------------------------------------------------------------------
        # 5. PIN-TO-PIN DETAILED STAGE LOGGING
        # -------------------------------------------------------------------------------------
        log_header = "\n==================== [SILENT-FACE ENSEMBLE PIPELINE PIN-TO-PIN LOG] ===================="
        log_lines = [
            log_header,
            f"[FRAME EVALUATION] Candidate Frames: {n_eval} | Total Latency: {total_latency}ms",
            f"[SILENT-FACE CLASS] Pred Label: {pred_label} (0=PrintSpoof, 1=RealFace, 2=ScreenSpoof)",
            f"[MODEL ACCURACY]    Class 1 (Real) Prob: {model_real_confidence*100:.2f}% | Class 0/2 (Spoof) Prob: {model_spoof_confidence*100:.2f}%",
            f"[MINIFASNET V1SE]   Scale 4.0 Crop Real Prob: {avg_v1se*100:.2f}%",
            f"[MINIFASNET V2]     Scale 2.7 Crop Real Prob: {avg_v2*100:.2f}%",
            f"[STAGE 1 - QUALITY] Face Quality Score       : {avg_quality_score:.4f}",
            f"[STAGE 2 - MOTION]  Landmark Motion Score    : {landmark_motion_score:.4f} (AvgDisp={motion_res.get('avg_displacement_px', 0)}px)",
            f"[STAGE 3 - UNIFORM] Motion Uniformity Score  : {motion_uniformity_score:.4f} (IsRigidReplay={is_rigid_replay})",
            f"[STAGE 4 - VOTING]  Weighted Score           : {weighted_score:.4f} | Initial State: {initial_decision}",
            f"[STAGE 5 - SECOND] TinyLiveness Executed     : {tiny_liveness_executed} (TinyScore={tiny_liveness_score})",
            f"[FINAL DECISION]    Verdict = {final_decision} (RealConf={real_confidence*100:.1f}%, SpoofConf={spoof_confidence*100:.1f}%) | {status_msg}",
            "=========================================================================================================\n"
        ]
        print("\n".join(log_lines))
        logger.info(f"AntiSpoof Verification: verdict={final_decision}, real_conf={real_confidence*100:.1f}%, label={pred_label}")

        return {
            "is_real": is_real,
            "liveness_decision": final_decision,
            "initial_decision": initial_decision,
            "pred_label": pred_label,
            "real_confidence": real_confidence,
            "spoof_confidence": spoof_confidence,
            "voting_result": round(weighted_score, 4),
            "minifasnet_v1se_score": round(avg_v1se, 4),
            "minifasnet_v2_score": round(avg_v2, 4),
            "landmark_motion_score": landmark_motion_score,
            "motion_uniformity_score": motion_uniformity_score,
            "quality_score": round(avg_quality_score, 4),
            "tiny_liveness_executed": tiny_liveness_executed,
            "tiny_liveness_score": tiny_liveness_score,
            "latency_ms": total_latency,
            "message": status_msg
        }

    def predict(self, img: np.ndarray, face_bbox: Optional[List[int]] = None) -> Dict[str, Any]:
        """Single frame liveness helper."""
        return self.predict_multi_frame([img], face_bboxes=[face_bbox] if face_bbox else None)


anti_spoof_service = AntiSpoofService()
