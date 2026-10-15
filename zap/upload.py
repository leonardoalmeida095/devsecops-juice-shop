import sys
from pathlib import Path

from google.cloud import storage


def main() -> int:
    if len(sys.argv) != 4:
        print("uso: upload.py OUT_DIR BUCKET PREFIX")
        return 1
    out_dir = Path(sys.argv[1])
    bucket_name = sys.argv[2]
    prefix = sys.argv[3].strip("/")
    files = sorted(path for path in out_dir.iterdir() if path.is_file())
    if not files:
        print("Nenhum relatório para enviar")
        return 1
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    for path in files:
        blob = bucket.blob(f"{prefix}/{path.name}")
        blob.upload_from_filename(str(path))
        print(f"gs://{bucket_name}/{prefix}/{path.name}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"Falha no upload: {exc.__class__.__name__}")
        sys.exit(1)
