import argparse
import json
from pathlib import Path

import torch
from ultralytics import YOLO


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    input_dir = Path(args.input)
    output_path = Path(args.output)

    weights_path = Path(__file__).resolve().parent / "weights" / "best.onnx"
    model = YOLO(str(weights_path), task="detect")

    device = "cuda" if torch.cuda.is_available() else "cpu"

    predictions = []

    for img_path in sorted(input_dir.iterdir()):
        if img_path.suffix.lower() not in (".jpg", ".jpeg", ".png"):
            continue

        image_id = int(img_path.stem.split("_")[-1])
        results = model(str(img_path), device=device, imgsz=1280, conf=0.25, max_det=300, verbose=False)

        for r in results:
            if r.boxes is None:
                continue
            for i in range(len(r.boxes)):
                x1, y1, x2, y2 = r.boxes.xyxy[i].tolist()
                predictions.append({
                    "image_id": image_id,
                    "category_id": int(r.boxes.cls[i].item()),
                    "bbox": [round(x1, 1), round(y1, 1), round(x2 - x1, 1), round(y2 - y1, 1)],
                    "score": round(float(r.boxes.conf[i].item()), 3),
                })

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(predictions, f)


if __name__ == "__main__":
    main()
