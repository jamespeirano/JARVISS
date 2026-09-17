"""Offline emergency assistant proof of concept."""
import os

# Set before importing ONNX Runtime: its runtime opt-out also prevents the native
# uploader and device identifier from being created on macOS/Linux.
os.environ['ORT_DISABLE_TELEMETRY'] = '1'
