import os
import fairaman
from fairaman.cli import main

if __name__ == "__main__":
    print("fairaman loaded from:", os.path.dirname(fairaman.__file__))
    main()