"""
Convert COCO annotations to YOLO format.
Creates two dataset variants:
  - grocery_detect:   all boxes → class 0 (detection only)
  - grocery_classify: boxes keep original category_id (0-355)

Images are symlinked to save disk space (~860MB).
Train/val split: 85/15, seed=42.
"""

import json
import random
from pathlib import Path

# Paths
PROJECT_ROOT = Path(__file__).resolve().parent
COCO_DIR = PROJECT_ROOT / "data" / "coco_dataset" / "train"
ANNOTATIONS_FILE = COCO_DIR / "annotations.json"
IMAGES_DIR = COCO_DIR / "images"
DATASETS_DIR = PROJECT_ROOT / "datasets"

SPLIT_RATIO = 0.85
SEED = 42


def load_annotations():
    with open(ANNOTATIONS_FILE) as f:
        return json.load(f)


def split_images(images, ratio, seed):
    ids = [img["id"] for img in images]
    random.seed(seed)
    random.shuffle(ids)
    split_idx = int(len(ids) * ratio)
    train_ids = set(ids[:split_idx])
    val_ids = set(ids[split_idx:])
    return train_ids, val_ids


def coco_to_yolo_bbox(bbox, img_w, img_h):
    """Convert COCO [x, y, w, h] (pixels) → YOLO [cx, cy, w, h] (normalized)."""
    x, y, w, h = bbox
    cx = (x + w / 2) / img_w
    cy = (y + h / 2) / img_h
    nw = w / img_w
    nh = h / img_h
    # Clamp to [0, 1]
    cx = max(0.0, min(1.0, cx))
    cy = max(0.0, min(1.0, cy))
    nw = max(0.0, min(1.0, nw))
    nh = max(0.0, min(1.0, nh))
    return cx, cy, nw, nh


def create_dataset(variant_name, annotations_by_image, image_info, train_ids, val_ids, remap_class=None):
    """
    Create a YOLO dataset directory with symlinked images and label .txt files.
    remap_class: if int, all annotations get this class_id. If None, keep original.
    """
    base = DATASETS_DIR / variant_name

    for split_name, split_ids in [("train", train_ids), ("val", val_ids)]:
        img_dir = base / split_name / "images"
        lbl_dir = base / split_name / "labels"
        img_dir.mkdir(parents=True, exist_ok=True)
        lbl_dir.mkdir(parents=True, exist_ok=True)

        for img_id in split_ids:
            info = image_info[img_id]
            fname = info["file_name"]
            img_w = info["width"]
            img_h = info["height"]

            # Symlink image
            src = IMAGES_DIR / fname
            dst = img_dir / fname
            if not dst.exists():
                dst.symlink_to(src.resolve())

            # Write labels
            label_name = Path(fname).stem + ".txt"
            label_path = lbl_dir / label_name

            anns = annotations_by_image.get(img_id, [])
            lines = []
            for ann in anns:
                cx, cy, nw, nh = coco_to_yolo_bbox(ann["bbox"], img_w, img_h)
                cls_id = remap_class if remap_class is not None else ann["category_id"]
                lines.append(f"{cls_id} {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}")

            label_path.write_text("\n".join(lines) + ("\n" if lines else ""))

    print(f"  {variant_name}: train={len(train_ids)} imgs, val={len(val_ids)} imgs")


def create_yaml_configs(data, train_ids, val_ids):
    """Create YAML dataset config files."""
    categories = data["categories"]

    # Detection YAML (1 class)
    detect_yaml = PROJECT_ROOT / "grocery_detect.yaml"
    detect_content = (
        f"path: {DATASETS_DIR / 'grocery_detect'}\n"
        f"train: train/images\n"
        f"val: val/images\n"
        f"\n"
        f"nc: 1\n"
        f"names:\n"
        f"  0: product\n"
    )
    detect_yaml.write_text(detect_content)
    print(f"  Written: {detect_yaml}")

    # Classification YAML (356 classes)
    classify_yaml = PROJECT_ROOT / "grocery_classify.yaml"
    lines = [
        f"path: {DATASETS_DIR / 'grocery_classify'}",
        "train: train/images",
        "val: val/images",
        "",
        f"nc: {len(categories)}",
        "names:",
    ]
    for cat in sorted(categories, key=lambda c: c["id"]):
        # Escape quotes in category names for YAML safety
        name = cat["name"].replace("'", "''")
        lines.append(f"  {cat['id']}: '{name}'")

    classify_yaml.write_text("\n".join(lines) + "\n")
    print(f"  Written: {classify_yaml}")


def main():
    print("Loading annotations...")
    data = load_annotations()

    images = data["images"]
    annotations = data["annotations"]
    categories = data["categories"]

    print(f"  {len(images)} images, {len(annotations)} annotations, {len(categories)} categories")

    # Build lookup maps
    image_info = {img["id"]: img for img in images}
    annotations_by_image = {}
    for ann in annotations:
        annotations_by_image.setdefault(ann["image_id"], []).append(ann)

    # Split
    print("Splitting train/val...")
    train_ids, val_ids = split_images(images, SPLIT_RATIO, SEED)
    print(f"  Train: {len(train_ids)}, Val: {len(val_ids)}")

    # Create datasets
    print("Creating detection dataset (1 class)...")
    create_dataset("grocery_detect", annotations_by_image, image_info, train_ids, val_ids, remap_class=0)

    print("Creating classification dataset (356 classes)...")
    create_dataset("grocery_classify", annotations_by_image, image_info, train_ids, val_ids, remap_class=None)

    # Create YAML configs
    print("Creating YAML configs...")
    create_yaml_configs(data, train_ids, val_ids)

    # Verification: spot-check
    print("\nVerification spot-check:")
    first_train_id = sorted(train_ids)[0]
    info = image_info[first_train_id]
    fname = info["file_name"]
    stem = Path(fname).stem

    detect_label = DATASETS_DIR / "grocery_detect" / "train" / "labels" / f"{stem}.txt"
    classify_label = DATASETS_DIR / "grocery_classify" / "train" / "labels" / f"{stem}.txt"

    print(f"  Image: {fname} ({info['width']}x{info['height']})")
    print(f"  Annotations: {len(annotations_by_image.get(first_train_id, []))}")

    if detect_label.exists():
        lines = detect_label.read_text().strip().split("\n")
        print(f"  Detect labels: {len(lines)} lines, first: {lines[0]}")

    if classify_label.exists():
        lines = classify_label.read_text().strip().split("\n")
        print(f"  Classify labels: {len(lines)} lines, first: {lines[0]}")

    # Cross-check one annotation
    ann = annotations_by_image[first_train_id][0]
    cx, cy, nw, nh = coco_to_yolo_bbox(ann["bbox"], info["width"], info["height"])
    print(f"\n  Original COCO bbox: {ann['bbox']} (cat_id={ann['category_id']})")
    print(f"  Converted YOLO:     {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}")

    print("\nDone!")


if __name__ == "__main__":
    main()
