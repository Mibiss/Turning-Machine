#!/bin/bash
# Setup script for GCP VM - run this after SSH-ing into the VM
# Usage: bash setup_vm.sh

set -e

echo "=== Setting up GCP VM for YOLO training ==="

# Check GPU
echo "Checking GPU..."
nvidia-smi || { echo "ERROR: No GPU detected!"; exit 1; }

# Install/upgrade packages
echo "Installing Python packages..."
pip install --upgrade pip
pip install ultralytics==8.1.0 torch torchvision --upgrade
pip install numpy scipy scikit-learn

# Verify CUDA
python3 -c "import torch; print(f'PyTorch {torch.__version__}, CUDA available: {torch.cuda.is_available()}, Device: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"N/A\"}')"

echo ""
echo "=== Setup complete! ==="
echo "Now run:"
echo "  python3 train_classify.py --phase a --data-dir ."
echo "  python3 train_classify.py --phase b --data-dir ."
