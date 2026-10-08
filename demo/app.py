"""
Gradio demo for the IPDS pothole detector.

Runs locally (`python demo/app.py`) or as a Hugging Face Space (see demo/README.md).
Only the vision half of IPDS runs here; the ESP32 sensor fusion needs the hardware.
"""
import glob
import os
import tempfile
import urllib.request

import cv2
import gradio as gr
from ultralytics import YOLO

DEMO_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_URL = "https://github.com/SanTiwari07/PotHoleDetection/releases/download/v1.0/pothole_yolov8.pt"
MODEL_PATH = os.getenv("IPDS_MODEL", os.path.join(DEMO_DIR, "..", "assets", "models", "pothole_yolov8.pt"))

# Keep video jobs short so the free CPU Space stays responsive
MAX_VIDEO_SECONDS = 10
VIDEO_FRAME_STRIDE = 2

if not os.path.exists(MODEL_PATH):
    MODEL_PATH = os.path.join(DEMO_DIR, "pothole_yolov8.pt")
    if not os.path.exists(MODEL_PATH):
        print(f"Downloading weights from {MODEL_URL} ...")
        urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)

model = YOLO(MODEL_PATH)


def detect_image(image, conf):
    if image is None:
        return None, "Upload an image first."
    # Gradio gives RGB; ultralytics expects BGR for numpy input
    result = model.predict(cv2.cvtColor(image, cv2.COLOR_RGB2BGR), conf=conf, verbose=False)[0]
    annotated = cv2.cvtColor(result.plot(), cv2.COLOR_BGR2RGB)
    n = len(result.boxes)
    return annotated, f"{n} pothole{'s' if n != 1 else ''} detected"


def detect_video(video_path, conf):
    if video_path is None:
        return None, "Upload a video first."
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    max_frames = int(fps * MAX_VIDEO_SECONDS)

    out_path = os.path.join(tempfile.mkdtemp(), "ipds_output.mp4")
    out = cv2.VideoWriter(out_path, cv2.VideoWriter_fourcc(*"mp4v"), fps / VIDEO_FRAME_STRIDE, (width, height))

    frame_idx, total = 0, 0
    while frame_idx < max_frames:
        ok, frame = cap.read()
        if not ok:
            break
        if frame_idx % VIDEO_FRAME_STRIDE == 0:
            result = model.predict(frame, conf=conf, verbose=False)[0]
            total += len(result.boxes)
            out.write(result.plot())
        frame_idx += 1

    cap.release()
    out.release()
    return out_path, f"Processed the first {frame_idx / fps:.1f}s: {total} detections across sampled frames"


examples = sorted(glob.glob(os.path.join(DEMO_DIR, "examples", "*.jpg")))

with gr.Blocks(title="IPDS Pothole Detector") as demo:
    gr.Markdown(
        "# 🕳️ IPDS: Real-Time Pothole Detection\n"
        "YOLOv8m fine-tuned for potholes (mAP@0.5 = 81.7%). "
        "This demo runs the vision model only; the full system adds an ESP32 sensor node for "
        "accelerometer-based severity and GPS tagging.\n\n"
        "[GitHub](https://github.com/SanTiwari07/PotHoleDetection) · "
        "[Paper (Zenodo)](https://zenodo.org/records/20760578)"
    )
    conf = gr.Slider(0.05, 0.95, value=0.25, step=0.05, label="Confidence threshold")

    with gr.Tab("Image"):
        with gr.Row():
            image_in = gr.Image(type="numpy", label="Road image")
            image_out = gr.Image(type="numpy", label="Detections")
        image_info = gr.Markdown()
        gr.Button("Detect potholes", variant="primary").click(detect_image, [image_in, conf], [image_out, image_info])
        if examples:
            gr.Examples(examples, inputs=image_in)

    with gr.Tab("Video"):
        gr.Markdown(f"Processes the first {MAX_VIDEO_SECONDS} seconds (every {VIDEO_FRAME_STRIDE}nd frame) to keep CPU time low.")
        with gr.Row():
            video_in = gr.Video(label="Dashcam clip")
            video_out = gr.Video(label="Detections")
        video_info = gr.Markdown()
        gr.Button("Detect potholes", variant="primary").click(detect_video, [video_in, conf], [video_out, video_info])

if __name__ == "__main__":
    demo.launch()
