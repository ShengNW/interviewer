#!/bin/bash
set -e

echo "=== 启动 Interviewer 应用: $(date) ==="

# 1. 停止可能占用的端口
echo "检查端口8090..."
fuser -k 8090/tcp 2>/dev/null || true
sleep 2

# 2. 激活虚拟环境
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
    echo "虚拟环境已激活"
else
    echo "错误: 未找到虚拟环境"
    exit 1
fi

# 3. 创建日志目录
mkdir -p logs

# 4. 启动应用（静默模式）
echo "启动应用..."
echo "应用日志: logs/app.log"
nohup python app.py > logs/app.log 2>&1 &

# 5. 等待启动
sleep 3

# 6. 检查状态
if ps aux | grep -q "[p]ython app.py"; then
    PID=$(pgrep -f "python app.py")
    echo "✅ 应用启动成功！"
    echo "  进程ID: $PID"
    echo "  端口: 8090"
    echo "  访问地址: http://localhost:8090"
    echo "  查看日志: tail -f logs/app.log"
else
    echo "❌ 应用启动失败"
    echo "查看错误日志:"
    tail -20 logs/app.log
fi
