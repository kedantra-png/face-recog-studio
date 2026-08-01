# -*- coding: utf-8 -*-
"""
Silent-Face-Anti-Spoofing Test Utility
--------------------------------------
Comprehensive CLI and Python script to test face anti-spoofing models on single images,
directories, or default sample images. Automatically handles aspect ratio padding.
"""

import os
import sys
import cv2
import time
import argparse
import warnings
import numpy as np

# Ensure repository root is in python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.anti_spoof_predict import AntiSpoofPredict
from src.generate_patches import CropImage
from src.utility import parse_model_name

warnings.filterwarnings('ignore')


def pad_to_aspect_ratio_3_4(image):
    """
    Pads an image to ensure a 3:4 aspect ratio (Width:Height = 3:4).
    The Android model was trained on 3:4 aspect ratio inputs.
    """
    h, w, _ = image.shape
    target_aspect = 3.0 / 4.0
    current_aspect = w / float(h)
    
    if abs(current_aspect - target_aspect) < 1e-2:
        return image, (0, 0)

    if current_aspect > target_aspect:
        # Image is wider than 3:4 -> pad top/bottom
        new_h = int(round(w / target_aspect))
        pad_total = new_h - h
        pad_top = pad_total // 2
        pad_bottom = pad_total - pad_top
        padded = cv2.copyMakeBorder(image, pad_top, pad_bottom, 0, 0, cv2.BORDER_CONSTANT, value=[0, 0, 0])
        return padded, (0, pad_top)
    else:
        # Image is taller than 3:4 -> pad left/right
        new_w = int(round(h * target_aspect))
        pad_total = new_w - w
        pad_left = pad_total // 2
        pad_right = pad_total - pad_left
        padded = cv2.copyMakeBorder(image, 0, 0, pad_left, pad_right, cv2.BORDER_CONSTANT, value=[0, 0, 0])
        return padded, (pad_left, 0)


def predict_anti_spoof(image_path, model_dir="./resources/anti_spoof_models", device_id=0, model_predictor=None):
    """
    Evaluates anti-spoofing on a given image file path or numpy image array.
    
    Returns:
        dict containing result details (is_real, score, label_str, bbox, per_model_scores, elapsed_time, annotated_img)
    """
    if isinstance(image_path, str):
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Image not found at path: {image_path}")
        image = cv2.imread(image_path)
        img_name = os.path.basename(image_path)
    else:
        image = image_path
        img_name = "input_frame"

    if image is None:
        raise ValueError(f"Could not decode image from: {image_path}")

    padded_image, (pad_x, pad_y) = pad_to_aspect_ratio_3_4(image)

    if model_predictor is None:
        model_predictor = AntiSpoofPredict(device_id)
        
    image_cropper = CropImage()
    image_bbox = model_predictor.get_bbox(padded_image)

    # Check if face was detected
    if image_bbox == [0, 0, 1, 1] or image_bbox[2] <= 0 or image_bbox[3] <= 0:
        return {
            "success": False,
            "error": "No face detected in the image.",
            "image_name": img_name
        }

    prediction = np.zeros((1, 3))
    per_model_scores = {}
    total_time = 0

    model_files = [f for f in os.listdir(model_dir) if f.endswith('.pth')]
    if not model_files:
        raise FileNotFoundError(f"No model files (.pth) found in model_dir: {model_dir}")

    for model_name in model_files:
        h_input, w_input, model_type, scale = parse_model_name(model_name)
        param = {
            "org_img": padded_image,
            "bbox": image_bbox,
            "scale": scale,
            "out_w": w_input,
            "out_h": h_input,
            "crop": True,
        }
        if scale is None:
            param["crop"] = False

        cropped_img = image_cropper.crop(**param)
        
        start = time.time()
        model_path = os.path.join(model_dir, model_name)
        model_pred = model_predictor.predict(cropped_img, model_path)
        cost = time.time() - start
        total_time += cost

        prediction += model_pred
        # Class 1 is Real Face, Class 0 & 2 are Spoof/Fake
        real_score = float(model_pred[0][1])
        per_model_scores[model_name] = {
            "real_score": real_score,
            "fake_score": float(1.0 - real_score),
            "latency_sec": cost
        }

    num_models = len(model_files)
    final_probs = prediction[0] / num_models
    label = int(np.argmax(final_probs))
    score = float(final_probs[label])
    is_real = (label == 1)

    result_label = "Real Face" if is_real else "Fake Face (Spoof)"
    color = (0, 215, 0) if is_real else (0, 0, 235)  # BGR

    # Draw bounding box and text on padded image
    annotated = padded_image.copy()
    x, y, w, h = image_bbox
    cv2.rectangle(annotated, (x, y), (x + w, y + h), color, 2)

    label_text = f"{result_label}: {score * 100:.1f}%"
    font_scale = max(0.5, min(1.0, annotated.shape[0] / 800.0))
    cv2.putText(annotated, label_text, (x, max(20, y - 10)),
                cv2.FONT_HERSHEY_SIMPLEX, font_scale, color, 2)

    return {
        "success": True,
        "is_real": is_real,
        "label": label,
        "label_str": result_label,
        "score": score,
        "real_probability": float(final_probs[1]),
        "fake_probability": float(final_probs[0] + final_probs[2]),
        "bbox": image_bbox,
        "per_model_scores": per_model_scores,
        "total_latency_sec": total_time,
        "annotated_image": annotated,
        "image_name": img_name
    }


def run_batch_test(image_dir, model_dir, device_id, output_dir=None):
    """
    Runs face anti-spoofing test on all images in a directory.
    """
    if not os.path.exists(image_dir):
        os.makedirs(image_dir, exist_ok=True)
        print(f"[-] Image directory '{image_dir}' created. Please place test images (.jpg/.png) inside.")
        return

    valid_exts = ('.jpg', '.jpeg', '.png', '.bmp', '.webp')
    image_files = [f for f in os.listdir(image_dir) if f.lower().endswith(valid_exts) and not f.endswith('_result.jpg')]
    
    if not image_files:
        print(f"[-] No valid images found in {image_dir}")
        return

    print("=" * 70)
    print(f" Silent-Face-Anti-Spoofing Batch Evaluation")
    print(f" Folder: {image_dir} | Total Images: {len(image_files)}")
    print("=" * 70)

    model_predictor = AntiSpoofPredict(device_id)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    summary_stats = {"real": 0, "fake": 0, "no_face": 0}

    for img_file in image_files:
        path = os.path.join(image_dir, img_file)
        try:
            res = predict_anti_spoof(path, model_dir=model_dir, device_id=device_id, model_predictor=model_predictor)
            if not res["success"]:
                print(f"[-] {img_file:<25} -> NO FACE DETECTED")
                summary_stats["no_face"] += 1
                continue

            status = "REAL" if res["is_real"] else "FAKE"
            if res["is_real"]:
                summary_stats["real"] += 1
            else:
                summary_stats["fake"] += 1

            print(f"[+] {img_file:<25} -> Verdict: {status:<4} | Score: {res['score']*100:5.1f}% | Time: {res['total_latency_sec']*1000:5.1f}ms")

            if output_dir:
                out_path = os.path.join(output_dir, f"result_{img_file}")
                cv2.imwrite(out_path, res["annotated_image"])

        except Exception as e:
            print(f"[!] Error processing {img_file}: {e}")

    print("-" * 70)
    print(f" Summary: Real Faces: {summary_stats['real']} | Fake/Spoof: {summary_stats['fake']} | No Face: {summary_stats['no_face']}")
    print("=" * 70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Silent-Face-Anti-Spoofing Test Utility")
    parser.add_argument("--image", type=str, default=None, help="Path to a single image file to evaluate")
    parser.add_argument("--dir", type=str, default=None, help="Directory of images to evaluate in batch mode")
    parser.add_argument("--model_dir", type=str, default="./resources/anti_spoof_models", help="Directory containing model weights")
    parser.add_argument("--device_id", type=int, default=0, help="GPU device ID (default: 0, uses CPU if CUDA unavailable)")
    parser.add_argument("--output_dir", type=str, default="./images/sample/results", help="Directory to save annotated result images")
    
    args = parser.parse_args()

    # Default to sample folder if no arguments provided
    if args.image is None and args.dir is None:
        sample_dir = "./images/sample"
        print(f"[*] No target specified. Running batch evaluation on sample directory: {sample_dir}")
        run_batch_test(sample_dir, args.model_dir, args.device_id, args.output_dir)
    elif args.image:
        print(f"[*] Evaluating single image: {args.image}")
        res = predict_anti_spoof(args.image, model_dir=args.model_dir, device_id=args.device_id)
        if res["success"]:
            print("=" * 50)
            print(f" File:           {res['image_name']}")
            print(f" Verdict:        {res['label_str']}")
            print(f" Confidence:     {res['score']*100:.2f}%")
            print(f" Real Prob:      {res['real_probability']*100:.2f}%")
            print(f" Fake Prob:      {res['fake_probability']*100:.2f}%")
            print(f" Bounding Box:   {res['bbox']}")
            print(f" Total Time:     {res['total_latency_sec']*1000:.1f} ms")
            print(" Per Model Scores:")
            for m_name, m_info in res["per_model_scores"].items():
                print(f"   - {m_name:<30}: Real {m_info['real_score']*100:.1f}% | Fake {m_info['fake_score']*100:.1f}%")
            print("=" * 50)

            os.makedirs(args.output_dir, exist_ok=True)
            out_file = os.path.join(args.output_dir, f"result_{os.path.basename(args.image)}")
            cv2.imwrite(out_file, res["annotated_image"])
            print(f"[+] Saved annotated visualization to: {out_file}")
        else:
            print(f"[-] Evaluation failed: {res['error']}")
    elif args.dir:
        run_batch_test(args.dir, args.model_dir, args.device_id, args.output_dir)
