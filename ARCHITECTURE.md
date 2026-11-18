# AAM Panel — AI Account Manager 架构契约

> 目标：聚合多个 AI 平台账号（Tabbit 国内/国际，未来 Trae/WorkBuddy），提供
> ① Web 面板（账号/积分/状态）② 统一 OpenAI 兼容反代 ③ 可扩展平台插件层。
>
> 本文档是唯一契约：前端、后端、UI 设计都以它为准。

## 目录结构

```
/opt/aam-panel/
├── ARCHITECTURE.md          # 本文档
├── backend/
│   ├── main.py              # FastAPI 入口（挂载 /api, /v1, 静态根目录）
│   ├── config.py            # 常量（DB 路径、sign key、version）
│   ├── db.py                # SQLite 层（WAL + busy_timeout，建表 + CRUD）
│   ├── api.py               # 面板管理 API（/api/*，含 tokens）
│   ├── gateway.py           # OpenAI 兼容层（/v1/*，多 key 鉴权）
│   ├── platforms/
│   │   ├── __init__.py      # registry: ADAPTERS = {"tabbit": TabbitAdapter,...}
│   │   ├── base.py          # PlatformAdapter 抽象类
│   │   └── tabbit.py        # Tabbit 协议适配器（国内/国际共用）
│   └── requirements.txt
├── frontend/                # Vue3 + Vite + Element Plus
│   ├── package.json
│   ├── index.html           # favicon 内联 data URI
│   ├── vite.config.js       # build.outDir = ../backend/static, base:'./'
│   └── src/
│       ├── main.js / App.vue（侧导航 6 项，中文）
│       ├── styles.css       # B1 深色卡片设计语言 + Element Plus 暗色覆盖
│       ├── lib/toast.js     # 自绘 toast
│       ├── api/index.js     # axios 封装（/api 前缀）
│       └── views/           # Dashboard/Accounts/Platforms/Gateway/Tokens/Settings
├── tools/ui_check.py        # DOM 断言验收（横向溢出/对比度/console）
└── data/aam.db              # SQLite（WAL 模式，双实例共享）
```

端口 **8710**（后端 API + 静态前端，同端口）。如被占用可用 `--port` 指定其它端口。

## DB Schema（sqlite3）

```sql
CREATE TABLE platforms (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  key TEXT UNIQUE NOT NULL,        -- tabbit-domestic / tabbit-intl / trae / workbuddy
  name TEXT NOT NULL,              -- "Tabbit 国内版"
  adapter TEXT NOT NULL,           -- 适配器类名 key: tabbit / trae / workbuddy
  base_url TEXT NOT NULL,          -- https://web.tabbit.com
  proxy TEXT DEFAULT '',           -- 出口代理，如 socks5h://127.0.0.1:1080；空=直连
  enabled INTEGER DEFAULT 1,
  builtin INTEGER DEFAULT 0,       -- 内置平台不可删（可禁用）
  meta TEXT DEFAULT '{}',          -- JSON 附加（version 等）
  created_at TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE accounts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  platform_id INTEGER NOT NULL REFERENCES platforms(id) ON DELETE CASCADE,
  name TEXT NOT NULL,              -- 备注名（默认 secret_mobile 或 user_id 前8位）
  credential TEXT NOT NULL,        -- cookie 串 或 api_key
  credential_type TEXT DEFAULT 'cookie',
  status TEXT DEFAULT 'unknown',   -- unknown / active / expired / error / disabled
  status_msg TEXT DEFAULT '',
  member_level TEXT DEFAULT '',    -- standard / pro / free
  quota_pct REAL,                  -- 0-100 已用百分比
  quota_json TEXT DEFAULT '{}',    -- 原始配额 JSON（重置时间、周期等）
  user_info TEXT DEFAULT '{}',     -- 原始用户信息（user_id/mobile masked）
  check_at TEXT,                   -- 上次检查时间
  last_used_at TEXT,
  request_count INTEGER DEFAULT 0,
  enabled INTEGER DEFAULT 1,
  created_at TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT);

CREATE TABLE request_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  account_id INTEGER, platform_key TEXT, model TEXT,
  ok INTEGER, latency_ms INTEGER, err TEXT DEFAULT '',
  created_at TEXT DEFAULT (datetime('now','localtime'))
);
CREATE INDEX idx_reqlog_time ON request_log(created_at);

CREATE TABLE tokens (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,              -- 用途名，如 "Cherry Studio"
  token TEXT UNIQUE NOT NULL,      -- aam-<40 hex>，网关 Bearer 凭据
  platform_key TEXT DEFAULT '',    -- 绑定平台 key；空=全部平台
  enabled INTEGER DEFAULT 1,
  note TEXT DEFAULT '',
  created_at TEXT DEFAULT (datetime('now','localtime')),
  last_used_at TEXT,
  request_count INTEGER DEFAULT 0
);
```

内置平台（首次启动 seed）：
| key | name | adapter | base_url | proxy |
|---|---|---|---|---|
| tabbit-domestic | Tabbit 国内版 | tabbit | https://web.tabbit.com | (空) |
| tabbit-intl | Tabbit 国际版 | tabbit | https://web.tabbit.ai | socks5h://127.0.0.1:1080 |
| trae | Trae（待接入） | trae | (空) | (空) |
| workbuddy | WorkBuddy（待接入） | workbuddy | (空) | (空) |

## 面板 API 契约（/api/*）

统一响应：成功 `{"ok":true,...}`；失败 HTTP 400/404/500 + `{"detail":"..."}`。

```
GET  /api/overview              → {platforms:[{id,key,name,account_count,active_count,avg_quota_pct}],
                                   stats:{total_accounts,active_accounts,requests_today,errors_today},
                                   gateway:{base_url, models_count}}
GET  /api/platforms             → {items:[platform...]}   # 含 account_count
POST /api/platforms             → body {key,name,adapter,base_url,proxy,enabled,meta} → platform
PUT  /api/platforms/{id}        → body 同上（可部分）→ platform
DELETE /api/platforms/{id}      → 仅非 builtin；否则 400

GET  /api/accounts?platform_id=&status=  → {items:[account + platform_key/platform_name]}
POST /api/accounts              → body {platform_id,name,credential,credential_type} → account（自动测活一次）
PUT  /api/accounts/{id}         → body {name?,credential?,enabled?} → account
DELETE /api/accounts/{id}       → 删除
POST /api/accounts/{id}/check   → 立即测活+刷积分 → {status,status_msg,member_level,quota_pct,quota_json,user_info}
POST /api/accounts/{id}/refresh-quota → 只刷积分

GET  /api/accounts/{id}/models  → {items:[model_id...]}（该账号可用模型，带缓存60s）
GET  /api/stats?days=7          → 请求趋势 [{date,ok,err}]
GET  /api/logs?limit=100        → 请求日志
POST /api/logs/clear            → 清空 request_log → {ok,deleted}(网关页与总览统计随之归零)
POST /api/auto-check/run        → 立刻跑一轮全量账号检测 → {ok,at,total,active,expired,error,unknown,pushed}
GET  /api/settings / POST /api/settings → {panel_key, gateway_key, daily_auto_check, notify_webhook,
                                           auto_check_last_at, auto_check_next_at, auto_check_summary}
```

## 统一网关契约（/v1/*，OpenAI 兼容）

鉴权:`Authorization: Bearer <gateway_key>`(settings 里配;必须是显式设置的随机值,公开默认值 `aam-local-key` 会被拒绝)。

```
GET  /v1/models
→ {"object":"list","data":[
     {"id":"tabbit-domestic/GLM-5.1","object":"model","owned_by":"tabbit-domestic"},
     ... 每个平台 × 每个账号可用模型的并集，带平台前缀
   ]}

POST /v1/chat/completions
body: OpenAI 标准 {model, messages, stream, temperature?...}
→ model 解析规则（按优先级）：
   1. "platform_key/model"  → 指定平台，账号池内轮询
   2. 裸模型名              → 在所有平台里找唯一匹配（多平台同名取第一个启用的，轮询账号）
   3. 找不到 → 404 {"error":{"message":"model not found"}}
→ 账号选择：该平台下 enabled 且 status!=expired 的账号，按 last_used_at 最久未用优先（负载均衡）
→ 流式：SSE 原样透传 OpenAI chunk 格式
→ usage 字段可全 0（上游不提供 token 计量）

鉴权（多 key）：
   1. 主密钥 = settings.gateway_key(须显式设置随机值,设置页可改)
   2. tokens 表任意 enabled=1 行(可绑定 platform_key 限定范围:/v1/models 只返回该平台模型,调用其它平台模型 → 403 permission_error;未绑定=全部平台)
   3. 其余 → 401 {"error":{"message":"invalid API key"}}
   4. 每次调用写入 request_log，并给 token 记 last_used_at / request_count
```

## 部署（systemd 双实例，IPv6 双栈）

```bash
cd /opt/aam-panel
python3 -m venv venv && venv/bin/pip install -r backend/requirements.txt   # httpx[socks] fastapi uvicorn
cd frontend && npm install --registry=https://registry.npmmirror.com && npm run build   # 产物 → backend/static
cat > /etc/systemd/system/aam-panel-v4.service <<'EOF'
[Unit]
Description=AAM Panel IPv4
[Service]
Type=simple
WorkingDirectory=/opt/aam-panel
ExecStart=/opt/aam-panel/venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8710
Restart=always
[Install]
WantedBy=multi-user.target
EOF
# aam-panel-v6.service 同结构，--host :: --port 8710（IPv6 公网访问）
systemctl daemon-reload && systemctl enable --now aam-panel-v4 aam-panel-v6
```

关键坑：
- **uvicorn --host :: 是 v6-only**（即使 sysctl bindv6only=0），127.0.0.1 连不上 → 必须双实例（v4 + v6 同端口可共存，不同地址族）
- SQLite 双进程并发 → db.py connect() 已加 `PRAGMA journal_mode=WAL; busy_timeout=10000`
- 部署/改代码后旧进程可能占着端口 → 新代码"看起来不生效"（曾误判为空内容 bug）：先 `ss -tlnp | grep 8710` 确认 PID
- 前端改动 → `npm run build`（vite base='./'，静态由后端 `app.mount("/", StaticFiles(html=True))` 托管，无需 nginx）

## Tabbit 适配器规格（platforms/tabbit.py）

平台无关参数：`base_url`（web.tabbit.com 或 web.tabbit.ai）、`proxy`（socks5h，国际版必填）、账号 cookie。

### 常量
- 签名密钥**不再硬编码常量**:运行时 `GET /chat/sign-key` 获取(按平台 key 进程内缓存 10 分钟),遇签名失效自动刷新并重试
- VERSION 默认 `1.1.39(10101039)`；`x-req-ctx` = base64(VERSION)

### 签名 headers（每次请求）
```
trace-id: uuid4
x-timestamp: str(int(time.time()*1000))
x-signature: uuid4
x-nonce: hmac_sha256_hex(key, f"{ts}.{sig}.{sha256_hex(body_str)}")   # GET 时 body_str=""
unique-uuid: 32-hex UUID，idx5='1'（Pro 自证），idx12='4'，idx16∈[8,9,a,b]，
             时间戳编码位 [2,7,11,14,18,21,25,28]（ts = 秒级 hex 后 8 位）
Cookie: <account.credential>
Accept: application/json 或 text/event-stream
```

### 端点
| 用途 | 请求 |
|---|---|
| 账号验证/用户信息 | GET `/api/v0/user/base-info` → `{success,user_info:{id,display_name,secret_mobile,...}}` |
| 配额/积分 | GET `/api/commerce/quota/v1/usage` → `{member_level,usage_percentage:"3.36%",remaining_reset_hours,current_cycle_start/end,membership_plan_details:[...]}` |
| 模型列表 | GET `/proxy/v1/model_config/models?a=0&scene=chat`（带签名）→ `{models:[{display_name,model_key,model_access_type,...}]}` |
| 会话列表 | POST `/newtab`，headers: `accept: text/x-component`, `content-type: text/plain;charset=UTF-8`, `next-action: 607f3555ebab54eceed6d8c97b0ef64a9badccbb3b`, `next-router-state-tree: %5B%22%22%2C%7B%22children%22%3A%5B%22newtab%22%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%2Ctrue%5D`，body `["$undefined",{"page":1,"size":20}]` → RSC 文本，提取 `chat_session_id` UUID |
| 聊天 | POST `/api/v1/chat/completion`（SSE） |
| 签名 key（499 时） | GET `/chat/sign-key`（返回纯文本 key） |

### 聊天 body（必须严格遵守，否则模型被拒/切走）
```json
{"chat_session_id":"<真实uuid>","message_id":null,"content":"<用户文本>",
 "selected_model":"<display_name>","parallel_group_id":null,"task_name":"chat",
 "agent_mode":false,"metadatas":{"html_content":"<p>文本</p>"},"references":[],
 "entity":{"key":"d41d8cd98f00b204e9800998ecf8427e","extras":{"type":"tab","url":""}}}
```
- `task_name` 必须小写 `chat`；`selected_model` 必须 display_name（mdl_xxx 会被切到隐藏模型）
- 会话 ID：优先复用账号下会话列表第一个（缓存 5 分钟）；无会话则 POST /newtab 拉；仍无 → 错误提示"先在客户端建一个对话"（或后续实现新建会话）
- SSE 事件：`ready/message_start/thinking/message_chunk/message_finish/finish/close/error/switch_model/usage`
  - 文本增量 = `message_chunk.data.content`；`thinking.data.reasoning_content` 可忽略或转 reasoning
  - `error.data.message` + `code`（492=需 Pro，493=需设默认浏览器/升级）

### 多轮对话
Tabbit 是会话制，但网关无状态：把 messages 拼成带角色标注的文本（`[User]\n...\n\n[Assistant]\n...`）作为单条 content 发送（同 tabbit-toy 做法）。

## 自动化任务(进程内调度)

`backend/scheduler.py`,随 FastAPI lifespan 启动。v4/v6 双实例都会启动调度器,用 `settings.auto_check_last_date` 原子抢占,保证一天只真跑一次。

- 触发:`settings.daily_auto_check != 'off'` 时,每天 **08:00**(本机时区)检测全部 `enabled=1` 账号的状态与积分(并发 4,单账号失败不影响其它);
- 记录:`settings.auto_check_last_at` / `auto_check_next_at` / `auto_check_summary`(JSON:`total/active/expired/error/unknown/pushed`);
- 推送:`settings.notify_webhook` 非空时 POST `{"type":"aam_auto_check","text":"...","summary":{...}}`;留空则只在面板记录,不推送;
- 手动触发:`POST /api/auto-check/run`(跳过当日去重,立刻跑一轮并返回汇总);
- 关闭:`daily_auto_check=off`(跳过当天),或环境变量 `AAM_DISABLE_SCHEDULER=1`(测试隔离用);
- 与 Trae 签到(crontab 08:05)互不依赖,各自独立。

## 前端页面(Vue3 + Element Plus,8 个视图)

1. **Dashboard 总览**：KPI 卡（账号总数/活跃/今日请求/错误率）+ 平台横条（每平台账号数、平均用量进度条）+ 最近请求表
2. **Accounts 账号**:核心页。筛选(平台/状态/搜索)+ 账号表格或卡片:备注名、平台徽标、状态 pill(有效/过期/错误/未检查)、会员等级、积分进度条(usage_pct)、最后检查时间、操作(测活、刷积分、看模型、编辑、删除);表头/行复选框支持全选与半选,选中后出现批量条(批量检测 / 批量删除,删除二次确认);新增/编辑弹窗「凭据说明」页签按平台 adapter 给出该平台可用的取值步骤
3. **Platforms 平台**:内置平台卡片(可禁用)+ 添加自定义平台(key/name/adapter/base_url/proxy)
4. **Gateway 网关**:显示统一入口 base_url + key(可改)+ 复制按钮 + curl 示例 + 模型列表(带前缀)+ 请求统计图
5. **Settings 设置**:面板管理密钥、网关密钥、每日自动检测开关、检测汇总 Webhook、(上次/下次)自动检测时间、立即检测一次、清理日志
6. **Tokens 密钥 / DailyTasks 每日任务 / Requests 请求日志**:密钥绑定平台、自动任务与调度状态、请求明细

交互要求（硬性）：
- 所有操作真实调后端 API，禁止空壳按钮/纯前端假数据
- 状态必须不只靠颜色区分（文字+图标）
- 添加账号后自动测活并显示结果
- 危险操作（删除）二次确认
- 空状态（无账号/无平台）有引导文案

## 设计方向（UI 子代理二次发挥，但必须满足）
- 桌面优先（1440px），同时 768px 可用；深色为默认主题，浅色可选
- 平台徽标用色：国内版橙红 #F97316 / 国际版蓝紫 #6366F1 / Trae 青 / WorkBuddy 绿
- 积分进度条分档：<50% 绿、50-80% 黄、>80% 红
- 禁止：大段纯文本堆砌、无意义渐变、emoji 当图标

## 验证标准（验收必跑）
1. `uvicorn backend.main:app --port 8710` 启动成功
2. `curl /api/overview` 200
3. 用真实国内版 cookie 新增账号 → status=active、quota_pct≈3.36、member_level=standard
4. `GET /v1/models` 返回带前缀模型清单
5. `POST /v1/chat/completions`（model=`tabbit-domestic/GLM-5.1`）真实返回内容（流式+非流式）
6. 前端 `npm run build` 成功，浏览器打开 8710 各页面无 console error，表单一键可用
