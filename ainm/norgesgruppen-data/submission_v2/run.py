"""
Submission run.py for the NorgesGruppen grocery detection+classification task.

python run.py --input /data/images/ --output /output/predictions.json
"""

import argparse
import json
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from ultralytics import YOLO

# Try importing ensemble_boxes (available in sandbox: ensemble-boxes 1.0.9)
try:
    from ensemble_boxes import weighted_boxes_fusion
    HAS_WBF = True
except ImportError:
    HAS_WBF = False


def load_models(weights_dir: Path):
    """Load all available models from weights directory."""
    models = []

    # Primary model
    for ext in (".pt", ".onnx"):
        path = weights_dir / f"primary{ext}"
        if path.exists():
            models.append({
                "path": path,
                "imgsz": 1600,
                "weight": 2.0,
                "name": "primary",
                "format": ext,
            })
            break

    # Ensemble model
    for ext in (".pt", ".onnx"):
        path = weights_dir / f"ensemble{ext}"
        if path.exists():
            models.append({
                "path": path,
                "imgsz": 1920,
                "weight": 1.0,
                "name": "ensemble",
                "format": ext,
            })
            break

    # Fallback: any model file
    if not models:
        for pattern in ("*.pt", "*.onnx"):
            for p in sorted(weights_dir.glob(pattern)):
                models.append({
                    "path": p,
                    "imgsz": 1600,
                    "weight": 1.0,
                    "name": p.stem,
                    "format": p.suffix,
                })
                break
            if models:
                break

    return models


def try_load_model(path):
    """Try to load a YOLO model, return None on failure."""
    try:
        model = YOLO(str(path))
        # Only move .pt models to GPU — ONNX handles device via execution providers
        if path.suffix == ".pt" and torch.cuda.is_available():
            model.to("cuda")
        return model
    except Exception as e:
        print(f"WARNING: Failed to load {path}: {e}")
        # If .pt fails, try .onnx fallback
        onnx_path = path.with_suffix(".onnx")
        if path.suffix == ".pt" and onnx_path.exists():
            print(f"Trying ONNX fallback: {onnx_path}")
            try:
                model = YOLO(str(onnx_path))
                return model
            except Exception as e2:
                print(f"WARNING: ONNX fallback also failed: {e2}")
        return None


def predict_single_model(model, img_path, imgsz, use_tta=False):
    """Get predictions from a single model."""
    device = "cuda" if torch.cuda.is_available() else "cpu"

    try:
        results = model(
            str(img_path),
            device=device,
            imgsz=imgsz,
            conf=0.01,
            max_det=300,
            verbose=False,
            augment=use_tta,
        )
    except Exception:
        # TTA might fail on ONNX models — retry without it
        if use_tta:
            results = model(
                str(img_path),
                device=device,
                imgsz=imgsz,
                conf=0.01,
                max_det=300,
                verbose=False,
                augment=False,
            )
        else:
            raise

    boxes, scores, labels = [], [], []
    for r in results:
        if r.boxes is None or len(r.boxes) == 0:
            continue
        h, w = r.orig_shape
        for i in range(len(r.boxes)):
            x1, y1, x2, y2 = r.boxes.xyxy[i].tolist()
            boxes.append([
                max(0, min(1, x1 / w)),
                max(0, min(1, y1 / h)),
                max(0, min(1, x2 / w)),
                max(0, min(1, y2 / h)),
            ])
            scores.append(float(r.boxes.conf[i].item()))
            labels.append(int(r.boxes.cls[i].item()))

    return boxes, scores, labels


def predict_ensemble(loaded_models, img_path):
    """Predict with WBF ensemble of multiple models."""
    all_boxes, all_scores, all_labels = [], [], []
    weights = []

    for minfo, model in loaded_models:
        boxes, scores, labels = predict_single_model(
            model, img_path, minfo["imgsz"], use_tta=(minfo["format"] == ".pt")
        )
        all_boxes.append(boxes)
        all_scores.append(scores)
        all_labels.append(labels)
        weights.append(minfo["weight"])

    if not any(len(b) > 0 for b in all_boxes):
        return [], [], []

    for i in range(len(all_boxes)):
        if len(all_boxes[i]) == 0:
            all_boxes[i] = [[0, 0, 0, 0]]
            all_scores[i] = [0]
            all_labels[i] = [0]

    fused_boxes, fused_scores, fused_labels = weighted_boxes_fusion(
        all_boxes,
        all_scores,
        all_labels,
        weights=weights,
        iou_thr=0.55,
        skip_box_thr=0.01,
    )

    return fused_boxes.tolist(), fused_scores.tolist(), fused_labels.astype(int).tolist()


def predict_single(loaded_models, img_path):
    """Predict with single model."""
    minfo, model = loaded_models[0]
    use_tta = minfo["format"] == ".pt"
    boxes, scores, labels = predict_single_model(
        model, img_path, minfo["imgsz"], use_tta=use_tta
    )
    return boxes, scores, labels


def parse_image_id(img_path):
    """Extract image_id from filename."""
    stem = img_path.stem
    if "_" in stem:
        try:
            return int(stem.split("_")[-1])
        except ValueError:
            pass
    try:
        return int(stem)
    except ValueError:
        pass
    return abs(hash(stem)) % (10**9)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    input_dir = Path(args.input)
    output_path = Path(args.output)
    weights_dir = Path(__file__).resolve().parent / "weights"

    # Load models
    model_configs = load_models(weights_dir)
    print(f"Found {len(model_configs)} model config(s): {[m['name'] for m in model_configs]}")

    loaded_models = []
    for minfo in model_configs:
        model = try_load_model(minfo["path"])
        if model is not None:
            loaded_models.append((minfo, model))
            print(f"  Loaded: {minfo['name']} ({minfo['format']})")

    if not loaded_models:
        print("ERROR: No models could be loaded!")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump([], f)
        return

    use_ensemble = len(loaded_models) > 1 and HAS_WBF
    print(f"Strategy: {'WBF ensemble' if use_ensemble else 'single model'}")

    conf_threshold = 0.15
    predictions = []

    image_files = sorted([
        p for p in input_dir.iterdir()
        if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff")
    ])
    print(f"Processing {len(image_files)} images...")

    for img_path in image_files:
        image_id = parse_image_id(img_path)

        try:
            if use_ensemble:
                boxes, scores, labels = predict_ensemble(loaded_models, img_path)
            else:
                boxes, scores, labels = predict_single(loaded_models, img_path)
        except Exception as e:
            print(f"WARNING: Error on {img_path.name}: {e}")
            continue

        if not boxes:
            continue

        with Image.open(img_path) as im:
            img_w, img_h = im.size

        for box, score, label in zip(boxes, scores, labels):
            if score < conf_threshold:
                continue

            x1 = box[0] * img_w
            y1 = box[1] * img_h
            x2 = box[2] * img_w
            y2 = box[3] * img_h

            predictions.append({
                "image_id": image_id,
                "category_id": int(label),
                "bbox": [round(x1, 1), round(y1, 1), round(x2 - x1, 1), round(y2 - y1, 1)],
                "score": round(float(score), 3),
            })

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(predictions, f)

    print(f"Wrote {len(predictions)} predictions to {output_path}")


if __name__ == "__main__":
    main()
