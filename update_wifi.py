import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE_DIR, '.env')

def main():
    if not os.path.exists(ENV_PATH):
        print(f"Error: {ENV_PATH} not found.")
        print("Create it from the template first:  cp .env.example .env  (then edit WIFI_SSID / WIFI_PASSWORD)")
        return

    ssid = ""
    password = ""

    # Parse .env file manually so we don't need python-dotenv dependency
    with open(ENV_PATH, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            
            if line.startswith("WIFI_SSID="):
                ssid = line.split("=", 1)[1].strip('"\'')
            elif line.startswith("WIFI_PASSWORD="):
                password = line.split("=", 1)[1].strip('"\'')

    if not ssid or not password:
        print("Error: Could not find WIFI_SSID or WIFI_PASSWORD in .env")
        return

    # Create C++ Header content
    header_content = f"""// AUTO-GENERATED FILE. DO NOT EDIT DIRECTLY.
// Update the .env file in the root directory and run update_wifi.py

const char* ssid = "{ssid}";
const char* password = "{password}";
"""

    cam_path = os.path.join(BASE_DIR, "ESP_32_Code", "esp_32_cam_final", "credentials.h")
    sensor_path = os.path.join(BASE_DIR, "ESP_32_Code", "esp_32_final", "credentials.h")

    # Write to both directories
    for path in [cam_path, sensor_path]:
        try:
            with open(path, "w") as f:
                f.write(header_content)
            print(f"Successfully synced credentials to: {os.path.relpath(path, BASE_DIR)}")
        except Exception as e:
            print(f"Failed to write to {path}: {e}")

if __name__ == "__main__":
    main()
