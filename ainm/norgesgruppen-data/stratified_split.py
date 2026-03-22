"""
Stratified multi-label train/val split for object detection.

Unlike the naive random image-level split in convert_coco_to_yolo.py,
this ensures every class has representation in the training set.

Strategy:
  1. Build a binary label matrix: images x classes
  2. Use greedy iterative stratification to split images
  3. Single-image classes are ALWAYS placed in train (can't waste them on val)
  4. Create two dataset variants:
     - grocery_classify_stratified: proper stratified split for development
     - grocery_classify_full: ALL images in train (no val) for final competition model

Images are symlinked to save disk space.
"""

import json
import random
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent
COCO_DIR = PROJECT_ROOT / "data" / "coco_dataset" / "train"
ANNOTATIONS_FILE = COCO_DIR / "annotations.json"
IMAGES_DIR = COCO_DIR / "images"
DATASETS_DIR = PROJECT_ROOT / "datasets"

VAL_RATIO = 0.15
SEED = 42


def load_annotations():
    with open(ANNOTATIONS_FILE) as f:
        return json.load(f)


def coco_to_yolo_bbox(bbox, img_w, img_h):
    x, y, w, h = bbox
    cx = max(0.0, min(1.0, (x + w / 2) / img_w))
    cy = max(0.0, min(1.0, (y + h / 2) / img_h))
    nw = max(0.0, min(1.0, w / img_w))
    nh = max(0.0, min(1.0, h / img_h))
    return cx, cy, nw, nh


def iterative_stratified_split(image_ids, image_classes, num_classes, val_ratio, seed):
    """
    Greedy iterative stratification for multi-label data.
    Based on: Sechidis et al., "On the Stratification of Multi-Label Data" (ECML 2011).

    For each class (rarest first), assign images to the split that is furthest
    from its desired proportion for that class.
    """
    rng = np.random.RandomState(seed)

    # Build label matrix: for each image, which classes are present
    img_to_idx = {img_id: i for i, img_id in enumerate(image_ids)}
    n_images = len(image_ids)

    # Count annotations per class per image
    class_counts_per_image = defaultdict(lambda: defaultdict(int))
    for img_id, cls_id in image_classes:
        class_counts_per_image[img_id][cls_id] += 1

    # Binary presence matrix
    label_matrix = np.zeros((n_images, num_classes), dtype=np.int32)
    for img_id, classes in class_counts_per_image.items():
        idx = img_to_idx[img_id]
        for cls_id in classes:
            label_matrix[idx, cls_id] = 1

    # Desired proportions
    desired_train = 1.0 - val_ratio
    desired_val = val_ratio

    train_set = set()
    val_set = set()

    # Step 1: Classes that appear in only 1 image -> force to train
    class_image_counts = label_matrix.sum(axis=0)  # how many images per class
    forced_train = set()
    for cls_id in range(num_classes):
        if class_image_counts[cls_id] == 1:
            img_idx = np.where(label_matrix[:, cls_id] == 1)[0][0]
            forced_train.add(image_ids[img_idx])

    train_set.update(forced_train)
    remaining = [img_id for img_id in image_ids if img_id not in forced_train]
    rng.shuffle(remaining)

    # Step 2: Iterative stratification on remaining images
    # Sort classes by frequency (rarest first) for better stratification
    remaining_idx = [img_to_idx[img_id] for img_id in remaining]
    remaining_label = label_matrix[remaining_idx]

    # Track current counts per class in each split
    train_class_counts = np.zeros(num_classes)
    val_class_counts = np.zeros(num_classes)

    # Add forced train counts
    for img_id in forced_train:
        idx = img_to_idx[img_id]
        train_class_counts += label_matrix[idx]

    # Total per class
    total_class_counts = label_matrix.sum(axis=0).astype(float)
    total_class_counts = np.maximum(total_class_counts, 1)  # avoid div by zero

    # Process remaining images
    # For each image, score it: which split needs it more?
    for i, img_id in enumerate(remaining):
        idx = img_to_idx[img_id]
        img_labels = label_matrix[idx]

        # For classes present in this image, compute how far each split
        # is from its desired proportion
        present_classes = np.where(img_labels == 1)[0]

        if len(present_classes) == 0:
            # No annotations — put in train
            train_set.add(img_id)
            continue

        # Score: sum of (desired_ratio - current_ratio) for present classes
        train_ratios = train_class_counts[present_classes] / total_class_counts[present_classes]
        val_ratios = val_class_counts[present_classes] / total_class_counts[present_classes]

        train_need = np.sum(desired_train - train_ratios)
        val_need = np.sum(desired_val - val_ratios)

        if train_need >= val_need:
            train_set.add(img_id)
            train_class_counts += img_labels
        else:
            val_set.add(img_id)
            val_class_counts += img_labels

    return train_set, val_set


def create_dataset(variant_name, annotations_by_image, image_info, train_ids, val_ids):
    base = DATASETS_DIR / variant_name

    for split_name, split_ids in [("train", train_ids), ("val", val_ids)]:
        if not split_ids:
            continue
        img_dir = base / split_name / "images"
        lbl_dir = base / split_name / "labels"
        img_dir.mkdir(parents=True, exist_ok=True)
        lbl_dir.mkdir(parents=True, exist_ok=True)

        for img_id in split_ids:
            info = image_info[img_id]
            fname = info["file_name"]
            img_w = info["width"]
            img_h = info["height"]

            src = IMAGES_DIR / fname
            dst = img_dir / fname
            if not dst.exists():
                dst.symlink_to(src.resolve())

            label_name = Path(fname).stem + ".txt"
            label_path = lbl_dir / label_name

            anns = annotations_by_image.get(img_id, [])
            lines = []
            for ann in anns:
                cx, cy, nw, nh = coco_to_yolo_bbox(ann["bbox"], img_w, img_h)
                cls_id = ann["category_id"]
                lines.append(f"{cls_id} {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}")

            label_path.write_text("\n".join(lines) + ("\n" if lines else ""))


def create_yaml(name, path, num_classes, categories):
    yaml_path = PROJECT_ROOT / f"{name}.yaml"
    lines = [
        f"path: {path}",
        "train: train/images",
        "val: val/images" if "full" not in name else "val: train/images",
        "",
        f"nc: {num_classes}",
        "names:",
    ]
    for cat in sorted(categories, key=lambda c: c["id"]):
        cat_name = cat["name"].replace("'", "''")
        lines.append(f"  {cat['id']}: '{cat_name}'")
    yaml_path.write_text("\n".join(lines) + "\n")
    return yaml_path


def analyze_split(name, annotations_by_image, train_ids, val_ids, num_classes):
    train_class_counts = Counter()
    val_class_counts = Counter()

    for img_id in train_ids:
        for ann in annotations_by_image.get(img_id, []):
            train_class_counts[ann["category_id"]] += 1
    for img_id in val_ids:
        for ann in annotations_by_image.get(img_id, []):
            val_class_counts[ann["category_id"]] += 1

    zero_train = sum(1 for c in range(num_classes) if train_class_counts[c] == 0)
    zero_val = sum(1 for c in range(num_classes) if val_class_counts[c] == 0)
    total_train = sum(train_class_counts.values())
    total_val = sum(val_class_counts.values())

    ratios = []
    for c in range(num_classes):
        t = train_class_counts[c]
        v = val_class_counts[c]
        if t + v > 0:
            ratios.append(t / (t + v))

    print(f"\n{'='*60}")
    print(f"  {name} Split Analysis")
    print(f"{'='*60}")
    print(f"  Images:      train={len(train_ids)}, val={len(val_ids)}")
    print(f"  Annotations: train={total_train}, val={total_val}")
    print(f"  Classes with 0 train examples: {zero_train}")
    print(f"  Classes with 0 val examples:   {zero_val}")
    print(f"  Per-class train ratio: mean={np.mean(ratios):.3f}, std={np.std(ratios):.3f}")
    print(f"  Min ratio: {np.min(ratios):.3f}, Max: {np.max(ratios):.3f}")


def main():
    print("Loading annotations...")
    data = load_annotations()
    images = data["images"]
    annotations = data["annotations"]
    categories = data["categories"]
    num_classes = len(categories)

    image_info = {img["id"]: img for img in images}
    annotations_by_image = defaultdict(list)
    for ann in annotations:
        annotations_by_image[ann["image_id"]].append(ann)

    image_ids = [img["id"] for img in images]
    image_classes = [(ann["image_id"], ann["category_id"]) for ann in annotations]

    # --- Old split (for comparison) ---
    old_ids = list(image_ids)
    random.seed(SEED)
    random.shuffle(old_ids)
    split_idx = int(len(old_ids) * 0.85)
    old_train = set(old_ids[:split_idx])
    old_val = set(old_ids[split_idx:])
    analyze_split("OLD (random)", annotations_by_image, old_train, old_val, num_classes)

    # --- New stratified split ---
    print("\nComputing stratified split...")
    train_ids, val_ids = iterative_stratified_split(
        image_ids, image_classes, num_classes, VAL_RATIO, SEED
    )
    analyze_split("NEW (stratified)", annotations_by_image, train_ids, val_ids, num_classes)

    # --- Create stratified dataset ---
    print("\nCreating stratified dataset...")
    create_dataset("grocery_classify_stratified", annotations_by_image, image_info, train_ids, val_ids)
    yaml1 = create_yaml(
        "grocery_classify_stratified",
        DATASETS_DIR / "grocery_classify_stratified",
        num_classes, categories
    )
    print(f"  Written: {yaml1}")

    # --- Create full dataset (all images in train, val points to train) ---
    print("Creating full dataset (all 248 images for training)...")
    all_ids = set(image_ids)
    create_dataset("grocery_classify_full", annotations_by_image, image_info, all_ids, set())
    yaml2 = create_yaml(
        "grocery_classify_full",
        DATASETS_DIR / "grocery_classify_full",
        num_classes, categories
    )
    print(f"  Written: {yaml2}")

    print(f"\nDone! Created two new datasets:")
    print(f"  1. grocery_classify_stratified — for development (proper split)")
    print(f"  2. grocery_classify_full — for final model (all data in train)")


if __name__ == "__main__":
    main()
