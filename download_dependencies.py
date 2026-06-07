import os
import urllib.request

def download_file(url, dest_path):
    print(f"Downloading {url} -> {dest_path} ...")
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    
    # Progress callback
    def progress_handler(block_num, block_size, total_size):
        read_so_far = block_num * block_size
        if total_size > 0:
            percent = read_so_far * 100 / total_size
            percent = min(100, percent)
            # Print progress cleanly
            sys.stdout.write(f"\rProgress: {percent:.1f}% ({read_so_far / (1024*1024):.1f} MB / {total_size / (1024*1024):.1f} MB)")
            sys.stdout.flush()
        else:
            sys.stdout.write(f"\rProgress: {read_so_far / (1024*1024):.1f} MB")
            sys.stdout.flush()

    try:
        import sys
        urllib.request.urlretrieve(url, dest_path, progress_handler)
        print("\nDownload complete!")
        return True
    except Exception as e:
        print(f"\nError downloading file: {e}")
        return False

if __name__ == "__main__":
    url = "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth"
    dest = os.path.join("hy3dpaint", "ckpt", "RealESRGAN_x4plus.pth")
    download_file(url, dest)
