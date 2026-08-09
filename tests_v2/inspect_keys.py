# -*- coding: utf-8 -*-
"""
Checkpoint Inspection Utility
-----------------------------
Reads resources/anti_spoof_models/2.7_80x80_MiniFASNetV2.pth and resources/anti_spoof_models/4_0_0_80x80_MiniFASNetV1SE.pth
and outputs all state_dict keys and tensor shapes to text files for exact architecture matching.
"""

import os
import sys
import torch

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def dump_keys(checkpoint_rel_path: str, output_txt_path: str):
    checkpoint_abs_path = os.path.join(PROJECT_ROOT, checkpoint_rel_path)
    output_abs_path = os.path.join(PROJECT_ROOT, output_txt_path)

    if not os.path.exists(checkpoint_abs_path):
        print(f"[ERROR] Checkpoint not found: {checkpoint_abs_path}")
        return

    state_dict = torch.load(checkpoint_abs_path, map_location="cpu")
    cleaned_state = {k.replace("module.", ""): v for k, v in state_dict.items()}

    lines = []
    lines.append(f"Checkpoint: {checkpoint_rel_path}")
    lines.append(f"Total Tensors: {len(cleaned_state)}")
    lines.append("=" * 80)
    lines.append(f"{'Key Name':<60} {'Shape':<20}")
    lines.append("-" * 80)

    for k, v in cleaned_state.items():
        lines.append(f"{k:<60} {str(list(v.shape)):<20}")

    with open(output_abs_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"[DUMP COMPLETE] Saved {len(cleaned_state)} keys to {output_abs_path}")

if __name__ == "__main__":
    dump_keys("resources/anti_spoof_models/2.7_80x80_MiniFASNetV2.pth", "tests_v2/v2_keys.txt")
    dump_keys("resources/anti_spoof_models/4_0_0_80x80_MiniFASNetV1SE.pth", "tests_v2/v1se_keys.txt")
