from pathlib import Path

from prepare_railmap import SOURCE_PATH, generate_railmap

SOURCE_PATH.write_text(generate_railmap())
Path("tools/prepare_railmap.py").unlink(missing_ok=True)
Path(__file__).unlink(missing_ok=True)
