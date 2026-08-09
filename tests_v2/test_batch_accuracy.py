# -*- coding: utf-8 -*-
"""
MiniFASNetV2 Batch Image Accuracy Testing Script
------------------------------------------------
Evaluates the verified MiniFASNetV2 model across all image frames in debug/
or any user-specified image directory / image file.

Usage:
  python tests_v2/test_batch_accuracy.py
  python tests_v2/test_batch_accuracy.py --dir debug
  python tests_v2/test_batch_accuracy.py --file debug/step1_input_frame_0.jpg
"""

import os
import sys
import argparse
import cv2
import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
from typing import List, Tuple, Dict, Any

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.model_lib.minifasnet_models import MiniFASNetV2
from tests_v2.test_exact_v2 import CropImage


def load_model() -> nn.Module:
    """Loads MiniFASNetV2 checkpoint with strict=True."""
    checkpoint_rel_path = "resources/anti_spoof_models/2.7_80x80_MiniFASNetV2.pth"
    checkpoint_abs_path = os.path.join(PROJECT_ROOT, checkpoint_rel_path)

    if not os.path.exists(checkpoint_abs_path):
        raise FileNotFoundError(f"Checkpoint not found at '{checkpoint_abs_path}'")

    model = MiniFASNetV2(conv6_kernel=(5, 5), num_classes=3, img_channel=3)
    state_dict = torch.load(checkpoint_abs_path, map_location="cpu")
    cleaned_state = {k.replace("module.", ""): v for k, v in state_dict.items()}

    model.load_state_dict(cleaned_state, strict=True)
    model.eval()
    return model


def evaluate_single_image(model: nn.Module, img_path: str, bbox: List[int] = None) -> Dict[str, Any]:
    """Evaluates MiniFASNetV2 on a single image file."""
    img = cv2.imread(img_path)
    if img is None:
        return {"error": f"Failed to read image at '{img_path}'"}

    h, w, _ = img.shape

    # If the image is already 80x80 (pre-cropped), use it directly
    if (h, w) == (80, 80):
        crop_bgr = img.copy()
        crop_source = "Pre-cropped 80x80"
    else:
        # Default face bbox if not provided
        if not bbox:
            bbox = [int(w * 0.25), int(h * 0.25), int(w * 0.5), int(h * 0.5)]
        crop_bgr = CropImage.crop(img, bbox, scale=2.7, out_w=80, out_h=80)
        crop_source = f"Scale 2.7 crop (bbox: {bbox})"

    # Verified Preprocessing: BGR float32 0..255 format
    tensor = torch.from_numpy(crop_bgr.transpose((2, 0, 1))).unsqueeze(0).float()

    model.eval()
    with torch.no_grad():
        logits = model(tensor).cpu().numpy()[0]
        probs = F.softmax(model(tensor), dim=1).cpu().numpy()[0]
        pred_class = int(np.argmax(probs))

    class_names = {0: "PrintSpoof", 1: "RealFace", 2: "ScreenSpoof"}

    return {
        "file_name": os.path.basename(img_path),
        "full_path": img_path,
        "image_size": f"{w}x{h}",
        "crop_source": crop_source,
        "logits": logits,
        "probs": probs,
        "print_prob": probs[0],
        "real_prob": probs[1],
        "screen_prob": probs[2],
        "predicted_class": pred_class,
        "predicted_label": class_names[pred_class],
        "confidence": probs[pred_class]
    }


def main():
    parser = argparse.ArgumentParser(description="MiniFASNetV2 Batch Accuracy Testing Script")
    parser.add_argument("--dir", type=str, default="debug", help="Directory containing images to test")
    parser.add_argument("--file", type=str, default=None, help="Specific image file to test")
    args = parser.parse_args()

    model = load_model()

    print("=" * 110)
    print("           MINIFASNET V2 BATCH IMAGE LIVENESS & ACCURACY EVALUATION REPORT")
    print("=" * 110)

    # Collect images to test
    image_files = []
    if args.file:
        file_abs = os.path.abspath(args.file) if os.path.isabs(args.file) else os.path.join(PROJECT_ROOT, args.file)
        if os.path.exists(file_abs):
            image_files.append(file_abs)
    else:
        target_dir = os.path.abspath(args.dir) if os.path.isabs(args.dir) else os.path.join(PROJECT_ROOT, args.dir)
        if os.path.exists(target_dir):
            for f in sorted(os.listdir(target_dir)):
                if f.lower().endswith((".jpg", ".jpeg", ".png", ".bmp", ".webp")):
                    image_files.append(os.path.join(target_dir, f))

    if not image_files:
        print(f"[ERROR] No valid images found to test.")
        return

    print(f"Total Target Images Found: {len(image_files)}")
    print(f"Model Checkpoint:        resources/anti_spoof_models/2.7_80x80_MiniFASNetV2.pth")
    print(f"Preprocessing Format:    BGR float32 [0.0, 255.0] (un-normalized float)")
    print("=" * 110)

    print(f"{'#':<3} {'Image File Name':<42} {'Orig Size':<11} {'Print %':<9} {'Real %':<9} {'Screen %':<9} {'Verdict':<20}")
    print("-" * 110)

    real_count = 0
    print_spoof_count = 0
    screen_spoof_count = 0

    # Default candidate frame bboxes for debug step1 input frames
    known_bboxes = {
        "step1_input_frame_0.jpg": [240, 277, 131, 173],
        "step1_input_frame_1.jpg": [238, 275, 133, 175],
        "step1_input_frame_2.jpg": [241, 278, 130, 172],
        "step1_input_frame_3.jpg": [239, 276, 132, 174],
    }

    for idx, fname in enumerate(image_files, 1):
        basename = os.path.basename(fname)
        bbox = known_bboxes.get(basename, None)

        res = evaluate_single_image(model, fname, bbox=bbox)
        if "error" in res:
            print(f"{idx:<3} {basename:<42} ERROR: {res['error']}")
            continue

        p_print = res['print_prob'] * 100
        p_real = res['real_prob'] * 100
        p_screen = res['screen_prob'] * 100
        pred_label = res['predicted_label']

        if res['predicted_class'] == 1:
            real_count += 1
            verdict_str = f"PASS ({pred_label})"
        elif res['predicted_class'] == 0:
            print_spoof_count += 1
            verdict_str = f"SPOOF ({pred_label})"
        else:
            screen_spoof_count += 1
            verdict_str = f"SPOOF ({pred_label})"

        print(f"{idx:<3} {basename:<42} {res['image_size']:<11} {p_print:<8.2f}% {p_real:<8.2f}% {p_screen:<8.2f}% {verdict_str:<20}")

    print("-" * 110)
    print("EVALUATION SUMMARY STATISTICS:")
    print(f"  Total Images Tested:    {len(image_files)}")
    print(f"  Real Face Verdicts:     {real_count}")
    print(f"  Print Spoof Verdicts:   {print_spoof_count}")
    print(f"  Screen Spoof Verdicts:  {screen_spoof_count}")
    print("=" * 110 + "\n")


if __name__ == "__main__":
    main()
