# Newera MC 运维说明（管理通道 / SSH 反代）

## 新增的 Secrets（仓库 Settings → Secrets and variables → Actions）
| Secret | 用途 |
|---|---|
| `MC_ADMIN_TOKEN` | 面板 ↔ 模组 ↔ 代理 共享的管理令牌（已设置，勿外泄） |
| `MC_SSH_KEY` | runner → VPS 反向隧道的 SSH 私钥（已设置；对应公钥已写入 VPS `/root/.ssh/authorized_keys`，仅允许端口转发） |
| `FRPC_TOKEN` | 原有：玩家连接隧道 |

## 管理通道结构
```
玩家 ---frp(45079)---> runner:11541 (MC 服务器)
面板 mc.newera2625.top
  ├─ /api/mc/* （admin 操作）--经 SSH 反代--> runner 127.0.0.1:12501（模组 API）
  │     ├─ GET  /api/players        在线玩家+状态
  │     ├─ POST /api/command        执行任意 MC 指令（踢/给物品/回血/聊天等）
  │     ├─ POST /api/chat/push      网站聊天推送到游戏
  │     └─ POST /api/stop           优雅关服
  ├─ /api/server/* （开关服）--经 SSH 反代--> runner 127.0.0.1:12502（mc-agent.py）
  │     ├─ GET  /api/server/status
  │     ├─ POST /api/server/start
  │     └─ POST /api/server/stop
  └─ /api/status（模组每5s推送玩家状态：血量/饥饿/坐标/背包 → DB）
```

## 模组说明
- `mods/newera-mc-auth-1.0.0.jar`：进服校验（未绑定 SSO → 拒绝连接）、状态上报、管理 API、聊天互通
- 配置 `config/newera-mc-auth.json`：`authToken` 留空，运行时由 workflow 注入环境变量 `NEWERA_MC_AUTH_TOKEN`
- 管理 API 仅监听 127.0.0.1 + 校验 `X-Auth-Token`，且只经 SSH 反向隧道可达

## 绑定流程
1. 玩家访问 https://mc.newera2625.top → SSO 登录
2. 个人中心输入自己的 MC 游戏名 → 自动绑定（离线服按游戏名计算 UUID）
3. 玩家进服 → 模组调 `/api/check` → 已绑定放行 / 未绑定拒绝连接

## 手工触发
`workflow_dispatch` 或推 main 分支即自动跑；也可在 Actions 页手动 Run workflow。
