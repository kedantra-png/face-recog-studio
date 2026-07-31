# Silent Face Anti-Spoofing (Liveness Detection)

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/)
[![PyTorch](https://img.shields.io/badge/PyTorch-2.0+-orange.svg)](https://pytorch.org/)
[![OpenCV](https://img.shields.io/badge/OpenCV-4.0+-green.svg)](https://opencv.org/)

A lightweight, real-time **Facial Liveness Detection System** (Presentation Attack Detection) designed by Minivision AI. It accurately distinguishes between live human faces and spoofing attacks (digital screen replays, paper photo printouts, 3D masks) without requiring active user gestures.

---

## 🚨 MANDATORY FILES: What MUST Be Copied to Another Project

> [!IMPORTANT]
> **Code files can be generated or written, but pre-trained neural network binary weights CANNOT be generated.**
> You MUST copy the pre-trained weight files in the `resources/` folder to your target project directory.

### 1. 📦 Non-Generateable Pre-Trained Binary Weight Files (MANDATORY)

These binary model files contain millions of trained neural network parameters and **MUST be physically copied** to any new project:

| File Path | Description | Type |
| :--- | :--- | :--- |
| 🔴 **`resources/anti_spoof_models/2.7_80x80_MiniFASNetV2.pth`** | MiniFASNetV2 Model Weights (Scale 2.7 patch) | PyTorch Binary Weights |
| 🔴 **`resources/anti_spoof_models/4_0_0_80x80_MiniFASNetV1SE.pth`** | MiniFASNetV1SE Model Weights (Scale 4.0 patch) | PyTorch Binary Weights |
| 🔴 **`resources/detection_model/Widerface-RetinaFace.caffemodel`** | RetinaFace Detector Binary Weights | Caffe Binary Weights |
| 🔴 **`resources/detection_model/deploy.prototxt`** | RetinaFace Caffe Network Layer Configuration | Prototxt Config |

---

### 2. 📁 Full Directory Structure to Copy into Target Project

Copy the `resources/` folder (mandatory weights) and `src/` folder (Python logic) into your target project:

```
your_new_project/
│
├── 🔴 resources/                         # 👈 MANDATORY (CANNOT BE GENERATED)
│   ├── anti_spoof_models/
│   │   ├── 2.7_80x80_MiniFASNetV2.pth    # PyTorch Pre-trained Model Weight
│   │   └── 4_0_0_80x80_MiniFASNetV1SE.pth# PyTorch Pre-trained Model Weight
│   └── detection_model/
│       ├── Widerface-RetinaFace.caffemodel # Caffe Face Detector Weight
│       └── deploy.prototxt               # Caffe Detector Prototxt Config
│
├── 🐍 src/                               # 👈 PYTHON LOGIC DIRECTORY
│   ├── __init__.py
│   ├── anti_spoof_predict.py             # Main predictor class & RetinaFace wrapper
│   ├── generate_patches.py               # Scale 2.7 and Scale 4.0 face cropper
│   ├── utility.py                        # Model name parser & utility functions
│   ├── default_config.py
│   ├── model_lib/
│   │   ├── MiniFASNet.py                 # PyTorch neural network definitions
│   │   └── MultiFTNet.py
│   └── data_io/
│       ├── functional.py
│       └── transform.py
│
└── 🛠️ test_model.py                      # 👈 OPTIONAL: CLI script & aspect-ratio padding helper
```

---

## ⚙️ Installation & Requirements

Ensure your target environment has the following Python packages installed:

```bash
pip install torch torchvision opencv-python numpy flask
```

---

## 🚀 Quick Usage & Commands

### 1. Run Command-Line Test Utility
Evaluate anti-spoofing on sample images or your own custom images/directories:

```bash
# Run batch test on sample dataset
python test_model.py

# Test a single custom image
python test_model.py --image path/to/face.jpg

# Test a directory of images and save annotated results
python test_model.py --dir path/to/folder --output_dir ./results
```

### 2. Launch Interactive Web App Studio
Start the modern web demonstration app:

```bash
python demo_app.py
```
Open your web browser and navigate to:
👉 **`http://127.0.0.1:5000`**

Features included in the Web App:
- 📹 **Real-Time Webcam Feed**: Live camera anti-spoofing detection with continuous auto-scan.
- 📁 **Image Upload**: Drag-and-drop file analyzer.
- 🖼️ **Sample Gallery**: 1-click test with built-in preset photos.
- 📊 **Diagnostic Telemetry**: Multi-scale model ensemble score breakdowns, face crop patch inspector, and latency metrics.

---

## 🧩 How to Integrate into Your Own Code

Here is a ready-to-use Python helper function you can drop into any backend (FastAPI, Flask, OpenCV):

```python
import os
import cv2
import numpy as np
from src.anti_spoof_predict import AntiSpoofPredict
from src.generate_patches import CropImage
from src.utility import parse_model_name
from test_model import pad_to_aspect_ratio_3_4

# Initialize predictor & cropper (reuse instance across requests)
MODEL_DIR = "./resources/anti_spoof_models"
model_predictor = AntiSpoofPredict(device_id=0)  # 0 for GPU, uses CPU if CUDA unavailable
cropper = CropImage()

def check_face_liveness(bgr_image):
    """
    Evaluates liveness for a given OpenCV BGR image.
    Returns: dict with is_real (bool), score (float 0-100), and label.
    """
    # Pad to 3:4 aspect ratio required by MiniFASNet
    padded_img, _ = pad_to_aspect_ratio_3_4(bgr_image)
    
    # Detect face bounding box
    bbox = model_predictor.get_bbox(padded_img)
    if bbox == [0, 0, 1, 1] or bbox[2] <= 0 or bbox[3] <= 0:
        return {"success": False, "error": "No face detected"}

    prediction = np.zeros((1, 3))
    model_files = [f for f in os.listdir(MODEL_DIR) if f.endswith('.pth')]

    for model_name in model_files:
        h_input, w_input, model_type, scale = parse_model_name(model_name)
        param = {
            "org_img": padded_img,
            "bbox": bbox,
            "scale": scale,
            "out_w": w_input,
            "out_h": h_input,
            "crop": True if scale else False,
        }
        cropped_img = cropper.crop(**param)
        model_path = os.path.join(MODEL_DIR, model_name)
        prediction += model_predictor.predict(cropped_img, model_path)

    # Average ensemble prediction across loaded models
    final_probs = prediction[0] / len(model_files)
    label = int(np.argmax(final_probs))
    real_score = float(final_probs[1]) * 100.0
    is_real = (label == 1)

    return {
        "success": True,
        "is_real": is_real,
        "score_percent": round(real_score, 2),
        "label": "REAL FACE" if is_real else "SPOOF ATTACK",
        "bbox": bbox
    }

# Example usage:
if __name__ == "__main__":
    img = cv2.imread("images/sample/image_T1.jpg")
    result = check_face_liveness(img)
    print("Result:", result)
```

---

## 🤖 Prompt for AI Agents to Integrate into Other Systems

If you want an AI assistant (or developer) to integrate this anti-spoofing module into another codebase, copy and paste the prompt below:

```text
PROMPT TO INTEGRATE SILENT-FACE-ANTI-SPOOFING INTO ANOTHER PROJECT:
------------------------------------------------------------------
"Please integrate the Silent-Face-Anti-Spoofing liveness detection module into our existing face processing pipeline.

Requirements:
1. Ensure the mandatory binary weight files from `resources/` (`2.7_80x80_MiniFASNetV2.pth`, `4_0_0_80x80_MiniFASNetV1SE.pth`, `Widerface-RetinaFace.caffemodel`, `deploy.prototxt`) and the Python logic files in `src/` are present in our project structure.
2. Ensure OpenCV (opencv-python), PyTorch (torch, torchvision), and NumPy are available in requirements.txt.
3. Add a liveness verification step BEFORE our face recognition / verification function.
4. The liveness step should take an input OpenCV BGR frame, pad it to 3:4 aspect ratio using `pad_to_aspect_ratio_3_4`, extract face bounding box with RetinaFace detector (`AntiSpoofPredict`), crop patches for scales 2.7 & 4.0 using `CropImage`, and evaluate prediction using `MiniFASNet`.
5. If the returned liveness confidence (is_real) is False or below 70%, reject the authentication attempt immediately with HTTP 403 / Liveness Failed response.
6. If liveness succeeds, proceed to face recognition embedding extraction."
```

---

## 📖 Architecture & Codebase Documentation

| Module / File | Purpose | Category |
| :--- | :--- | :--- |
| **`resources/anti_spoof_models/`** | Pre-trained MiniFASNet weights (`2.7_80x80_MiniFASNetV2.pth` & `4_0_0_80x80_MiniFASNetV1SE.pth`). | 🔴 Mandatory Binary Weights |
| **`resources/detection_model/`** | Caffe deployment files for RetinaFace (`deploy.prototxt` & `Widerface-RetinaFace.caffemodel`). | 🔴 Mandatory Binary Weights |
| **`src/anti_spoof_predict.py`** | Contains `Detection` (RetinaFace Caffe wrapper) and `AntiSpoofPredict` (PyTorch weight loader & classifier). | 🐍 Python Logic |
| **`src/generate_patches.py`** | Implements `CropImage._get_new_box` to crop multi-scale facial bounding boxes (Scale 2.7 for zoomed face, Scale 4.0 for background context). | 🐍 Python Logic |
| **`src/utility.py`** | Parses model filename conventions (`parse_model_name`) to auto-configure input dimensions and network architecture. | 🐍 Python Logic |
| **`src/model_lib/MiniFASNet.py`** | PyTorch definitions of lightweight mobilenet-style architectures (`MiniFASNetV1`, `MiniFASNetV2`, `MiniFASNetV1SE`, `MiniFASNetV2SE`). | 🐍 Python Logic |
| **`test_model.py`** | CLI testing script with aspect-ratio padding helper. | 🐍 Python Utility |
| **`demo_app.py`** | Flask Web Server providing web UI dashboard and REST API endpoints (`/api/predict`, `/api/samples`). | 🐍 Python Web Server |
