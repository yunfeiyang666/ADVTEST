#!/bin/bash
# ==============================================================================
# deploy_sft_pipeline.sh
# Remote deployment and execution automation script for Phase 3 SFT Exporter
# ==============================================================================

# User configuration (change these to match your server connection)
SERVER_IP="your_server_ip"
SERVER_USER="your_username"
SERVER_ROOT="/home/yunyang/ADVTEST"  # target repo root on server

echo "============================================================="
echo "   Phase 3 SFT Exporter Remote Deployment & Execution Tool   "
echo "============================================================="

# 1. Sync local modifications to remote server
echo "--> Syncing local files to server ${SERVER_USER}@${SERVER_IP}:${SERVER_ROOT}..."
rsync -avz --exclude='.git/' \
          --exclude='.venv310/' \
          --exclude='.venv/' \
          --exclude='__pycache__/' \
          --exclude='sft_dataset_test/' \
          --exclude='sft_dataset/' \
          ./ "${SERVER_USER}@${SERVER_IP}:${SERVER_ROOT}/"

if [ $? -ne 0 ]; then
    echo "Error: rsync sync failed!"
    exit 1
fi
echo "--> Sync completed successfully."

# 2. Execute VLM SFT Dataset Export on Server
echo "--> Running SFT Exporter on remote GPU server..."
ssh "${SERVER_USER}@${SERVER_IP}" << EOF
    cd "${SERVER_ROOT}"
    
    # Setup server runtime environment
    source .venv/bin/activate || source .venv310/bin/activate
    
    # Export paths
    export ADVTEST_ROOT="${SERVER_ROOT}"
    export NUSCENES_DATAROOT="${SERVER_ROOT}/data"
    export NUSCENES_VERSION="v1.0-trainval"
    
    echo "--> Starting remote dataset generation..."
    python "1号机代码/DATA_new/analysis/rq1_error_detection/export_sft_dataset.py" \
           --out_dir "${SERVER_ROOT}/1号机代码/DATA_new/sft_dataset"
EOF

echo "============================================================="
echo "   Remote SFT Exporter Pipeline Finished!                     "
echo "============================================================="
