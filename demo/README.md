---
title: IPDS Pothole Detector
colorFrom: yellow
colorTo: gray
sdk: gradio
app_file: app.py
pinned: false
license: mit
short_description: YOLOv8 pothole detection from the IPDS research project
---

# IPDS Pothole Detector (Gradio demo)

Browser demo of the vision model from
[IPDS: Real-Time Pothole Detection](https://github.com/SanTiwari07/PotHoleDetection).

## Run locally

```bash
pip install -r demo/requirements.txt
python demo/app.py
```

The weights are downloaded from GitHub Releases on first start if `assets/models/pothole_yolov8.pt` is missing.

## Deploy as a Hugging Face Space

1. Create a new Space at <https://huggingface.co/new-space> and pick **Gradio** as the SDK.
2. Copy the contents of this `demo/` folder (`app.py`, `requirements.txt`, `README.md`, `examples/`) into the Space repo and push.
3. Once it builds, put the Space URL in the GitHub repo's **About → Website** field and in the main README badge.
