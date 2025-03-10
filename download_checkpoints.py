import os
import requests

def download_checkpoints(env_path):
    """Downloads the oemer checkpoints to the specified environment path if they don't exist."""

    base_url = "https://github.com/BreezeWhite/oemer/releases/download/checkpoints/"
    checkpoint_files = {
        "unet_big": {"model": "1st_model.onnx", "weights": "1st_weights.h5"},
        "seg_net": {"model": "2nd_model.onnx", "weights": "2nd_weights.h5"},
    }

    for checkpoint_dir, files in checkpoint_files.items():
        target_dir = os.path.join(env_path, "lib", "site-packages", "oemer", "checkpoints", checkpoint_dir)
        os.makedirs(target_dir, exist_ok=True)

        for filename, filename_with_prefix in files.items():
            # Check if the final file exists before downloading
            new_filepath = os.path.join(target_dir, f"{filename}.onnx" if filename == "model" else f"{filename}.h5")
            if os.path.exists(new_filepath):
                print(f"{new_filepath} already exists, skipping download.")
                continue

            url = base_url + filename_with_prefix
            print(f"Downloading {url}...")
            response = requests.get(url)
            response.raise_for_status()

            filepath = os.path.join(target_dir, filename_with_prefix)
            print(f"Saving {filename_with_prefix} to {filepath}...")
            with open(filepath, "wb") as f:
                f.write(response.content)

            # Rename the file
            if not os.path.exists(new_filepath):
                print(f"Renaming {filepath} to {new_filepath}...")
                os.rename(filepath, new_filepath)
            else:
                print(f"{new_filepath} already exists, skipping rename.")

    print("Checkpoints download complete!")

if __name__ == "__main__":
    # Dynamically determine the environment path
    env_path = os.path.join("miniconda", "envs", "pdf2muse")
    download_checkpoints(env_path)
