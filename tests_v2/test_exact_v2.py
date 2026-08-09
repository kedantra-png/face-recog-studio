# -*- coding: utf-8 -*-
"""
Standalone Exact Checkpoint Validation Test for MiniFASNetV2
------------------------------------------------------------
Tests exact checkpoint loading of resources/anti_spoof_models/2.7_80x80_MiniFASNetV2.pth
with strict=True (0 missing keys, 0 unexpected keys).
"""

import os
import sys
import torch
import torch.nn as nn
import torch.nn.functional as F
import cv2
import numpy as np
from typing import Tuple, List, Dict, Any

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.model_lib.minifasnet_models import (
    Conv_block, Linear_block, Depth_Wise, Multi_Depth_Wise, Flatten, keep_dict
)


class MiniFASNetV2Exact(nn.Module):
    """
    Exact PyTorch model architecture matching 'resources/anti_spoof_models/2.7_80x80_MiniFASNetV2.pth'.
    Features:
      - DepthWise backbone with keep_dict['1.8M_']
      - conv_6_sep (Conv_block: 128 -> 512, 1x1 conv + BN + PReLU)
      - conv_6_dw  (Linear_block: 512 -> 512, 5x5 depthwise conv + BN)
      - linear     (Linear: 512 -> 128, bias=False)
      - bn         (BatchNorm1d: 128)
      - prob       (Linear: 128 -> 3, bias=False)
    """
    def __init__(self, keep: list = keep_dict['1.8M_'], embedding_size: int = 128, conv6_kernel: Tuple[int, int] = (5, 5), drop_p: float = 0.2, num_classes: int = 3, img_channel: int = 3):
        super().__init__()
        self.embedding_size = embedding_size

        self.conv1 = Conv_block(img_channel, keep[0], kernel=(3, 3), stride=(2, 2), padding=(1, 1))
        self.conv2_dw = Conv_block(keep[0], keep[1], kernel=(3, 3), stride=(1, 1), padding=(1, 1), groups=keep[0])

        self.conv_23 = Depth_Wise((keep[1], keep[2]), (keep[2], keep[3]), (keep[3], keep[4]), kernel=(3, 3), stride=(2, 2), padding=(1, 1), groups=keep[3])
        self.conv_3 = Multi_Depth_Wise(4, keep[4:17], residual=True, kernel=(3, 3), stride=(1, 1), padding=(1, 1), groups=keep[6])
        self.conv_34 = Depth_Wise((keep[16], keep[17]), (keep[17], keep[18]), (keep[18], keep[19]), kernel=(3, 3), stride=(2, 2), padding=(1, 1), groups=keep[18])
        self.conv_4 = Multi_Depth_Wise(6, keep[19:38], residual=True, kernel=(3, 3), stride=(1, 1), padding=(1, 1), groups=keep[21])

        self.conv_45 = Depth_Wise((keep[37], keep[38]), (keep[38], keep[39]), (keep[39], keep[40]), kernel=(3, 3), stride=(2, 2), padding=(1, 1), groups=keep[39])
        self.conv_5 = Multi_Depth_Wise(2, keep[40:47], residual=True, kernel=(3, 3), stride=(1, 1), padding=(1, 1), groups=keep[42])
        self.conv_6_sep = Conv_block(keep[46], keep[47], kernel=(1, 1), stride=(1, 1), padding=(0, 0))
        self.conv_6_dw = Linear_block(keep[47], keep[47], kernel=conv6_kernel, stride=(1, 1), padding=(0, 0), groups=keep[47])
        self.conv_6_flatten = Flatten()

        self.linear = nn.Linear(keep[47], embedding_size, bias=False)
        self.bn = nn.BatchNorm1d(embedding_size)
        self.drop = nn.Dropout(p=drop_p)
        self.prob = nn.Linear(embedding_size, num_classes, bias=False)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.conv1(x)
        x = self.conv2_dw(x)
        x = self.conv_23(x)
        x = self.conv_3(x)
        x = self.conv_34(x)
        x = self.conv_4(x)
        x = self.conv_45(x)
        x = self.conv_5(x)
        x = self.conv_6_sep(x)
        x = self.conv_6_dw(x)
        x = self.conv_6_flatten(x)

        x = self.linear(x)
        x = self.bn(x)
        x = self.drop(x)
        x = self.prob(x)
        return x


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


def run_standalone_checkpoint_validation():
    checkpoint_rel_path = "resources/anti_spoof_models/2.7_80x80_MiniFASNetV2.pth"
    checkpoint_abs_path = os.path.join(PROJECT_ROOT, checkpoint_rel_path)

    if not os.path.exists(checkpoint_abs_path):
        raise FileNotFoundError(f"Checkpoint file not found: {checkpoint_abs_path}")

    state_dict = torch.load(checkpoint_abs_path, map_location="cpu")
    cleaned_state = {k.replace("module.", ""): v for k, v in state_dict.items()}

    model = MiniFASNetV2Exact(conv6_kernel=(5, 5), num_classes=3, img_channel=3)
    model.eval()

    # Perform strict load
    res = model.load_state_dict(cleaned_state, strict=True)
    missing_keys_count = len(res.missing_keys)
    unexpected_keys_count = len(res.unexpected_keys)

    assert missing_keys_count == 0, f"Missing keys ({missing_keys_count}): {res.missing_keys}"
    assert unexpected_keys_count == 0, f"Unexpected keys ({unexpected_keys_count}): {res.unexpected_keys}"

    param_count = sum(p.numel() for p in model.parameters())
    state_dict_tensor_count = len(cleaned_state)

    print("=" * 80)
    print("STANDALONE MINIFASNET V2 CHECKPOINT VALIDATION REPORT")
    print("=" * 80)
    print(f"checkpoint_path:          {checkpoint_rel_path}")
    print(f"missing_keys:             {missing_keys_count}")
    print(f"unexpected_keys:          {unexpected_keys_count}")
    print(f"strict_load:              PASS")
    print(f"parameter_count:          {param_count}")
    print(f"state_dict_tensor_count:  {state_dict_tensor_count}")
    print("=" * 80)

    # Preprocessing BGR float32 0..1 validation on test frame
    debug_dir = os.path.join(PROJECT_ROOT, "debug")
    frame_path = os.path.join(debug_dir, "step1_input_frame_0.jpg")

    if os.path.exists(frame_path):
        frame = cv2.imread(frame_path)
        bbox = [240, 277, 131, 173]
        crop_bgr = CropImage.crop(frame, bbox, scale=2.7, out_w=80, out_h=80)

        # Verified Preprocessing: BGR float32 0..1
        tensor = torch.from_numpy(crop_bgr.transpose((2, 0, 1))).unsqueeze(0).float() / 255.0

        with torch.no_grad():
            logits = model(tensor)
            prob = F.softmax(logits, dim=1)

        logits_np = logits.cpu().numpy()[0]
        prob_np = prob.cpu().numpy()[0]
        pred_class = int(np.argmax(prob_np))

        class_names = {0: "PrintSpoof", 1: "RealFace", 2: "ScreenSpoof"}
        pred_label = class_names[pred_class]

        print("\n" + "=" * 80)
        print("VERIFIED PREPROCESSING INFERENCE RESULT (BGR float32 0..1)")
        print("=" * 80)
        print(f"Tensor shape:         {list(tensor.shape)}")
        print(f"Tensor range:         [{tensor.min().item():.4f}, {tensor.max().item():.4f}]")
        print(f"Logits:               [{logits_np[0]:.4f}, {logits_np[1]:.4f}, {logits_np[2]:.4f}]")
        print(f"Softmax Probabilities: [{prob_np[0]:.4f}, {prob_np[1]:.4f}, {prob_np[2]:.4f}]")
        print(f"Predicted Class:      {pred_class} ({pred_label})")
        print("=" * 80 + "\n")


if __name__ == "__main__":
    run_standalone_checkpoint_validation()
