# Contributing to IPDS

Thanks for your interest in improving IPDS! Contributions of all sizes are welcome: bug reports, docs fixes, new hardware ports, better models, and field-test data from your city.

## Ways to contribute

- **Report a bug or ask for a feature:** open an [issue](https://github.com/SanTiwari07/PotHoleDetection/issues/new/choose).
- **Share your build:** post photos, videos or logs from your own setup in Discussions. Field data from different roads and countries is especially valuable.
- **Pick up an issue:** look for the [`good first issue`](https://github.com/SanTiwari07/PotHoleDetection/labels/good%20first%20issue) and [`help wanted`](https://github.com/SanTiwari07/PotHoleDetection/labels/help%20wanted) labels.

## Development setup

```bash
git clone https://github.com/SanTiwari07/PotHoleDetection.git
cd PotHoleDetection
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
pytest tests
```

Run the pipeline without hardware on any road video:

```bash
python python/main.py --source path/to/video.mp4
```

The model weights are downloaded automatically on first run.

### Firmware

Sketches live in `ESP_32_Code/`. Copy `.env.example` to `.env`, fill in your WiFi credentials, and run `python update_wifi.py` to generate the git-ignored `credentials.h` files. You can try the sensor node without hardware in the [Wokwi simulation](https://wokwi.com/projects/453817129999607809).

## Pull requests

1. Fork the repo and create a branch from `main`.
2. Keep each PR focused on one change, and add or update tests in `tests/` when you change pipeline logic.
3. Make sure `pytest tests` passes.
4. **Never commit credentials**: `.env` and `credentials.h` are git-ignored for a reason.
5. Describe what you changed and how you tested it (on hardware, Wokwi, or a recorded video).

## Code style

Match the surrounding code: type hints on public functions, docstrings on modules and classes, and configuration as named constants at the top of a file rather than magic numbers.
