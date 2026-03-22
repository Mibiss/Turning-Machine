"""
Train YOLOv8x for grocery product classification (356 classes).
Designed for GCP A100 GPU. Incorporates research-backed optimizations.

Training strategy (research-backed):
  Phase 1: Frozen backbone warmup (learns classification head first)
  Phase 2: Full fine-tune on stratified split (monitors val metrics)
  Phase 3: Final model on ALL data (competition submission)
  Phase 4: (Optional) Second model for WBF ensemble

Key research findings applied:
  - Progressive unfreezing (freeze backbone -> unfreeze all)
  - cls loss weight 2.0 (4x default, critical for 356 classes)
  - Cosine LR annealing for smoother convergence
  - close_mosaic=20 for clean fine-tuning at end (+0.5-1.5% mAP)
  - Heavy augmentation: mixup + copy_paste for rare classes
  - AdamW optimizer (better than SGD for fine-tuning)

Usage on GCP VM:
  python train_classify.py --phase 1      # frozen backbone warmup (~10 min)
  python train_classify.py --phase 2      # full fine-tune stratified (~1 hr)
  python train_classify.py --phase 3      # final model, all data (~2-3 hrs)
  python train_classify.py --phase 4      # ensemble candidate (~2 hrs)
  python train_classify.py --phase 3 --resume  # resume interrupted training
"""

import argparse
from pathlib import Path
from ultralytics import YOLO


def _find_best_weights(data_dir: Path, *run_names):
    """Find the best available weights from previous phases."""
    for name in run_names:
        path = data_dir / "runs" / "classify_v2" / name / "weights" / "best.pt"
        if path.exists():
            return path
    return None


def train_phase_1(data_dir: Path):
    """Phase 1: Frozen backbone warmup.

    Research finding: freezing backbone and only training the detection head first
    prevents catastrophic forgetting of pretrained features while the classification
    head adapts to 356 classes. This is especially important with small datasets.
    """
    yaml_path = data_dir / "grocery_classify_stratified.yaml"

    print("=== Phase 1: Frozen backbone warmup (YOLOv8x) ===")
    model = YOLO("yolov8x.pt")

    results = model.train(
        data=str(yaml_path),
        epochs=50,
        patience=20,
        batch=-1,          # auto batch size — fills GPU memory optimally
        imgsz=1280,        # start at 1280, will increase in phase 2
        device=0,
        workers=8,
        project=str(data_dir / "runs" / "classify_v2"),
        name="phase1_frozen",
        exist_ok=True,
        pretrained=True,

        # Freeze backbone (first 10 layers)
        freeze=10,

        # Higher LR is fine when backbone is frozen
        optimizer="SGD",
        lr0=0.01,
        lrf=0.01,
        momentum=0.937,
        weight_decay=0.0005,
        warmup_epochs=3,

        # Classification loss boosted for 356 classes
        cls=2.0,
        box=7.5,
        dfl=1.5,

        # Standard augmentation for warmup
        mosaic=1.0,
        mixup=0.1,
        copy_paste=0.1,
        degrees=5.0,
        translate=0.1,
        scale=0.5,
        shear=2.0,
        flipud=0.0,
        fliplr=0.5,
        hsv_h=0.015,
        hsv_s=0.7,
        hsv_v=0.4,
        erasing=0.3,

        close_mosaic=10,
        amp=True,
        plots=True,
        save=True,
        verbose=True,
    )
    return results


def train_phase_2(data_dir: Path):
    """Phase 2: Full fine-tune on stratified split.

    Research findings applied:
    - Unfreeze all layers with lower LR (progressive unfreezing)
    - AdamW + cosine LR for smooth convergence
    - cls=2.0 to heavily prioritize classification
    - close_mosaic=20 for clean fine-tuning at end
    - Higher resolution (1600px) for distinguishing similar products
    """
    yaml_path = data_dir / "grocery_classify_stratified.yaml"

    weights = _find_best_weights(data_dir, "phase1_frozen")
    if weights:
        print(f"=== Phase 2: Full fine-tune from phase 1 weights: {weights} ===")
        model = YOLO(str(weights))
    else:
        print("=== Phase 2: Full fine-tune from pretrained yolov8x.pt ===")
        model = YOLO("yolov8x.pt")

    results = model.train(
        data=str(yaml_path),
        epochs=300,
        patience=50,
        batch=-1,
        imgsz=1600,       # bump resolution — A100 can handle it
        device=0,
        workers=8,
        project=str(data_dir / "runs" / "classify_v2"),
        name="phase2_finetune",
        exist_ok=True,
        pretrained=True,

        # Unfreeze everything
        freeze=0,

        # AdamW + cosine LR — best combo from research
        optimizer="AdamW",
        lr0=0.001,
        lrf=0.01,
        cos_lr=True,
        weight_decay=0.001,
        warmup_epochs=10,

        # Heavy classification focus
        cls=2.0,
        box=7.5,
        dfl=1.5,

        # Heavy augmentation for tiny dataset
        mosaic=1.0,
        mixup=0.2,
        copy_paste=0.15,
        degrees=10.0,
        translate=0.2,
        scale=0.5,
        shear=3.0,
        flipud=0.0,
        fliplr=0.5,
        hsv_h=0.02,
        hsv_s=0.7,
        hsv_v=0.4,
        erasing=0.3,

        # Key trick: disable mosaic for last 20 epochs for clean fine-tuning
        close_mosaic=20,
        amp=True,
        plots=True,
        save=True,
        save_period=50,
        verbose=True,
    )
    return results


def train_phase_3(data_dir: Path, resume: bool = False):
    """Phase 3: Final model on ALL data for competition submission.

    Uses all 248 images (no held-out val). Starts from phase 2 best weights.
    More epochs with generous patience — let early stopping decide.
    """
    yaml_path = data_dir / "grocery_classify_full.yaml"

    if resume:
        last_weights = data_dir / "runs" / "classify_v2" / "phase3_final" / "weights" / "last.pt"
        if last_weights.exists():
            print(f"=== Phase 3: Resuming from {last_weights} ===")
            model = YOLO(str(last_weights))
            results = model.train(resume=True)
            _export(data_dir, "phase3_final", 1600)
            return results
        else:
            print("No checkpoint found to resume, starting fresh")

    weights = _find_best_weights(data_dir, "phase2_finetune", "phase1_frozen")
    if weights:
        print(f"=== Phase 3: Final model from {weights} ===")
        model = YOLO(str(weights))
        lr = 0.0003
        warmup = 5
    else:
        print("=== Phase 3: Final model from pretrained yolov8x.pt ===")
        model = YOLO("yolov8x.pt")
        lr = 0.001
        warmup = 10

    results = model.train(
        data=str(yaml_path),
        epochs=500,
        patience=80,      # very generous — all data, no val, let it learn
        batch=-1,
        imgsz=1600,
        device=0,
        workers=8,
        project=str(data_dir / "runs" / "classify_v2"),
        name="phase3_final",
        exist_ok=True,
        pretrained=True,

        freeze=0,
        optimizer="AdamW",
        lr0=lr,
        lrf=0.001,
        cos_lr=True,
        weight_decay=0.001,
        warmup_epochs=warmup,

        cls=2.0,
        box=7.5,
        dfl=1.5,

        mosaic=1.0,
        mixup=0.2,
        copy_paste=0.15,
        degrees=10.0,
        translate=0.2,
        scale=0.5,
        shear=3.0,
        flipud=0.0,
        fliplr=0.5,
        hsv_h=0.02,
        hsv_s=0.7,
        hsv_v=0.4,
        erasing=0.3,

        close_mosaic=25,
        amp=True,
        plots=True,
        save=True,
        save_period=50,
        verbose=True,
    )

    _export(data_dir, "phase3_final", 1600)
    return results


def train_phase_4(data_dir: Path):
    """Phase 4: Second model for WBF ensemble.

    Different architecture (YOLOv8l) at different resolution (1920px).
    Diversity in the ensemble = better combined predictions.
    """
    yaml_path = data_dir / "grocery_classify_full.yaml"

    print("=== Phase 4: YOLOv8l at 1920px — ensemble candidate ===")
    model = YOLO("yolov8l.pt")

    results = model.train(
        data=str(yaml_path),
        epochs=400,
        patience=60,
        batch=-1,
        imgsz=1920,
        device=0,
        workers=8,
        project=str(data_dir / "runs" / "classify_v2"),
        name="phase4_ensemble",
        exist_ok=True,
        pretrained=True,

        freeze=0,
        optimizer="AdamW",
        lr0=0.001,
        lrf=0.001,
        cos_lr=True,
        weight_decay=0.001,
        warmup_epochs=10,

        cls=2.0,
        box=7.5,
        dfl=1.5,

        mosaic=1.0,
        mixup=0.2,
        copy_paste=0.15,
        degrees=10.0,
        translate=0.2,
        scale=0.5,
        shear=3.0,
        flipud=0.0,
        fliplr=0.5,
        hsv_h=0.02,
        hsv_s=0.7,
        hsv_v=0.4,
        erasing=0.3,

        close_mosaic=25,
        amp=True,
        plots=True,
        save=True,
        save_period=50,
        verbose=True,
    )

    _export(data_dir, "phase4_ensemble", 1920)
    return results


def _export(data_dir: Path, run_name: str, imgsz: int):
    """Export best weights to ONNX for submission."""
    best_weights = data_dir / "runs" / "classify_v2" / run_name / "weights" / "best.pt"
    if best_weights.exists():
        print(f"Exporting {run_name} best model to ONNX (imgsz={imgsz})...")
        export_model = YOLO(str(best_weights))
        export_model.export(format="onnx", imgsz=imgsz, simplify=True, dynamic=False)
        print("ONNX export complete!")
    else:
        print(f"WARNING: {best_weights} not found, skipping export")


def main():
    parser = argparse.ArgumentParser(description="Train YOLOv8 classifier for grocery products (A100)")
    parser.add_argument("--phase", choices=["1", "2", "3", "4"], required=True,
                        help="1=frozen warmup, 2=full finetune, 3=final all-data, 4=ensemble")
    parser.add_argument("--data-dir", type=str, default=".",
                        help="Path to norgesgruppen-data directory")
    parser.add_argument("--resume", action="store_true",
                        help="Resume interrupted training (phase 3 only)")
    args = parser.parse_args()

    data_dir = Path(args.data_dir).resolve()
    print(f"Data directory: {data_dir}")
    print(f"Phase: {args.phase}")

    if args.phase == "1":
        train_phase_1(data_dir)
    elif args.phase == "2":
        train_phase_2(data_dir)
    elif args.phase == "3":
        train_phase_3(data_dir, resume=args.resume)
    elif args.phase == "4":
        train_phase_4(data_dir)


if __name__ == "__main__":
    main()
