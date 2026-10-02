#!/usr/bin/env bash
# MC 运维脚本：rcon 控制 / 存档备份 / 优雅停服
set -u

rcon() {
  python3 - "$1" << 'PYEOF'
import socket, struct, sys
def packet(s, rid, ptype, body):
    data = struct.pack('<III', rid, ptype, len(body.encode())+2) + body.encode() + b'\x00\x00'
    s.sendall(data)
def read(s):
    try:
        size = struct.unpack('<I', s.recv(4))[0]
        rid, ptype = struct.unpack('<II', s.recv(8))
        body = s.recv(size - 10).decode(errors='replace')
        return body
    except Exception:
        return ''
try:
    s = socket.create_connection(('127.0.0.1', 25575), timeout=5)
    packet(s, 1, 3, 'newera2625')
    read(s)
    packet(s, 2, 2, sys.argv[1])
    out = read(s)
    print(out.strip())
    s.close()
except Exception as e:
    print(f"rcon error: {e}")
    sys.exit(1)
PYEOF
}

save_all() {
  rcon "save-all flush" >/dev/null 2>&1 || echo "[warn] save-all 失败"
  sleep 2
}

backup_world() {
  save_all
  tar czf world.tar.gz --exclude='*/session.lock' world world_nether world_the_end 2>/dev/null || true
  if [ ! -s world.tar.gz ]; then
    echo "[warn] world.tar.gz 为空或不存在"
  fi
  git config user.email "bot@newera2625.top"
  git config user.name "newera-bot"
  git add world.tar.gz
  if git log --oneline -5 2>/dev/null | grep -q "backup"; then
    git commit --amend -m "backup $(date +%s)" --allow-empty -q
    git push -q --force origin main || echo "[warn] push 失败"
  else
    git commit -m "backup $(date +%s)" --allow-empty -q
    git push -q origin main || echo "[warn] push 失败"
  fi
  echo "[ok] 存档已备份: $(du -h world.tar.gz | cut -f1)"
}

stop_server() {
  rcon "stop" >/dev/null 2>&1 || true
  sleep 3
  pkill -f "server.jar" 2>/dev/null || true
  echo "[ok] 服务器已停止"
}

case "${1:-}" in
  backup_world) backup_world ;;
  stop_server)  stop_server ;;
  *) echo "usage: $0 {backup_world|stop_server}" ;;
esac
