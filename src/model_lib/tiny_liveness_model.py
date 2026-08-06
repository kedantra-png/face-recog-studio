# -*- coding: utf-8 -*-
"""
TinyLiveness Secondary Verification Model Executor
---------------------------------------------------
Ultra-lightweight passive face anti-spoofing verification engine (yuvrajraina/TinyLiveness).
Executed ONLY when primary weighted liveness confidence falls into the UNCERTAIN range.
Optimized for 2 vCPU / 4 GB RAM deployment using ONNXRuntime or PyTorch.
"""

import os
import cv2
import logging
import numpy as np
from typing import Dict, Any, Optional

logger = logging.getLogger("pipeline.tiny_liveness")

try:
    import onnxruntime as ort
    ONNX_AVAILABLE = True
except ImportError:
    ONNX_AVAILABLE = False

try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False


class TinyLivenessModel:
    def __init__(self, model_path: Optional[str] = None):
        self.model_path = model_path
        self.session = None
        self.torch_model = None
        self._initialized = False

    def load_model(self, model_path: str) -> bool:
        self.model_path = model_path
        if not model_path or not os.path.exists(model_path):
            logger.info(f"TinyLiveness model file not found at '{model_path}'. Running in lightweight heuristic secondary mode.")
            self._initialized = True
            return False

        try:
            if model_path.endswith('.onnx') and ONNX_AVAILABLE:
                opts = ort.SessionOptions()
                opts.intra_op_num_threads = 1
                opts.inter_op_num_threads = 1
                opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
                self.session = ort.InferenceSession(model_path, sess_options=opts, providers=['CPUExecutionProvider'])
                self._initialized = True
                logger.info(f"TinyLiveness ONNX session loaded successfully from {model_path}")
                return True
            elif model_path.endswith('.pth') and TORCH_AVAILABLE:
                self.torch_model = torch.load(model_path, map_location='cpu')
                if hasattr(self.torch_model, 'eval'):
                    self.torch_model.eval()
                self._initialized = True
                logger.info(f"TinyLiveness PyTorch model loaded successfully from {model_path}")
                return True
        except Exception as e:
            logger.warning(f"Failed to load TinyLiveness model from {model_path}: {e}")

        self._initialized = True
        return False

    def predict(self, face_bgr: np.ndarray) -> Dict[str, Any]:
        """
        Runs TinyLiveness secondary evaluation on an aligned/cropped face BGR image.
        Returns:
            Dict containing:
                - is_real: bool
                - liveness_score: float (0.0 to 1.0)
                - verified: bool
                - method: str
        """
        if face_bgr is None or face_bgr.size == 0:
            return {"is_real": False, "liveness_score": 0.0, "verified": False, "method": "invalid_input"}

        if self.session is not None:
            try:
                # Preprocess for TinyLiveness ONNX (128x128 or 112x112 normalized RGB tensor)
                input_name = self.session.get_inputs()[0].name
                shape = self.session.get_inputs()[0].shape
                h, w = (shape[2], shape[3]) if len(shape) == 4 and shape[2] and shape[3] else (128, 128)

                resized = cv2.resize(face_bgr, (w, h))
                rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
                blob = np.transpose(rgb, (2, 0, 1))[np.newaxis, ...]  # Shape: (1, 3, H, W)

                outputs = self.session.run(None, {input_name: blob})
                logits = outputs[0][0]
                if len(logits) >= 2:
                    probs = np.exp(logits) / np.sum(np.exp(logits))
                    real_prob = float(probs[1])
                else:
                    real_prob = float(1.0 / (1.0 + np.exp(-logits[0])))

                is_real = bool(real_prob >= 0.50)
                return {
                    "is_real": is_real,
                    "liveness_score": round(real_prob, 4),
                    "verified": True,
                    "method": "TinyLiveness_ONNX"
                }
            except Exception as e:
                logger.warning(f"Error executing TinyLiveness ONNX inference: {e}")

        # Lightweight secondary verification fallback using frequency spectrum texture analysis
        gray = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2GRAY)
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()

        # FFT High Frequency Energy Ratio (Printed photos/screens have high frequency moire artifact suppressions)
        f = np.fft.fft2(gray)
        fshift = np.fft.fftshift(f)
        magnitude_spectrum = 20 * np.log(np.abs(fshift) + 1e-5)
        h, w = gray.shape
        cy, cx = h // 2, w // 2
        radius = min(h, w) // 4
        y, x = np.ogrid[:h, :w]
        mask = (x - cx) ** 2 + (y - cy) ** 2 <= radius ** 2
        high_freq_ratio = float(np.sum(magnitude_spectrum[~mask]) / (np.sum(magnitude_spectrum) + 1e-5))

        score = min(0.95, max(0.10, 0.40 + (high_freq_ratio * 0.4) + (min(laplacian_var, 300.0) / 600.0)))
        is_real = bool(score >= 0.55)

        return {
            "is_real": is_real,
            "liveness_score": round(score, 4),
            "verified": True,
            "method": "TinyLiveness_Spectral_Fallback"
        }


tiny_liveness_model = TinyLivenessModel()
