import sys
import os
import sqlite3
import signal
import psutil

# 获取当前脚本所在目录的上一级目录作为基准
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# 假设数据库在 web_prototype 同级或内部，根据之前的 ls 输出来看，应该在 socks5-ss2/instance/xray.db 或者 socks5-ss2/xray.db
# 先尝试常见位置
DB_PATH = 'instance/xray.db'
if not os.path.exists(DB_PATH):
    DB_PATH = 'xray.db'

SERVICE_DIR = 'xray_services'

def force_delete(port):
    print(f"正在强制删除服务: {port}")
    
    # 1. 杀进程
    try:
        pid_file = os.path.join(SERVICE_DIR, str(port), 'xray.pid')
        if os.path.exists(pid_file):
            with open(pid_file, 'r') as f:
                content = f.read().strip()
                if content:
                    pid = int(content)
                    if psutil.pid_exists(pid):
                        print(f"发现进程 {pid}，正在终止...")
                        os.kill(pid, signal.SIGKILL)
                    else:
                        print(f"进程 {pid} 不存在")
            
            os.remove(pid_file)
            print("PID 文件已清理")
        else:
            print("PID 文件不存在")
    except Exception as e:
        print(f"清理进程失败 (可能已停止): {e}")

    # 2. 清理数据库
    try:
        print(f"连接数据库: {DB_PATH}")
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # 检查是否存在
        svc = cursor.execute("SELECT id, node_name FROM services WHERE port = ?", (port,)).fetchone()
        if not svc:
            print("数据库中未找到该服务")
            return

        print(f"正在从数据库删除: {svc[1]} (ID: {svc[0]})")
        # 硬删除还是软删除？根据代码逻辑是软删除
        cursor.execute("UPDATE services SET deleted_at = CURRENT_TIMESTAMP, status = 'stopped' WHERE port = ?", (port,))
        conn.commit()
        print("数据库记录已更新为删除状态")
        conn.close()
    except Exception as e:
        print(f"数据库操作失败: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 force_delete.py <端口号> [端口号2 ...]")
        sys.exit(1)
    
    for p in sys.argv[1:]:
        force_delete(p)
