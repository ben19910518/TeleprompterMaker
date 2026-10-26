import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    from teleprompter.main import main
    sys.exit(main())
