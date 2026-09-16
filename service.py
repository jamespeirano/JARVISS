from jarviss.service import main

if __name__ == '__main__':
    import multiprocessing
    multiprocessing.freeze_support()
    # Initialize native numerical libraries on the main thread before stdin blocks.
    # Loading NumPy through ONNX in a frozen worker can deadlock on Windows.
    import numpy
    import onnxruntime
    onnxruntime.disable_telemetry_events()
    main()
