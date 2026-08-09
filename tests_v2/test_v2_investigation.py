# -*- coding: utf-8 -*-
"""
MiniFASNet Checkpoint & Architecture Inspection Script
-------------------------------------------------------
Inspects all state_dict keys of 2.7_80x80_MiniFASNetV2.pth and 4_0_0_80x80_MiniFASNetV1SE.pth
and finds the exact PyTorch model architecture configuration that matches with strict=True.
"""

import os
import sys
import torch
import torch.nn as nn
from typing import List, Tuple, Dict, Any

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.model_lib.minifasnet_models import MiniFASNet, MiniFASNetSE, keep_dict


def inspect_checkpoint(checkpoint_rel_path: str):
    checkpoint_abs_path = os.path.join(PROJECT_ROOT, checkpoint_rel_path)
    if not os.path.exists(checkpoint_abs_path):
        print(f"[ERROR] File not found: {checkpoint_abs_path}")
        return

    print("=" * 80)
    print(f"CHECKPOINT INSPECTION: {checkpoint_rel_path}")
    print("=" * 80)

    state_dict = torch.load(checkpoint_abs_path, map_location="cpu")
    cleaned_state = {k.replace("module.", ""): v for k, v in state_dict.items()}

    print(f"Total Tensors in Checkpoint: {len(cleaned_state)}")
    print("\n--- First 15 Keys ---")
    for k in list(cleaned_state.keys())[:15]:
        print(f"  {k:<45} shape: {list(cleaned_state[k].shape)}")

    print("\n--- Last 15 Keys ---")
    for k in list(cleaned_state.keys())[-15:]:
        print(f"  {k:<45} shape: {list(cleaned_state[k].shape)}")

    # Test candidate model configurations
    print("\n" + "=" * 80)
    print("TESTING CANDIDATE MODEL ARCHITECTURES FOR STRICT MATCHING")
    print("=" * 80)

    candidates = [
        ("MiniFASNet(1.8M_, bias=True)",  lambda: MiniFASNet(keep_dict['1.8M_'], num_classes=3, conv6_kernel=(5,5))),
        ("MiniFASNet(1.8M, bias=True)",   lambda: MiniFASNet(keep_dict['1.8M'], num_classes=3, conv6_kernel=(5,5))),
        ("MiniFASNetSE(1.8M_, bias=True)",lambda: MiniFASNetSE(keep_dict['1.8M_'], num_classes=3, conv6_kernel=(5,5))),
        ("MiniFASNetSE(1.8M, bias=True)", lambda: MiniFASNetSE(keep_dict['1.8M'], num_classes=3, conv6_kernel=(5,5))),
    ]

    for name, c_func in candidates:
        model = c_func()
        model.eval()
        model_state = model.state_dict()

        missing = []
        unexpected = []
        try:
            res = model.load_state_dict(cleaned_state, strict=True)
            missing = res.missing_keys
            unexpected = res.unexpected_keys
            success = True
        except RuntimeError as e:
            success = False
            for line in str(e).split("\n"):
                if "Missing key(s)" in line:
                    missing.append(line.strip())
                elif "Unexpected key(s)" in line:
                    unexpected.append(line.strip())

        print(f"\n---> Architecture: {name}")
        print(f"     Strict Load Result: {'PASS [0 Mismatches]' if success else 'FAIL'}")
        print(f"     Missing Keys Count:    {len(missing)}")
        if missing:
            print(f"     Sample Missing:       {missing[:3]}")
        print(f"     Unexpected Keys Count: {len(unexpected)}")
        if unexpected:
            print(f"     Sample Unexpected:    {unexpected[:3]}")


def main():
    inspect_checkpoint("resources/anti_spoof_models/2.7_80x80_MiniFASNetV2.pth")
    print("\n")
    inspect_checkpoint("resources/anti_spoof_models/4_0_0_80x80_MiniFASNetV1SE.pth")


if __name__ == "__main__":
    main()
