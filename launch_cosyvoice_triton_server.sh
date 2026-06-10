#!/bin/bash
set -e

###################################
# 基础配置
###################################

CONTAINER_NAME="cosyvoice-server"
IMAGE_NAME="docker.1panel.live/soar97/triton-cosyvoice:25.06"

GPU_ID="4"

HOST_HTTP_PORT=18000
HOST_GRPC_PORT=18001
HOST_METRICS_PORT=18002

WORKSPACE_DIR="/workspace"
COSYVOICE_DIR="${WORKSPACE_DIR}/CosyVoice"
TRITON_DIR="${COSYVOICE_DIR}/runtime/triton_trtllm"

LOG_FILE="/tmp/cosyvoice_triton.log"

DECOUPLED_MODE="False"
KV_CACHE_FREE_GPU_MEMORY_FRACTION="0.8"

###################################
# 颜色配置
###################################

RED='\033[1;31m'
GREEN='\033[1;32m'
YELLOW='\033[1;33m'
BLUE='\033[1;34m'
CYAN='\033[1;36m'
NC='\033[0m'

log_info() {
    echo -e "${BLUE}[INFO] $*${NC}"
}

log_ok() {
    echo -e "${GREEN}[OK] $*${NC}"
}

log_warn() {
    echo -e "${YELLOW}[WARN] $*${NC}"
}

log_err() {
    echo -e "${RED}[ERROR] $*${NC}"
}

log_step() {
    echo -e "${CYAN}========== $* ==========${NC}"
}

###################################
# 工具函数
###################################

container_exists() {
    docker ps -a --format '{{.Names}}' | grep -wq "${CONTAINER_NAME}"
}

container_running() {
    docker ps --format '{{.Names}}' | grep -wq "${CONTAINER_NAME}"
}

ensure_container_exists() {
    if ! container_exists; then
        log_err "容器不存在：${CONTAINER_NAME}"
        log_err "请先执行：$0 install"
        exit 1
    fi
}

ensure_container_running() {
    ensure_container_exists

    if ! container_running; then
        log_warn "容器未运行，正在启动：${CONTAINER_NAME}"
        docker start "${CONTAINER_NAME}" >/dev/null
        log_ok "容器已启动"
    fi
}

exec_in_container() {
    docker exec "${CONTAINER_NAME}" /bin/bash -c "$1"
}

###################################
# 安装步骤
###################################

install_create_container() {
    log_step "创建容器"

    docker rm -f "${CONTAINER_NAME}" 2>/dev/null || true

    docker run -dit \
        --name "${CONTAINER_NAME}" \
        --restart unless-stopped \
        --gpus "\"device=${GPU_ID}\"" \
        --ipc=host \
        --shm-size=8g \
        -p "${HOST_HTTP_PORT}:18000" \
        -p "${HOST_GRPC_PORT}:18001" \
        -p "${HOST_METRICS_PORT}:18002" \
        "${IMAGE_NAME}" \
        /bin/bash

    log_ok "容器创建完成：${CONTAINER_NAME}"
}

install_clone_repo() {
    log_step "克隆 CosyVoice 仓库"

    exec_in_container "
set -e

export GIT_HTTP_VERSION=HTTP/1.1
export GIT_TERMINAL_PROMPT=0

cd ${WORKSPACE_DIR}

if [ ! -d CosyVoice ]; then
    git clone https://github.com/FunAudioLLM/CosyVoice.git
else
    echo 'CosyVoice already exists, skip clone'
fi

cd ${COSYVOICE_DIR}
git submodule update --init --recursive
"

    log_ok "仓库准备完成"
}

install_modify_script() {
    log_step "修改 run_cosyvoice3.sh 配置"

    exec_in_container "
set -e

cd ${TRITON_DIR}

if [ ! -f run_cosyvoice3.sh ]; then
    echo 'run_cosyvoice3.sh not found'
    exit 1
fi

sed -i -E 's/DECOUPLED_MODE=(True|False)/DECOUPLED_MODE=${DECOUPLED_MODE}/g' run_cosyvoice3.sh

sed -i -E 's/--kv_cache_free_gpu_memory_fraction[[:space:]]+[0-9.]+/--kv_cache_free_gpu_memory_fraction ${KV_CACHE_FREE_GPU_MEMORY_FRACTION}/g' run_cosyvoice3.sh

echo 'current config:'
grep -n 'DECOUPLED_MODE=' run_cosyvoice3.sh || true
grep -n 'kv_cache_free_gpu_memory_fraction' run_cosyvoice3.sh || true
"

    log_ok "脚本配置修改完成"
}

install_compile_triton_model() {
    log_step "编译 Triton 模型"

    exec_in_container "
set -e

cd ${TRITON_DIR}

export HF_ENDPOINT=https://hf-mirror.com

bash run_cosyvoice3.sh 0 2
"

    log_ok "Triton 模型编译完成"
}

###################################
# 服务管理
###################################

install_service() {
    log_step "安装 CosyVoice Triton 服务"

    log_info "镜像：${IMAGE_NAME}"
    log_info "容器：${CONTAINER_NAME}"
    log_info "GPU：${GPU_ID}"
    log_info "HTTP 端口：${HOST_HTTP_PORT}"
    log_info "gRPC 端口：${HOST_GRPC_PORT}"
    log_info "Metrics 端口：${HOST_METRICS_PORT}"
    log_info "DECOUPLED_MODE：${DECOUPLED_MODE}"
    log_info "KV_CACHE_FREE_GPU_MEMORY_FRACTION：${KV_CACHE_FREE_GPU_MEMORY_FRACTION}"

    log_step "拉取镜像"
    docker pull "${IMAGE_NAME}"

    install_create_container
    install_clone_repo
    install_modify_script
    install_compile_triton_model

    log_ok "安装完成"
    log_info "启动服务：$0 start"
}

start_service() {

    log_step "启动 CosyVoice Triton 服务"

    ensure_container_running

    install_modify_script

    docker exec -d "${CONTAINER_NAME}" /bin/bash -c "
set -e

cd ${TRITON_DIR}

mkdir -p \$(dirname ${LOG_FILE})
touch ${LOG_FILE}


nohup bash run_cosyvoice3.sh 3 3 > ${LOG_FILE} 2>&1 &
"

    sleep 2

    log_ok "服务启动命令已提交"

    log_info "日志文件：${LOG_FILE}"

    log_info "查看日志："
    echo "    $0 logs"

    log_info "健康检查："
    echo "    http://127.0.0.1:${HOST_HTTP_PORT}/v2/health/ready"
}

stop_service() {
    log_step "停止 CosyVoice Triton 服务"

    ensure_container_running

    exec_in_container "
ps -ef | grep -E 'tritonserver|trtllm|cosyvoice' | grep -v grep | awk '{print \$2}' | xargs -r kill -9
"

    log_ok "服务已停止"
}

restart_service() {
    log_step "重启 CosyVoice Triton 服务"

    stop_service
    start_service

    log_ok "服务已重启"
}

show_logs() {
    ensure_container_running

    log_step "查看服务日志"

    docker exec -it "${CONTAINER_NAME}" /bin/bash -c "
touch ${LOG_FILE}
tail -f ${LOG_FILE}
"
}

show_status() {
    log_step "容器状态"

    docker ps -a | grep "${CONTAINER_NAME}" || true

    echo ""
    log_step "服务进程"

    if container_exists; then
        docker exec "${CONTAINER_NAME}" /bin/bash -c "
ps -ef | grep -E 'tritonserver|trtllm' | grep -v grep || true
" || true
    else
        log_warn "容器不存在"
    fi

    echo ""
    log_step "Triton Health"

    curl -s "http://127.0.0.1:${HOST_HTTP_PORT}/v2/health/ready" || true
    echo ""
}

remove_service() {
    log_step "删除容器"

    docker rm -f "${CONTAINER_NAME}" 2>/dev/null || true

    log_ok "容器已删除：${CONTAINER_NAME}"
}

show_usage() {
    echo ""
    echo -e "${CYAN}Usage:${NC}"
    echo "  $0 install    安装：拉取镜像、创建容器、克隆仓库、编译模型"
    echo "  $0 start      启动 Triton 服务"
    echo "  $0 stop       停止 Triton 服务"
    echo "  $0 restart    重启 Triton 服务"
    echo "  $0 logs       查看服务日志"
    echo "  $0 status     查看容器、进程、健康状态"
    echo "  $0 remove     删除容器"
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

    remove)
        remove_service
        ;;

    *)
        show_usage
        ;;
esac