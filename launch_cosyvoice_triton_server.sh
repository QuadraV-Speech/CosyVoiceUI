#!/bin/bash
set -e

###################################
# 基础配置
###################################

CONTAINER_NAME="cosyvoice-server"
IMAGE_NAME="docker.1panel.live/soar97/triton-cosyvoice:25.06"

GPU_ID="3"

HOST_HTTP_PORT=18000
HOST_GRPC_PORT=18001
HOST_METRICS_PORT=18002

WORKSPACE_DIR="/workspace"
COSYVOICE_DIR="${WORKSPACE_DIR}/CosyVoice"
TRITON_DIR="${COSYVOICE_DIR}/runtime/triton_trtllm"

LOG_FILE="/tmp/cosyvoice_triton.log"

DECOUPLED_MODE="False"
KV_CACHE_FREE_GPU_MEMORY_FRACTION="0.7"

# Git 克隆代理。优先使用专用变量，否则沿用当前 shell 的代理配置。
GIT_PROXY_URL="${COSYVOICE_GIT_PROXY:-${HTTPS_PROXY:-${HTTP_PROXY:-}}}"
PROXY_RELAY_PORT="${COSYVOICE_PROXY_RELAY_PORT:-17897}"

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

CONTAINER_GIT_PROXY=""
PROXY_RELAY_PID=""

stop_proxy_relay() {
    if [ -n "${PROXY_RELAY_PID}" ] && kill -0 "${PROXY_RELAY_PID}" 2>/dev/null; then
        kill "${PROXY_RELAY_PID}" 2>/dev/null || true
        wait "${PROXY_RELAY_PID}" 2>/dev/null || true
    fi

    PROXY_RELAY_PID=""
}

prepare_git_proxy() {
    CONTAINER_GIT_PROXY=""

    if [ -z "${GIT_PROXY_URL}" ]; then
        log_info "未配置 Git 代理，使用直连"
        return
    fi

    # 容器中的 127.0.0.1 指向容器自身。若代理只监听宿主机回环地址，
    # 临时在当前容器的 Docker 网关上建立 TCP 转发。
    if [[ "${GIT_PROXY_URL}" =~ ^(https?://)([^/@]+@)?(127\.0\.0\.1|localhost):([0-9]+)(/.*)?$ ]]; then
        local proxy_scheme="${BASH_REMATCH[1]}"
        local proxy_auth="${BASH_REMATCH[2]}"
        local proxy_port="${BASH_REMATCH[4]}"
        local proxy_path="${BASH_REMATCH[5]}"
        local docker_gateway

        if ! command -v ncat >/dev/null 2>&1; then
            log_err "代理监听在本机回环地址，但未安装 ncat，容器无法访问该代理"
            log_err "请安装 ncat，或将 COSYVOICE_GIT_PROXY 设置为容器可访问的代理地址"
            return 1
        fi

        if ! [[ "${PROXY_RELAY_PORT}" =~ ^[0-9]+$ ]] ||
            [ "${PROXY_RELAY_PORT}" -lt 1 ] ||
            [ "${PROXY_RELAY_PORT}" -gt 65535 ]; then
            log_err "无效的代理转发端口：${PROXY_RELAY_PORT}"
            return 1
        fi

        docker_gateway="$(docker inspect \
            --format '{{range .NetworkSettings.Networks}}{{.Gateway}}{{end}}' \
            "${CONTAINER_NAME}")"

        if [ -z "${docker_gateway}" ]; then
            log_err "无法获取容器的 Docker 网关地址"
            return 1
        fi

        ncat -l "${docker_gateway}" "${PROXY_RELAY_PORT}" \
            --keep-open \
            --sh-exec "ncat 127.0.0.1 ${proxy_port}" \
            >/tmp/cosyvoice_git_proxy_relay.log 2>&1 &
        PROXY_RELAY_PID=$!

        sleep 1
        if ! kill -0 "${PROXY_RELAY_PID}" 2>/dev/null; then
            log_err "代理转发启动失败，详情见 /tmp/cosyvoice_git_proxy_relay.log"
            PROXY_RELAY_PID=""
            return 1
        fi

        CONTAINER_GIT_PROXY="${proxy_scheme}${proxy_auth}${docker_gateway}:${PROXY_RELAY_PORT}${proxy_path}"
        log_ok "已为容器建立临时 Git 代理转发"
    else
        CONTAINER_GIT_PROXY="${GIT_PROXY_URL}"
        log_info "使用 COSYVOICE_GIT_PROXY/系统代理克隆仓库"
    fi
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

    prepare_git_proxy
    trap stop_proxy_relay EXIT

    local proxy_args=()
    if [ -n "${CONTAINER_GIT_PROXY}" ]; then
        proxy_args=(
            -e "HTTP_PROXY=${CONTAINER_GIT_PROXY}"
            -e "HTTPS_PROXY=${CONTAINER_GIT_PROXY}"
            -e "http_proxy=${CONTAINER_GIT_PROXY}"
            -e "https_proxy=${CONTAINER_GIT_PROXY}"
        )
    fi

    local clone_status=0
    docker exec "${proxy_args[@]}" "${CONTAINER_NAME}" /bin/bash -c "
set -e

export GIT_TERMINAL_PROMPT=0

cd ${WORKSPACE_DIR}

if [ -d CosyVoice/.git ] && git -C CosyVoice rev-parse --verify HEAD >/dev/null 2>&1; then
    echo 'CosyVoice already cloned, skip clone'
else
    if [ -e CosyVoice ]; then
        echo 'Removing incomplete CosyVoice checkout'
        rm -rf CosyVoice
    fi

    git -c http.version=HTTP/1.1 clone --progress \
        https://github.com/FunAudioLLM/CosyVoice.git
fi

cd ${COSYVOICE_DIR}
git -c http.version=HTTP/1.1 submodule update --init --recursive --progress
" || clone_status=$?

    stop_proxy_relay
    trap - EXIT

    if [ "${clone_status}" -ne 0 ]; then
        log_err "CosyVoice 仓库克隆失败"
        return "${clone_status}"
    fi

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
