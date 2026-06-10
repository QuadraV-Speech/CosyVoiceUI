#!/bin/bash

cd "$(dirname "$0")"
mkdir -p tmp
script_name="server"
PID_FILE="tmp/${script_name}.pid"
LOG_FILE="tmp/${script_name}.log"
CONSOLE_LOG_FILE="tmp/${script_name}.console.log"
DEFAULT_PYTHON="/home/wangwei/miniconda3/envs/speech/bin/python"
if [ -z "$COSYVOICE_PYTHON_BIN" ]; then
    if [ -x "$DEFAULT_PYTHON" ]; then
        COSYVOICE_PYTHON_BIN="$DEFAULT_PYTHON"
    else
        COSYVOICE_PYTHON_BIN="python3"
    fi
fi
CMD=(env "COSYVOICE_LOG_FILE=$LOG_FILE" "$COSYVOICE_PYTHON_BIN" -m CosyVoiceUI.server)
> $LOG_FILE
> $CONSOLE_LOG_FILE

start() {
    # Check if the process is already running
    if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        echo "Process is already running."
        exit 1
    fi
    
    # Start the process
    echo "Starting process..."
    nohup "${CMD[@]}" >> "$CONSOLE_LOG_FILE" 2>&1 &
    
    # Save the PID
    echo $! > "$PID_FILE"
    echo "Process started with PID $(cat "$PID_FILE")"
}

stop() {
    # Check if PID file exists
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        # Kill the process
        if kill -0 "$PID" 2>/dev/null; then
            echo "Stopping process with PID $PID..."
            kill "$PID"
            rm "$PID_FILE"
            echo "Process stopped."
        else
            echo "Process with PID $PID not found."
            rm "$PID_FILE"
        fi
    else
        echo "PID file not found. Process may not be running."
    fi
}

case "$1" in
    -k)
        stop
        ;;
    *)
        start
        ;;
esac
