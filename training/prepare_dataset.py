"""
Converts the Kaggle "Pothole Detection" dataset (andrewmvd) from Pascal VOC XML to YOLO format.

Dataset: https://www.kaggle.com/datasets/andrewmvd/pothole-detection
Expected input layout (as downloaded and unzipped from Kaggle):
    <src>/images/*.png
    <src>/annotations/*.xml

Output layout (ready for `training/train.py`):
    <dst>/images/{train,val}/*.png
    <dst>/labels/{train,val}/*.txt
    <dst>/data.yaml
"""
import argparse
import math
import os
import random
import shutil
import xml.etree.ElementTree as ET
from typing import List, Tuple

CLASS_NAMES = ["pothole"]


def voc_to_yolo(xml_path: str) -> Tuple[str, List[str]]:
    """Returns (image filename, YOLO label lines) for one VOC annotation file."""
    root = ET.parse(xml_path).getroot()
    filename = root.findtext("filename")
    width = float(root.findtext("size/width"))
    height = float(root.findtext("size/height"))

    lines = []
    for obj in root.findall("object"):
        name = obj.findtext("name").strip().lower()
        if name not in CLASS_NAMES:
            continue
        box = obj.find("bndbox")
        x1, y1, x2, y2 = (float(box.findtext(k)) for k in ("xmin", "ymin", "xmax", "ymax"))
        # Clamp to the image in case an annotation spills over the border
        x1, x2 = max(0.0, x1), min(width, x2)
        y1, y2 = max(0.0, y1), min(height, y2)
        if x2 <= x1 or y2 <= y1:
            continue
        cx, cy = (x1 + x2) / 2 / width, (y1 + y2) / 2 / height
        w, h = (x2 - x1) / width, (y2 - y1) / height
        lines.append(f"{CLASS_NAMES.index(name)} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}")
    return filename, lines


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--src", required=True, help="Unzipped Kaggle dataset folder (contains images/ and annotations/)")
    parser.add_argument("--dst", default="datasets/pothole_yolo", help="Output folder for the YOLO dataset")
    parser.add_argument("--val-ratio", type=float, default=0.1,
                        help="Fraction of images used for validation (paper: 67 of 665 = 10%%)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for a reproducible split")
    args = parser.parse_args()

    ann_dir = os.path.join(args.src, "annotations")
    img_dir = os.path.join(args.src, "images")
    xml_files = sorted(f for f in os.listdir(ann_dir) if f.endswith(".xml"))
    if not xml_files:
        raise SystemExit(f"No .xml annotations found in {ann_dir}")

    random.Random(args.seed).shuffle(xml_files)
    n_val = math.ceil(len(xml_files) * args.val_ratio)
    splits = {"val": xml_files[:n_val], "train": xml_files[n_val:]}

    counts = {}
    for split, files in splits.items():
        os.makedirs(os.path.join(args.dst, "images", split), exist_ok=True)
        os.makedirs(os.path.join(args.dst, "labels", split), exist_ok=True)
        boxes = 0
        for xml_name in files:
            filename, lines = voc_to_yolo(os.path.join(ann_dir, xml_name))
            img_path = os.path.join(img_dir, filename)
            if not os.path.exists(img_path):
                # Some VOC files carry a stale filename; fall back to the annotation's stem
                stem = os.path.splitext(xml_name)[0]
                matches = [f for f in os.listdir(img_dir) if os.path.splitext(f)[0] == stem]
                if not matches:
                    print(f"  ! skipping {xml_name}: image not found")
                    continue
                filename, img_path = matches[0], os.path.join(img_dir, matches[0])
            shutil.copy2(img_path, os.path.join(args.dst, "images", split, filename))
            label_path = os.path.join(args.dst, "labels", split, os.path.splitext(filename)[0] + ".txt")
            with open(label_path, "w") as f:
                f.write("\n".join(lines) + ("\n" if lines else ""))
            boxes += len(lines)
        counts[split] = (len(files), boxes)

    with open(os.path.join(args.dst, "data.yaml"), "w") as f:
        f.write(f"path: {os.path.abspath(args.dst)}\n")
        f.write("train: images/train\nval: images/val\n")
        f.write(f"names:\n" + "".join(f"  {i}: {n}\n" for i, n in enumerate(CLASS_NAMES)))

    for split, (n_img, n_box) in counts.items():
        print(f"{split}: {n_img} images, {n_box} boxes")
    print(f"Wrote {os.path.join(args.dst, 'data.yaml')}")


if __name__ == "__main__":
    main()
