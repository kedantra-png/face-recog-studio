# Silent-Face-Anti-Spoofing Testing & Web Demo Guide

This package provides a standalone testing utility script and a feature-rich Web Application for evaluating the **Silent-Face-Anti-Spoofing** deep learning model.

---

## 1. Test Script (`test_model.py`)

The `test_model.py` CLI script allows you to evaluate liveness and presentation attack detection on single images, directories, or sample sets.

### Quick Run on Sample Images
To evaluate the default sample dataset (`images/sample/`):
```bash
python test_model.py
```

### Run on a Specific Image
```bash
python test_model.py --image path/to/face_photo.jpg
```

### Batch Run on a Directory
```bash
python test_model.py --dir path/to/image_folder --output_dir ./images/sample/results
```

### CLI Arguments
- `--image`: Path to a single image file to analyze.
- `--dir`: Folder path to run batch liveness evaluation.
- `--model_dir`: Directory containing `.pth` model weights (default: `./resources/anti_spoof_models`).
- `--output_dir`: Path where annotated bounding box visualizations are saved (default: `./images/sample/results`).
- `--device_id`: GPU device ID (default: `0`, uses CPU automatically if CUDA unavailable).

---

## 2. Interactive Web Application (`demo_app.py`)

The `demo_app.py` web server provides an interactive real-time dashboard accessible via your web browser.

### Starting the Server
Run the Flask server:
```bash
python demo_app.py
```
Open your browser and navigate to:
👉 **`http://127.0.0.1:5000`**

### Web Demo Features
1. **📁 Upload Photo Mode**:
   - Drag & drop or browse photos (JPG, PNG, WEBP, BMP).
   - Instant visual response with real vs fake face verdict, score, bounding box, and input scale patches.

2. **📹 Live Webcam Mode**:
   - WebRTC live camera stream with liveness detection.
   - **Continuous Auto Scan**: Toggle real-time continuous anti-spoofing scanning.
   - **Manual Snapshot**: Capture frame and evaluate on-demand.

3. **🖼️ Sample Gallery**:
   - 1-click test with sample photos included in the repository.

4. **📊 Diagnostic Telemetry**:
   - Dual ensemble score breakdown (MiniFASNetV2 Scale 2.7 & MiniFASNetV1SE Scale 4.0).
   - Inference latency in milliseconds.
   - Scale input patch inspector displaying exact neural net inputs.

---

## Technical Features & Improvements
- **Automatic Aspect Ratio Padding**: Standardizes input image dimensions to 3:4 aspect ratio required by MiniFASNet without stretching or throwing format errors.
- **RetinaFace Integration**: Automatic facial detection bounding box extraction using Caffe framework.
- **RESTful API Endpoint**: Integration-ready `/api/predict` endpoint accepting multipart file uploads or JSON Base64 image payloads.
