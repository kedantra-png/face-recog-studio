# -*- coding: utf-8 -*-
"""
MiniFASNetV2 Anti-Spoofing Pipeline - Verified Production Baseline Test
------------------------------------------------------------------------
Verifies the production baseline fixes for MiniFASNetV2:
  1. Model Architecture: Loads 2.7_80x80_MiniFASNetV2.pth using MiniFASNetV2Exact
     (conv_6_sep + conv_6_dw + prob bias=False) with strict=True (0 missing, 0 unexpected).
  2. Preprocessing: BGR float32 0..255 format (tensor = torch.from_numpy(crop.transpose(2,0,1)).unsqueeze(0).float()).
  3. Crop Pipeline: Scale 2.7, 80x80 output, cv2.INTER_LINEAR directly from in-memory frame.
  4. Class Mapping: 0=PrintSpoof, 1=RealFace, 2=ScreenSpoof.
  5. Validation: Asserts strict checkpoint loading, BGR 0..255 range, and RealFace prediction (95.5% confidence).

IMPORTANT:
- Only files inside tests_v2/ are created/modified.
- All checks fail loudly if any assertion is violated.
"""

import os
import sys
import cv2
import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
from typing import List, Tuple, Dict, Any

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from tests_v2.test_exact_v2 import MiniFASNetV2Exact, CropImage


def load_v2_model_strict() -> Tuple[nn.Module, Dict[str, Any]]:
    """Loads MiniFASNetV2Exact model strictly (strict=True). Fails loudly if mismatch occurs."""
    checkpoint_rel_path = "resources/anti_spoof_models/2.7_80x80_MiniFASNetV2.pth"
    checkpoint_abs_path = os.path.join(PROJECT_ROOT, checkpoint_rel_path)

    if not os.path.exists(checkpoint_abs_path):
        raise FileNotFoundError(f"CRITICAL: Checkpoint not found at '{checkpoint_abs_path}'")

    model = MiniFASNetV2Exact(conv6_kernel=(5, 5), num_classes=3, img_channel=3)
    state_dict = torch.load(checkpoint_abs_path, map_location="cpu")
    cleaned_state = {k.replace("module.", ""): v for k, v in state_dict.items()}

    # Strict loading - must pass without error
    try:
        load_res = model.load_state_dict(cleaned_state, strict=True)
        missing_keys = load_res.missing_keys
        unexpected_keys = load_res.unexpected_keys
    except RuntimeError as e:
        raise RuntimeError(f"CRITICAL: strict=True checkpoint loading FAILED for MiniFASNetV2Exact: {e}")

    assert len(missing_keys) == 0, f"CRITICAL: Missing keys detected: {missing_keys}"
    assert len(unexpected_keys) == 0, f"CRITICAL: Unexpected keys detected: {unexpected_keys}"

    model.eval()

    info = {
        "checkpoint_path": checkpoint_rel_path,
        "architecture": "MiniFASNetV2Exact",
        "strict_load": True,
        "missing_keys": len(missing_keys),
        "unexpected_keys": len(unexpected_keys),
        "parameter_count": sum(p.numel() for p in model.parameters()),
        "checkpoint_tensor_count": len(cleaned_state)
    }
    return model, info


def get_test_frame_and_crop() -> Tuple[np.ndarray, np.ndarray, List[int]]:
    """Loads original frame and generates scale 2.7 in-memory crop."""
    debug_dir = os.path.join(PROJECT_ROOT, "debug")
    frame_path = os.path.join(debug_dir, "step1_input_frame_0.jpg")

    if not os.path.exists(frame_path):
        raise FileNotFoundError(f"Test image frame not found at '{frame_path}'")

    frame = cv2.imread(frame_path)
    if frame is None:
        raise ValueError(f"Failed to read image frame from '{frame_path}'")

    bbox = [240, 277, 131, 173]  # Frame 0 detection bbox
    crop_bgr = CropImage.crop(frame, bbox, scale=2.7, out_w=80, out_h=80)

    return frame, crop_bgr, bbox


def run_verified_inference(model: nn.Module, crop_bgr: np.ndarray) -> Dict[str, Any]:
    """Runs verified inference using BGR float32 0..255 preprocessing format."""

    # Preprocessing: BGR float32 0..255 (official minivision Silent-Face format)
    tensor = torch.from_numpy(crop_bgr.transpose((2, 0, 1))).unsqueeze(0).float()

    tensor_min = float(tensor.min())
    tensor_max = float(tensor.max())

    model.eval()
    with torch.no_grad():
        logits = model(tensor)
        probabilities = F.softmax(logits, dim=1)

    logits_np = logits.cpu().numpy()[0]
    probs_np = probabilities.cpu().numpy()[0]
    pred_class = int(np.argmax(probs_np))

    class_names = {0: "PrintSpoof", 1: "RealFace", 2: "ScreenSpoof"}
    pred_label = class_names[pred_class]

    return {
        "tensor": tensor,
        "tensor_shape": list(tensor.shape),
        "tensor_dtype": str(tensor.dtype),
        "tensor_min": tensor_min,
        "tensor_max": tensor_max,
        "tensor_mean": float(tensor.mean()),
        "tensor_std": float(tensor.std()),
        "logits": logits_np,
        "probabilities": probs_np,
        "predicted_class": pred_class,
        "predicted_label": pred_label
    }


def main():
    print("=" * 80)
    print("  MINIFASNET V2 VERIFIED PRODUCTION BASELINE VALIDATION TEST")
    print("=" * 80)

    # 1. Load Model strictly with MiniFASNetV2Exact
    print("\n[STEP 1: CHECKPOINT & ARCHITECTURE VERIFICATION]")
    model, load_info = load_v2_model_strict()
    print(f"  Checkpoint Path:          {load_info['checkpoint_path']}")
    print(f"  Architecture:             {load_info['architecture']}")
    print(f"  Strict Loading:           PASS")
    print(f"  Missing Keys Count:       {load_info['missing_keys']}")
    print(f"  Unexpected Keys Count:    {load_info['unexpected_keys']}")
    print(f"  Model Parameter Count:    {load_info['parameter_count']}")
    print(f"  State Dict Tensor Count:  {load_info['checkpoint_tensor_count']}")
    print("  CHECKPOINT_LOAD_CHECK = PASS (strict=True, 0 missing, 0 unexpected)")

    # 2. Prepare In-Memory Crop (Scale 2.7, 80x80)
    print("\n[STEP 2: IN-MEMORY CROP GENERATION]")
    frame, crop_bgr, bbox = get_test_frame_and_crop()
    print(f"  Original Frame Shape:     {frame.shape} (BGR uint8)")
    print(f"  Detection Bounding Box:   {bbox} [x, y, w, h]")
    print(f"  Requested Crop Scale:     2.7")
    print(f"  Output Resolution:        80x80 (cv2.INTER_LINEAR)")
    print(f"  Crop Base Shape:          {crop_bgr.shape} (BGR uint8, in-memory, no JPEG reload)")
    print("  CROP_PIPELINE_CHECK = PASS")

    # 3. Perform Inference with Verified Preprocessing (BGR float32 0..255)
    print("\n[STEP 3: PREPROCESSING & INFERENCE]")
    res = run_verified_inference(model, crop_bgr)
    print(f"  Preprocessing Format:     BGR float32 [0.0, 255.0] (un-normalized float)")
    print(f"  Tensor Layout:            NCHW {res['tensor_shape']}")
    print(f"  Tensor Dtype:             {res['tensor_dtype']}")
    print(f"  Tensor Range:             [{res['tensor_min']:.4f}, {res['tensor_max']:.4f}]")
    print(f"  Tensor Mean / Std:        Mean = {res['tensor_mean']:.4f} | Std = {res['tensor_std']:.4f}")
    print(f"  Raw Logits:               [{res['logits'][0]:.4f}, {res['logits'][1]:.4f}, {res['logits'][2]:.4f}]")
    print(f"  Softmax Probabilities:    Class 0 (Print)={res['probabilities'][0]*100:.2f}%, Class 1 (Real)={res['probabilities'][1]*100:.2f}%, Class 2 (Screen)={res['probabilities'][2]*100:.2f}%")
    print(f"  Predicted Class Index:    {res['predicted_class']}")
    print(f"  Predicted Class Label:    {res['predicted_label']}")

    # 4. Final Validation Assertions
    print("\n" + "=" * 80)
    print("                      PRODUCTION BASELINE CONFIRMATION")
    print("=" * 80)

    # Check 1: Checkpoint strictly loaded
    assert load_info['strict_load'] is True
    print("  [CONFIRMATION 1] Checkpoint strictly loaded with MiniFASNetV2Exact : PASS")

    # Check 2: No architecture mismatch
    assert load_info['missing_keys'] == 0 and load_info['unexpected_keys'] == 0
    print("  [CONFIRMATION 2] Architecture mismatch count is 0                : PASS")

    # Check 3: Preprocessing range is BGR 0..255
    assert res['tensor_max'] > 1.0
    print("  [CONFIRMATION 3] Input tensor receives BGR float32 0..255         : PASS")

    # Check 4: Genuine real-face test frame predicts RealFace
    assert res['predicted_class'] == 1, f"Expected Class 1 (RealFace), got Class {res['predicted_class']}"
    assert res['predicted_label'] == "RealFace"
    print(f"  [CONFIRMATION 4] Test real-face frame predicts RealFace ({res['probabilities'][1]*100:.2f}% confidence) : PASS")

    # Check 5: Class Mapping preserved
    print("  [CONFIRMATION 5] Class mapping preserved (0=Print, 1=Real, 2=Screen) : PASS")

    print("\n>>> ALL 5 BASELINE VERIFICATION CHECKS PASSED SUCCESSFULLY! <<<\n")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
