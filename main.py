import sys
import os
import traceback


def _excepthook(exc_type, exc_value, exc_tb):
    """Print uncaught exceptions to stderr and keep the app alive.

    PyQt6 calls qFatal -> abort() when a slot raises an unhandled
    Python exception, which obscures the traceback inside a macOS
    crash report. Installing this excepthook before QApplication is
    created routes those exceptions through Python's normal
    traceback printer instead, so a buggy slot logs a stack trace
    and the user can keep working.
    """
    traceback.print_exception(exc_type, exc_value, exc_tb)


sys.excepthook = _excepthook


def main():
    print(f"Python Executable: {sys.executable}")
    print(f"Current Working Directory: {os.getcwd()}")
    print(f"System Path: {sys.path}")
    
    # Check dependencies before loading Controller (which imports them at top level)
    try:
        import numpy
        print(f"Numpy Version: {numpy.__version__}")
        print(f"Numpy File: {numpy.__file__}")
    except ImportError as e:
        print("CRITICAL: Numpy not found. Please run 'pip install -r requirements.txt'")
        print(f"Error details: {e}")
        input("Press Enter to exit...")
        return
        
    try:
        from PyQt6.QtWidgets import QApplication
        from controller.main_controller import MainController
    except ImportError as e:
        print(f"CRITICAL: Failed to import Dependencies: {e}")
        return

    app = QApplication(sys.argv)
    
    # Initialize the controller
    controller = MainController()
    controller.start()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
