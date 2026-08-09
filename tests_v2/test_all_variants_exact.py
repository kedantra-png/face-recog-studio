# -*- coding: utf-8 -*-
"""
Evaluate All 4 Preprocessing Variants under Exact Model Architecture
----------------------------------------------------------------------
Evaluates MiniFASNetV2Exact (strict=True, 0 missing, 0 unexpected) across:
  - TEST A: BGR 0..255
  - TEST B: RGB 0..255
  - TEST C: BGR 0..1
  - TEST D: RGB 0..1
"""

import os
import sys
import cv2
import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
from typing import List, Tuple

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from tests_v2.test_exact_v2 import MiniFASNetV2Exact, CropImage


def main():
    checkpoint_rel_path = "resources/anti_spoof_models/2.7_80x80_MiniFASNetV2.pth"
    checkpoint_abs_path = os.path.join(PROJECT_ROOT, checkpoint_rel_path)

    state_dict = torch.load(checkpoint_abs_path, map_location="cpu")
    cleaned_state = {k.replace("module.", ""): v for k, v in state_dict.items()}

    model = MiniFASNetV2Exact(conv6_kernel=(5, 5), num_classes=3, img_channel=3)
    res = model.load_state_dict(cleaned_state, strict=True)
    model.eval()

    print("=" * 80)
    print("MINIFASNET V2 EXACT ARCHITECTURE — 4 PREPROCESSING VARIANTS TEST")
    print("=" * 80)
    print(f"Checkpoint: {checkpoint_rel_path}")
    print(f"Missing keys: {len(res.missing_keys)} | Unexpected keys: {len(res.unexpected_keys)} | strict_load: PASS\n")

    debug_dir = os.path.join(PROJECT_ROOT, "debug")
    frame_path = os.path.join(debug_dir, "step1_input_frame_0.jpg")
    frame = cv2.imread(frame_path)
    bbox = [240, 277, 131, 173]
    crop_bgr = CropImage.crop(frame, bbox, scale=2.7, out_w=80, out_h=80)

    # Prepare variants
    # Variant A: BGR 0..255
    t_a = torch.from_numpy(crop_bgr.transpose((2, 0, 1))).unsqueeze(0).float()

    # Variant B: RGB 0..255
    crop_rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
    t_b = torch.from_numpy(crop_rgb.transpose((2, 0, 1))).unsqueeze(0).float()

    # Variant C: BGR 0..1
    t_c = t_a / 255.0

    # Variant D: RGB 0..1
    t_d = t_b / 255.0

    variants = [
        ("TEST A (BGR 0-255)", t_a),
        ("TEST B (RGB 0-255)", t_b),
        ("TEST C (BGR 0-1)",   t_c),
        ("TEST D (RGB 0-1)",   t_d),
    ]

    class_names = {0: "PrintSpoof", 1: "RealFace", 2: "ScreenSpoof"}

    print(f"{'Variant':<20} {'Min':<8} {'Max':<8} {'Mean':<8} {'Std':<8} {'Logits [c0, c1, c2]':<32} {'Pred Label':<15}")
    print("-" * 105)

    with torch.no_grad():
        for name, t in variants:
            logits = model(t).cpu().numpy()[0]
            probs = F.softmax(model(t), dim=1).cpu().numpy()[0]
            pred = int(np.argmax(probs))

            t_min = round(float(t.min()), 3)
            t_max = round(float(t.max()), 3)
            t_mean = round(float(t.mean()), 3)
            t_std = round(float(t.std()), 3)

            logits_str = f"[{logits[0]:.2f}, {logits[1]:.2f}, {logits[2]:.2f}]"
            probs_str = f"[{probs[0]*100:.1f}%, {probs[1]*100:.1f}%, {probs[2]*100:.1f}%]"

            print(f"{name:<20} {t_min:<8} {t_max:<8} {t_mean:<8} {t_std:<8} {logits_str:<32} Class {pred} ({class_names[pred]}) - {probs_str}")

    print("-" * 105 + "\n")


if __name__ == "__main__":
    main()
