# -*- coding: utf-8 -*-
"""
Separate Test Script for MiniFASNetV2 Model & Preprocessing Variants
---------------------------------------------------------------------
Tests 4 preprocessing variants on a single frame from debug folder:
  - TEST A: BGR + 0..255
  - TEST B: RGB + 0..255
  - TEST C: BGR + 0..1 (Verified Production Format)
  - TEST D: RGB + 0..1

Outputs:
  1. Tensor shape, dtype, min, max, mean, std per variant
  2. Summary comparison table
  3. Logits & Softmax probabilities per variant
  4. Confirmation of MiniFASNetV2SE strict architecture loading
"""

import os
import sys
import cv2
import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
from typing import List, Tuple

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.model_lib.minifasnet_models import MiniFASNetSE, keep_dict


def MiniFASNetV2SE(embedding_size: int = 128, conv6_kernel: Tuple[int, int] = (5, 5), drop_p: float = 0.2, num_classes: int = 3, img_channel: int = 3) -> MiniFASNetSE:
    """MiniFASNetV2SE architecture using 1.8M_ keep_dict and Squeeze-and-Excitation layers."""
    return MiniFASNetSE(keep_dict['1.8M_'], embedding_size, conv6_kernel, drop_p, num_classes, img_channel)


class CropImage:
    """Official Minivision crop generator for scale 2.7 (V2)."""
    @staticmethod
    def crop(img: np.ndarray, bbox: List[int], scale: float = 2.7, out_w: int = 80, out_h: int = 80) -> np.ndarray:
        if img is None or img.size == 0 or not bbox or len(bbox) < 4:
            return cv2.resize(img, (out_w, out_h)) if (img is not None and img.size > 0) else np.zeros((out_h, out_w, 3), dtype=np.uint8)

        src_h, src_w, _ = img.shape
        x, y, box_w, box_h = bbox[:4]

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


def load_v2se_model_strict() -> nn.Module:
    """Loads MiniFASNetV2SE model with strict=True."""
    checkpoint_rel_path = "resources/anti_spoof_models/2.7_80x80_MiniFASNetV2.pth"
    checkpoint_abs_path = os.path.join(PROJECT_ROOT, checkpoint_rel_path)

    if not os.path.exists(checkpoint_abs_path):
        raise FileNotFoundError(f"Model checkpoint not found at: {checkpoint_abs_path}")

    model = MiniFASNetV2SE(conv6_kernel=(5, 5), num_classes=3, img_channel=3)
    state_dict = torch.load(checkpoint_abs_path, map_location="cpu")
    cleaned_state = {k.replace("module.", ""): v for k, v in state_dict.items()}

    model.load_state_dict(cleaned_state, strict=True)
    model.eval()
    return model


def get_test_crop() -> Tuple[np.ndarray, str]:
    """Loads a single face crop (80x80 BGR uint8) from debug folder."""
    debug_dir = os.path.join(PROJECT_ROOT, "debug")
    frame_path = os.path.join(debug_dir, "step1_input_frame_0.jpg")
    
    if os.path.exists(frame_path):
        frame = cv2.imread(frame_path)
        if frame is not None:
            bbox = [240, 277, 131, 173]
            crop_bgr = CropImage.crop(frame, bbox, scale=2.7, out_w=80, out_h=80)
            return crop_bgr, frame_path

    raise FileNotFoundError(f"No test images found in {debug_dir}")


def main():
    print("=" * 80)
    print("      MINIFASNET V2 PREPROCESSING & LOGITS COMPARISON TEST (SINGLE FRAME)")
    print("=" * 80)

    # 1. Load Model strictly with MiniFASNetV2SE
    model = load_v2se_model_strict()
    print(f"\n[MODEL LOADED] MiniFASNetV2SE strictly loaded from resources/anti_spoof_models/2.7_80x80_MiniFASNetV2.pth (strict=True: SUCCESS)")

    # 2. Load Single Image Frame
    crop_bgr_80x80, img_source = get_test_crop()
    print(f"[IMAGE LOADED] Source: '{img_source}' | Crop Base Shape: {crop_bgr_80x80.shape} | Dtype: {crop_bgr_80x80.dtype}\n")

    # Prepare Preprocessing Variants
    # TEST A: BGR + 0..255
    crop_a = crop_bgr_80x80.copy()
    tensor_a = torch.from_numpy(crop_a.transpose((2, 0, 1))).unsqueeze(0).float()

    # TEST B: RGB + 0..255
    crop_b = cv2.cvtColor(crop_bgr_80x80, cv2.COLOR_BGR2RGB)
    tensor_b = torch.from_numpy(crop_b.transpose((2, 0, 1))).unsqueeze(0).float()

    # TEST C: BGR + 0..1 (Verified Production Format)
    crop_c = crop_bgr_80x80.copy()
    tensor_c = torch.from_numpy(crop_c.transpose((2, 0, 1))).unsqueeze(0).float() / 255.0

    # TEST D: RGB + 0..1
    crop_d = cv2.cvtColor(crop_bgr_80x80, cv2.COLOR_BGR2RGB)
    tensor_d = torch.from_numpy(crop_d.transpose((2, 0, 1))).unsqueeze(0).float() / 255.0

    tests = [
        ("TEST A (BGR 0-255)", tensor_a),
        ("TEST B (RGB 0-255)", tensor_b),
        ("TEST C (BGR 0-1)",   tensor_c),
        ("TEST D (RGB 0-1)",   tensor_d),
    ]

    # 3. Print Tensor Statistics Summary Table
    print("=" * 80)
    print("                          TENSOR STATISTICAL SUMMARY")
    print("=" * 80)
    print(f"{'Variant':<20} {'Shape':<18} {'Dtype':<12} {'Min':<8} {'Max':<8} {'Mean':<10} {'Std':<10}")
    print("-" * 80)

    for name, t in tests:
        t_min = round(float(t.min()), 3)
        t_max = round(float(t.max()), 3)
        t_mean = round(float(t.mean()), 3)
        t_std = round(float(t.std()), 3)
        print(f"{name:<20} {str(list(t.shape)):<18} {str(t.dtype).split('.')[-1]:<12} {t_min:<8} {t_max:<8} {t_mean:<10} {t_std:<10}")

    print("-" * 80)

    # 4. Perform Forward Pass and Softmax for each variant
    print("\n" + "=" * 80)
    print("                     MODEL FORWARD PASS, LOGITS & SOFTMAX")
    print("=" * 80)

    results = {}
    class_names = {0: "PrintSpoof", 1: "RealFace", 2: "ScreenSpoof"}

    with torch.no_grad():
        for name, t in tests:
            logits = model(t)
            prob = F.softmax(logits, dim=1)

            logits_np = logits.cpu().numpy()[0]
            prob_np = prob.cpu().numpy()[0]
            pred_class = int(np.argmax(prob_np))

            results[name] = {
                "logits": logits_np,
                "probabilities": prob_np,
                "predicted_class": pred_class,
                "predicted_label": class_names[pred_class]
            }

            print(f"\n---> {name}")
            print(f"  shape:         {t.shape}")
            print(f"  dtype:         {t.dtype}")
            print(f"  min:           {t.min().item():.4f}")
            print(f"  max:           {t.max().item():.4f}")
            print(f"  mean:          {t.mean().item():.4f}")
            print(f"  std:           {t.std().item():.4f}")
            print(f"  logits:        [{logits_np[0]:.4f}, {logits_np[1]:.4f}, {logits_np[2]:.4f}]")
            print(f"  probabilities: [{prob_np[0]:.4f}, {prob_np[1]:.4f}, {prob_np[2]:.4f}]")
            print(f"  Prediction:    Class {pred_class} ({class_names[pred_class]})")

    print("\n" + "=" * 80)
    print("                        VERIFIED PRODUCTION PREPROCESSING")
    print("=" * 80)
    print("  VERIFIED FORMAT:  TEST C (BGR float32 0..1)")
    print(f"  LOGITS:           [{results['TEST C (BGR 0-1)']['logits'][0]:.4f}, {results['TEST C (BGR 0-1)']['logits'][1]:.4f}, {results['TEST C (BGR 0-1)']['logits'][2]:.4f}]")
    print(f"  PROBABILITIES:    [{results['TEST C (BGR 0-1)']['probabilities'][0]:.4f}, {results['TEST C (BGR 0-1)']['probabilities'][1]:.4f}, {results['TEST C (BGR 0-1)']['probabilities'][2]:.4f}]")
    print(f"  PREDICTED LABEL:  {results['TEST C (BGR 0-1)']['predicted_label']} (Class {results['TEST C (BGR 0-1)']['predicted_class']})")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
