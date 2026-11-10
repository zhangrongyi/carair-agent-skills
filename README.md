# Car Air Agent Skills

面向 Codex 的两项汽车空调业务 Skill：`query-carair-products` 通过受保护的只读 API 查询商品、库存和缓存成交价；`carair-new-sku-research` 用商品查询、Lark Base 和公开来源研究客户提出的新配件，并写入一条 `信息收集` 记录供员工事后复核。

公开此仓库**不会授予内部数据访问权**。商品 API 需要单独发放的只读 Token；Lark 需要员工本人 OAuth、应用 API 权限和目标 Base 的访问权。首版支持 Codex、macOS 和原生 Windows；WSL/Linux 的安全凭据配置不在本版范围内。

## 复制给 Codex 的安装提示

```text
请阅读 https://github.com/zhangrongyi/carair-agent-skills 的 README，并用 $skill-installer 从该公共仓库的 query-carair-products 和 carair-new-sku-research 两个路径安装 Skill。先检查 Python 3.10+、Node.js 和 lark-cli；若未安装 lark-cli，按官方方式安装。然后按 README 引导我在本机完成 Lark 应用创建、OAuth 登录和产品 API Token 的隐藏输入，逐项验证 health、商品查询、whoami 和不写入的 inspect。不要索取或显示任何 Token、App Secret，也不要执行 apply 作为安装测试。
```

Codex Skill 安装器实际需要仓库名加两个**目录路径**，单独给仓库根 URL 不会自动确定安装路径。对应命令为：

```text
python3 <SKILL_INSTALLER_DIR>/scripts/install-skill-from-github.py --repo zhangrongyi/carair-agent-skills --path query-carair-products carair-new-sku-research
```

`<SKILL_INSTALLER_DIR>` 是 Codex 内置 `skill-installer` 的目录，由 Codex 自行定位。安装到 `$CODEX_HOME/skills`，未设置时是 `~/.codex/skills`。若目标目录已存在，安装器会停止；先确认旧版和凭据状态，再安排更新。安装后若 Skill 尚未出现，重启 Codex 或在下一轮对话使用。

## 三阶段安装

### 1. Lark CLI 与本人 OAuth

检查 Python 3.10+、Node.js 和 npm/npx。macOS 用 `python3 --version`，Windows PowerShell 用 `py -3 --version`；两者用 `node --version` 和 `npx --version`。按 [Lark CLI 官方说明](https://github.com/larksuite/cli#installation--quick-start)安装：

```text
npx @larksuite/cli@latest install
lark-cli --version
lark-cli config init --new
lark-cli auth login --scope "bitable:app"
lark-cli auth status
lark-cli whoami
```

每位员工为自己创建 Lark 应用，按浏览器提示完成设置与公司租户审批。应用仅开启 Base 的“查看、评论、编辑和管理”权限 `bitable:app`；这是写记录所需权限，`inspect` 单独使用时可采用只读权限。不要运行无参数 `auth login` 或 `--recommend`，它们可能请求所有业务域。CLI 登录要显示员工本人；工作流明确使用 `--as user`。管理员还必须给该员工及其应用开放两个目标 Base：同行目录可读、`开款2.0` 目标表可读写及上传附件。应用 Scope 与 Base ACL 两层都要满足；遇到授权错误，先核对 `auth status`、`whoami` 与资源权限。[Lark API 权限说明](https://open.larksuite.com/document/server-docs/getting-started/overview-of-app-scopes)

### 2. 产品查询 Skill 与只读 Token

按上面的 Codex 提示安装两项 Skill。管理员通过公司密码管理器向员工共享当前产品 API 的只读 Token；员工只在**本机交互终端**运行以下命令，提示输入时不会回显。不要把 Token 放到 GitHub、Codex 对话、命令参数、截图或 `.env` 文件。产品客户端优先读临时环境变量 `CAR_AIR_CODEX_API_TOKEN`，否则读系统凭据库；日常推荐凭据库。

macOS：

```bash
skill_root="${CODEX_HOME:-$HOME/.codex}/skills/query-carair-products"
python3 "$skill_root/scripts/query_products.py" configure-credential
python3 "$skill_root/scripts/query_products.py" health
python3 "$skill_root/scripts/query_products.py" search "Alza compressor" --limit 5
```

Windows 原生 PowerShell：

```powershell
$skillRoot = if ($env:CODEX_HOME) { Join-Path $env:CODEX_HOME 'skills\query-carair-products' } else { Join-Path $HOME '.codex\skills\query-carair-products' }
py -3 "$skillRoot\scripts\query_products.py" configure-credential
py -3 "$skillRoot\scripts\query_products.py" health
py -3 "$skillRoot\scripts\query_products.py" search "Alza compressor" --limit 5
```

`health` 应返回 `ok: true`、`environment: production` 和 `read_only: true`；若实际环境不是 production，应停下核对配置。Keychain 服务名是 `com.baijia.codex-readonly-api`，Windows Credential Manager 目标是 `com.baijia.codex-readonly-api:production`。

### 3. 开款 Skill 的只读验证

先确认 `lark-cli whoami` 是员工本人，再运行 `inspect`。它查询产品 API、现有开发记录和同行目录，**不会写入**。

macOS：

```bash
research_root="${CODEX_HOME:-$HOME/.codex}/skills/carair-new-sku-research"
python3 "$research_root/scripts/workflow.py" inspect --reference "729415" --model "CAM PLACER X VAN" --category "冷凝器"
```

Windows 原生 PowerShell：

```powershell
$researchRoot = if ($env:CODEX_HOME) { Join-Path $env:CODEX_HOME 'skills\carair-new-sku-research' } else { Join-Path $HOME '.codex\skills\carair-new-sku-research' }
py -3 "$researchRoot\scripts\workflow.py" inspect --reference "729415" --model "CAM PLACER X VAN" --category "冷凝器"
```

`ok: true` 且包含 `product_queries`、`development_records_checked` 和 `peer_sources` 才算通过。随后可在 Codex 中使用 `$query-carair-products` 查询商品，或提供客户配件资料并调用 `$carair-new-sku-research`。后者完成证据检查后会写入一条信息收集记录和产品图片，返回链接供人工复核；不会据此确认适配或推进采购。

## 常见故障

| 现象 | 处理 |
| --- | --- |
| 安装器提示目录已存在 | 核对已装版本；按团队更新流程备份并替换 Skill 目录，不要覆盖凭据库。 |
| `lark-cli is not installed` | 按官方安装 CLI，重开终端检查 `lark-cli --version`。 |
| Lark 授权或资源拒绝 | 核对 `auth status`、`whoami`、应用的 `bitable:app`、租户审批及两个 Base 的 ACL。 |
| `API token is not configured` 或 401 | 在本机重新运行 `configure-credential`；由管理员核对共享 Token，勿发送到对话。 |
| 429 | 等待限流恢复；共享 Token 的所有员工可能共用额度。 |
| `inspect` 商品查询失败 | 先排除产品 API 故障；不要改用数据库、SSH 或管理员接口绕过。 |
| `apply` 报告已写入记录但上传或回读失败 | 先打开返回的记录 ID 检查，确认后再决定如何修复，避免重复创建。 |

## 仓库内容与权限

- [`query-carair-products`](query-carair-products/SKILL.md)：只读商品 API；不直接连数据库。
- [`carair-new-sku-research`](carair-new-sku-research/SKILL.md)：内部查重、市场研究、单条 Base 记录及图片上传。
- [`docs/ADMIN.md`](docs/ADMIN.md)：管理员分发、授权与轮换说明。

两个脚本保留现有生产 API/Base 地址作为默认值；`CAR_AIR_API_BASE_URL`、`CARAIR_DEVELOPMENT_BASE_URL`、`CARAIR_PEERS_BASE_URL` 可在本机覆盖。地址和表 ID 不是凭据，仍需上述授权才能访问。客户图片、聊天、草稿 JSON、CLI 输出和任何凭据都不得提交到本仓库。

本仓库采用 [MIT License](LICENSE)。
