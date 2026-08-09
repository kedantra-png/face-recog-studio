# -*- coding: utf-8 -*-
import os
import sys
import torch

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
chk_v2 = os.path.join(PROJECT_ROOT, "resources", "anti_spoof_models", "2.7_80x80_MiniFASNetV2.pth")
chk_v1se = os.path.join(PROJECT_ROOT, "resources", "anti_spoof_models", "4_0_0_80x80_MiniFASNetV1SE.pth")

v2_sd = torch.load(chk_v2, map_location="cpu")
cleaned_v2 = {k.replace("module.", ""): list(v.shape) for k, v in v2_sd.items()}

v1_sd = torch.load(chk_v1se, map_location="cpu")
cleaned_v1 = {k.replace("module.", ""): list(v.shape) for k, v in v1_sd.items()}

with open(os.path.join(PROJECT_ROOT, "tests_v2", "keys_summary.txt"), "w", encoding="utf-8") as f:
    f.write("=== 2.7_80x80_MiniFASNetV2.pth KEYS (Total: " + str(len(cleaned_v2)) + ") ===\n")
    for k, s in cleaned_v2.items():
        f.write(f"  {k:<55} {s}\n")
    
    f.write("\n=== 4_0_0_80x80_MiniFASNetV1SE.pth KEYS (Total: " + str(len(cleaned_v1)) + ") ===\n")
    for k, s in cleaned_v1.items():
        f.write(f"  {k:<55} {s}\n")

print("Keys dumped to tests_v2/keys_summary.txt successfully!")
