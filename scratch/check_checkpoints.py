import torch
import sys
import os

sys.path.insert(0, os.path.abspath("."))
from src.model_lib.minifasnet_models import MiniFASNetV1SE, MiniFASNetV2, keep_dict, MiniFASNet, MiniFASNetSE

pth1 = "resources/anti_spoof_models/4_0_0_80x80_MiniFASNetV1SE.pth"
pth2 = "resources/anti_spoof_models/2.7_80x80_MiniFASNetV2.pth"

state1 = torch.load(pth1, map_location='cpu')
state2 = torch.load(pth2, map_location='cpu')

print("--- Checkpoint 1 (4_0_0_80x80_MiniFASNetV1SE.pth) ---")
cleaned1 = {k.replace('module.', ''): v for k, v in state1.items()}
print("Keys count:", len(cleaned1))
for k, v in list(cleaned1.items())[:10]:
    print(f"  {k}: {v.shape}")

print("\n--- Checkpoint 2 (2.7_80x80_MiniFASNetV2.pth) ---")
cleaned2 = {k.replace('module.', ''): v for k, v in state2.items()}
print("Keys count:", len(cleaned2))
for k, v in list(cleaned2.items())[:10]:
    print(f"  {k}: {v.shape}")

print("\n--- Testing Model Instantiations ---")

# Try loading state1 into MiniFASNetV1SE
m1 = MiniFASNetV1SE()
try:
    m1.load_state_dict(cleaned1, strict=True)
    print("SUCCESS: MiniFASNetV1SE loaded cleaned1 strictly!")
except Exception as e:
    print("FAIL MiniFASNetV1SE + cleaned1:", e)

# Try loading state2 into MiniFASNetV2
m2 = MiniFASNetV2()
try:
    m2.load_state_dict(cleaned2, strict=True)
    print("SUCCESS: MiniFASNetV2 loaded cleaned2 strictly!")
except Exception as e:
    print("FAIL MiniFASNetV2 + cleaned2:", e)

# Try cross loading or testing other keep configs
print("\nChecking layer shapes in state1 vs state2:")
print("state1 conv_3.model.0.conv_dw.prelu.weight:", cleaned1.get('conv_3.model.0.conv_dw.prelu.weight', 'N/A').shape if 'conv_3.model.0.conv_dw.prelu.weight' in cleaned1 else 'N/A')
print("state2 conv_3.model.0.conv_dw.prelu.weight:", cleaned2.get('conv_3.model.0.conv_dw.prelu.weight', 'N/A').shape if 'conv_3.model.0.conv_dw.prelu.weight' in cleaned2 else 'N/A')

print("state1 conv_4.model.0.conv.conv.weight:", cleaned1.get('conv_4.model.0.conv.conv.weight', 'N/A').shape if 'conv_4.model.0.conv.conv.weight' in cleaned1 else 'N/A')
print("state2 conv_4.model.0.conv.conv.weight:", cleaned2.get('conv_4.model.0.conv.conv.weight', 'N/A').shape if 'conv_4.model.0.conv.conv.weight' in cleaned2 else 'N/A')
