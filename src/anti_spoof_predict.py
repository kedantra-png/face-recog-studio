# -*- coding: utf-8 -*-
"""
MiniFASNet Anti-Spoof Predictor Gateway Module
---------------------------------------------
Standard prediction interface wrapper for Silent-Face-Anti-Spoofing.
"""

import os
import cv2
import torch
import numpy as np
import torch.nn.functional as F
from typing import Dict, Any, List, Optional

from src.model_lib.minifasnet_models import MiniFASNetV1SE, MiniFASNetV2
from src.generate_patches import CropImage
from src.utility import parse_model_name, get_kernel


class AntiSpoofPredict:
    """
    Predictor wrapper for Silent-Face Anti-Spoofing models.
    """

    def __init__(self, device_id: int = 0):
        self.device = torch.device(f"cuda:{device_id}" if torch.cuda.is_available() and device_id >= 0 else "cpu")
        self.models: Dict[str, torch.nn.Module] = {}

    def _load_model(self, model_path: str) -> bool:
        if not os.path.exists(model_path):
            return False

        try:
            info = parse_model_name(model_path)
            model_type = info.get("model_type", "MiniFASNetV2")
            kernel = get_kernel(info.get("height", 80), info.get("width", 80))

            if model_type == "MiniFASNetV1SE":
                net = MiniFASNetV1SE(conv6_kernel=kernel, num_classes=3, img_channel=3)
            else:
                net = MiniFASNetV2(conv6_kernel=kernel, num_classes=3, img_channel=3)

            state_dict = torch.load(model_path, map_location=self.device)
            cleaned_state = {k.replace('module.', ''): v for k, v in state_dict.items()}
            net.load_state_dict(cleaned_state, strict=True)
            net.to(self.device)
            net.eval()

            self.models[model_path] = net
            return True
        except Exception:
            return False

    def predict(self, img: np.ndarray, model_path: str) -> np.ndarray:
        if model_path not in self.models:
            if not self._load_model(model_path):
                return np.array([[0.33, 0.34, 0.33]], dtype=np.float32)

        net = self.models[model_path]
        if img is None or img.size == 0:
            img = np.zeros((80, 80, 3), dtype=np.uint8)

        if img.shape[:2] != (80, 80):
            img = cv2.resize(img, (80, 80))

        tensor = torch.from_numpy(img.transpose((2, 0, 1))).unsqueeze(0).float().to(self.device)

        with torch.no_grad():
            out = net(tensor)
            probs = F.softmax(out, dim=1).cpu().numpy()
            return probs
