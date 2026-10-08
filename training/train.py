"""
Fine-tunes YOLOv8m on the prepared pothole dataset with the settings reported in the paper
(640x640 input, 100 epochs, AdamW) and copies the best weights to assets/models/.

Usage:
    python training/prepare_dataset.py --src path/to/kaggle/pothole-detection
    python training/train.py
"""
import argparse
import os
import shutil

from ultralytics import YOLO

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_OUT = os.path.join(ROOT_DIR, "assets", "models", "pothole_yolov8.pt")


def main():
    parser = argparse.ArgumentParser(description="Train the IPDS pothole detector.")
    parser.add_argument("--data", default="datasets/pothole_yolo/data.yaml", help="data.yaml from prepare_dataset.py")
    parser.add_argument("--model", default="yolov8m.pt", help="Pretrained base model")
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=16, help="Lower this if you run out of GPU memory")
    parser.add_argument("--device", default=None, help="e.g. 0 for the first GPU, or cpu")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    model = YOLO(args.model)
    results = model.train(
        data=args.data,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        optimizer="AdamW",
        device=args.device,
        seed=args.seed,
        project=os.path.join(ROOT_DIR, "runs"),
        name="pothole_yolov8m",
    )

    best = os.path.join(results.save_dir, "weights", "best.pt")
    os.makedirs(os.path.dirname(MODEL_OUT), exist_ok=True)
    shutil.copy2(best, MODEL_OUT)
    print(f"Best weights copied to {MODEL_OUT}")

    metrics = YOLO(MODEL_OUT).val(data=args.data, imgsz=args.imgsz)
    print(f"mAP@0.5 = {metrics.box.map50:.4f}  mAP@0.5:0.95 = {metrics.box.map:.4f}  "
          f"P = {metrics.box.mp:.4f}  R = {metrics.box.mr:.4f}")


if __name__ == "__main__":
    main()
