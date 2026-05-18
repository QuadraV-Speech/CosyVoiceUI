#!/bin/bash
set -e

###################################
# 配置
###################################

CONTAINER_NAME="cosyvoice-server"
IMAGE_NAME="soar97/triton-cosyvoice:25.06"

GPU_ID="1"

HOST_HTTP_PORT=18000
HOST_GRPC_PORT=18001
HOST_METRICS_PORT=18002

WORKSPACE_DIR="/workspace"
COSYVOICE_DIR="${WORKSPACE_DIR}/CosyVoice"
TRITON_DIR="${COSYVOICE_DIR}/runtime/triton_trtllm"

LOG_FILE="/tmp/cosyvoice.log"

# 配置项
DECOUPLED_MODE="False"

KV_CACHE_FREE_GPU_MEMORY_FRACTION="0.4"

###################################
# 安装
###################################

install_service() {

    echo "===== pull image ====="

    docker pull "${IMAGE_NAME}"

    echo "===== recreate container ====="

    docker rm -f "${CONTAINER_NAME}" 2>/dev/null || true

    docker run -dit \
        --name "${CONTAINER_NAME}" \
        --restart unless-stopped \
        --gpus "\"device=${GPU_ID}\"" \
        --shm-size=2g \
        -p "${HOST_HTTP_PORT}:18000" \
        -p "${HOST_GRPC_PORT}:18001" \
        -p "${HOST_METRICS_PORT}:18002" \
        "${IMAGE_NAME}" \
        /bin/bash

    echo "===== init cosyvoice ====="

    docker exec "${CONTAINER_NAME}" /bin/bash -c "
set -e

export HF_ENDPOINT=https://hf-mirror.com

cd ${WORKSPACE_DIR}

if [ ! -d CosyVoice ]; then
    git clone https://github.com/FunAudioLLM/CosyVoice.git
fi

cd ${COSYVOICE_DIR}

git submodule update --init --recursive

cd ${TRITON_DIR}

# 修改 decoupled mode
sed -i -E 's/DECOUPLED_MODE=(True|False)/DECOUPLED_MODE=${DECOUPLED_MODE}/g' run_cosyvoice3.sh

# 修改 kv cache fraction
sed -i -E 's/--kv_cache_free_gpu_memory_fraction[[:space:]]+[0-9.]+/--kv_cache_free_gpu_memory_fraction ${KV_CACHE_FREE_GPU_MEMORY_FRACTION}/g' run_cosyvoice3.sh

echo '===== begin install ====='

bash run_cosyvoice3.sh 0 2
"

    echo "===== install success ====="
}

###################################
# 启动
###################################

start_service() {

    echo "===== start service ====="

    docker start "${CONTAINER_NAME}" >/dev/null

    docker exec -d "${CONTAINER_NAME}" /bin/bash -c "
set -e

export HF_ENDPOINT=https://hf-mirror.com

cd ${TRITON_DIR}

pkill -f tritonserver || true
pkill -f trtllm-serve || true
pkill -f 'trtllm' || true

# 启动前再次确保参数正确
sed -i -E 's/DECOUPLED_MODE=(True|False)/DECOUPLED_MODE=${DECOUPLED_MODE}/g' run_cosyvoice3.sh

sed -i -E 's/--kv_cache_free_gpu_memory_fraction[[:space:]]+[0-9.]+/--kv_cache_free_gpu_memory_fraction ${KV_CACHE_FREE_GPU_MEMORY_FRACTION}/g' run_cosyvoice3.sh

nohup bash run_cosyvoice3.sh 3 3 > ${LOG_FILE} 2>&1 &
"

    echo "===== service started ====="
}

###################################
# 停止
###################################

stop_service() {

    echo "===== stop service ====="

    docker exec "${CONTAINER_NAME}" /bin/bash -c "
pkill -f tritonserver || true
pkill -f trtllm-serve || true
pkill -f 'trtllm' || true
"

    echo "===== service stopped ====="
}

###################################
# 重启
###################################

restart_service() {

    stop_service

    sleep 3

    start_service
}

###################################
# 日志
###################################

show_logs() {

    docker exec -it "${CONTAINER_NAME}" tail -f "${LOG_FILE}"
}

###################################
# 状态
###################################

show_status() {

    echo "===== docker ====="

    docker ps -a | grep "${CONTAINER_NAME}" || true

    echo ""

    echo "===== triton ====="

    curl "http://127.0.0.1:${HOST_HTTP_PORT}/v2/health/ready" || true

    echo ""
}

###################################
# 主入口
###################################

case "$1" in

    install)
        install_service
        ;;

    start)
        start_service
        ;;

    stop)
        stop_service
        ;;

    restart)
        restart_service
        ;;

    logs)
        show_logs
        ;;

    status)
        show_status
        ;;

    *)
        echo ""
        echo "Usage:"
        echo ""
        echo "./cosyvoice.sh install"
        echo "./cosyvoice.sh start"
        echo "./cosyvoice.sh stop"
        echo "./cosyvoice.sh restart"
        echo "./cosyvoice.sh logs"
        echo "./cosyvoice.sh status"
        echo ""
        ;;
esac