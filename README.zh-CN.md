# VPS DueGuard

[English](README.md) | [简体中文](README.zh-CN.md)

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Debian%20%7C%20Ubuntu-30A3DC?style=for-the-badge&logo=linux&logoColor=white)](#快速开始)
[![Telegram](https://img.shields.io/badge/Telegram-Bot%20Ready-26A5E4?style=for-the-badge&logo=telegram&logoColor=white)](#telegram-bot)
[![WHMCS](https://img.shields.io/static/v1?label=Panel&message=WHMCS%20%7C%20Lagom-like&color=0F766E&style=for-the-badge)](#兼容性说明)
[![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE)

VPS DueGuard 是一个用于监控多个 WHMCS/Lagom 类 VPS 商户面板的小工具，支持查看有效服务、续费日期、流量使用情况，并通过 Telegram 发送续费提醒、每日报告和 Bot 查询结果。

这个项目适合同时使用多个 VPS 商户的小型服务器用户：它比完整监控系统更轻，比手动登录每个服务商面板更方便。

## 为什么需要 VPS DueGuard

很多低价 VPS 服务商使用相似的 WHMCS/Lagom 客户区模板。你需要的数据通常都在面板里，但分散在不同账号和不同服务商页面中。

VPS DueGuard 专注于这个具体场景：

- 一次添加多个服务商
- 尽量复用登录会话
- 从全部服务商查询有效 VPS
- 在一个输出里查看续费和流量信息
- 在续费前收到 Telegram 提醒
- 随时通过 Telegram Bot 查询最新汇总

## 法律与负责任使用

VPS DueGuard 仅用于监控你本人拥有或已获得明确授权管理的 VPS 账号。使用者应自行确认本工具的使用方式符合各服务商的服务条款。

本项目不会、也不应被用于绕过验证码、二次验证、访问控制、限速或反自动化机制。不得将本工具用于未获授权的账号、系统或服务商面板。

WHMCS、Lagom、Telegram、Python 以及本文中提到的服务或品牌名称归其各自权利人所有。本项目为独立开源项目，与上述服务、品牌或服务商不存在关联、授权、赞助、认可或官方支持关系。

本软件按 MIT License 以“原样”提供。因不当使用导致的账号限制、服务商政策违规、数据丢失、服务中断或其他后果，由使用者自行承担。

## 功能

| 功能 | 说明 |
| --- | --- |
| 多商户统一资产 | 跨多个 WHMCS/Lagom 类服务商列出有效 VPS |
| 只显示有效服务 | 过滤已取消、已终止等非活跃服务 |
| 流量信息汇总 | 在面板公开相关信息时显示已用/总量和剩余流量 |
| 续费提醒 | 在配置的续费提醒窗口内发送 Telegram 提醒 |
| 每日报告 | 每日发送有效 VPS 的 Telegram 汇总 |
| Telegram Bot 查询 | 通过 Telegram 查询汇总、流量、续费或单个服务商 |
| Cookie 会话缓存 | 复用服务商登录 Cookie，减少重复登录并加快查询 |
| 菜单式 Linux 部署 | 通过一个菜单完成安装、配置、测试、服务管理、日志和卸载 |
| 干净卸载 | 删除项目专属程序文件、运行时、systemd units、Cookie、状态和快捷命令 |

## 兼容性说明

VPS DueGuard 面向 WHMCS/Lagom 类客户区面板，但实际兼容性取决于各服务商的页面结构、登录流程、账号安全设置和服务条款。

本文中的兼容性说明仅作为信息参考，不代表与任何服务商或平台存在关联、授权、认可、赞助或官方支持关系。

很多使用相似客户区的服务商，可以通过在 `config.yaml` 中添加 URL 和账号信息来尝试接入。使用前请自行确认服务商是否允许自动化登录、页面解析、Cookie 会话复用和通知集成。

## 支持的面板范围

VPS DueGuard 当前主要面向 WHMCS/Lagom 类客户区。

已支持的行为：

- 用户名和密码登录
- 尽量使用英文客户区页面
- 服务列表解析
- 服务详情页解析
- 续费日期提取
- 在页面可见时提取流量使用和剩余流量
- 检测常见阻断，例如验证码、2FA 和登录失败页面

本项目只检测常见阻断，不会绕过这些机制。请勿将其用于绕过验证码、二次验证、访问控制、限速、反自动化检查或服务商限制。

如果某个面板没有公开流量信息，该服务仍会保留在结果中，流量字段显示为 `unknown`。

## 快速开始

在 Debian 或 Ubuntu 上执行：

```bash
git clone https://github.com/xing-xing-coder/vps-dueguard.git
cd vps-dueguard
sudo bash vpsm.sh
```

脚本会打开双语菜单。选择语言后，按步骤安装程序、添加服务商、测试查询、配置 Telegram 并启用服务。

安装完成后，随时打开菜单：

```bash
vpsm
```

对于常规 Linux 部署，`vpsm` 是主要入口。日常使用不需要记 Python 命令。

## 菜单概览

```text
VPS DueGuard 设置

1. 安装 / 更新 VPS DueGuard
2. 服务商管理
3. Telegram 和提醒管理
4. 查询和测试
5. systemd 服务管理
6. 查看日志
7. 完整卸载
8. 退出
```

菜单支持：

- 安装或更新 VPS DueGuard
- 添加、查看或重写服务商配置
- 测试全部服务商或单个服务商
- 配置 Telegram Bot Token 和 Chat ID
- 配置续费提醒天数
- 发送 Telegram 测试消息
- 发送一次每日报告
- 执行一次续费提醒检查
- 启动、停止、重启和查看 Telegram Bot 服务
- 启用或禁用日报和续费提醒定时器
- 查看最近的 systemd 日志
- 卸载全部项目专属文件

## 服务商配置

Linux 菜单会写入：

```text
/opt/vps-dueguard/config.yaml
```

示例：

```yaml
providers:
  - name: provider-a
    base_url: https://example-provider-a.com/
    username: your@email.com
    password: your-password

  - name: provider-b
    base_url: https://example-provider-b.com/
    username: your@email.com
    password: your-password
```

服务商名称会自动转为小写。之后可以从菜单查询单个服务商，也可以通过 Telegram 指令 `/provider provider-a` 查询。

## Telegram Bot

在菜单中添加 Bot Token 和 Chat ID：

```yaml
telegram:
  bot_token: "123456:your-bot-token"
  chat_id: "123456789"
```

只有配置中的 `chat_id` 可以查询 VPS 信息。

可用指令：

| 指令 | 说明 |
| --- | --- |
| `/summary` | 显示全部有效 VPS、续费日期和流量 |
| `/traffic` | 显示流量使用和剩余流量 |
| `/renewals` | 显示续费日期和剩余天数 |
| `/provider provider-a` | 查询单个已配置服务商 |
| `/refresh` | 强制重新查询并刷新 5 分钟缓存 |
| `/help` | 显示指令帮助 |

Bot 会在 `config.yaml` 变化时重新加载配置。如果你在菜单中修改了服务商配置，发送 `/refresh` 后 Bot 会使用最新配置。

## 续费提醒

默认提醒天数：

```text
21,14,7,3
```

菜单只接受英文逗号分隔数字，例如：

```text
21,14,7,3
```

提醒窗口是包含式判断。例如配置了 `30` 天，而某台 VPS 还剩 `21` 天到期，`30` 天提醒窗口可以触发一次。

重复提醒通过本地状态文件避免：

```text
/opt/vps-dueguard/.vps_dueguard_state.json
```

去重键包含服务商、服务名、续费日期和提醒阈值。

## Cookie 会话

默认启用 Cookie 会话缓存：

```yaml
sessions:
  enabled: true
  session_dir: ".vps_sessions"
```

每个服务商都有独立 Cookie 文件。工具会先尝试使用缓存 Cookie；如果会话失效，会重新登录并更新 Cookie。

这样可以减少重复登录，并让第一次查询后的 Telegram 查询更快。

## Linux 安装细节

安装脚本使用项目专属路径：

| 内容 | 路径 |
| --- | --- |
| 程序目录 | `/opt/vps-dueguard` |
| Python 虚拟环境 | `/opt/vps-dueguard/.venv` |
| 独立 Python 运行时 | `/opt/vps-dueguard-runtime` |
| 快捷命令 | `/usr/local/bin/vpsm` |
| 配置文件 | `/opt/vps-dueguard/config.yaml` |
| Cookie 会话 | `/opt/vps-dueguard/.vps_sessions` |
| 提醒状态 | `/opt/vps-dueguard/.vps_dueguard_state.json` |

如果服务器只有 Python 3.7 这类旧版本，安装脚本会通过 `uv` 在 `/opt/vps-dueguard-runtime` 下安装独立 Python 3.11。安装时出现 `/root/.local/bin` 不在 `PATH` 的提示通常可以忽略，因为脚本使用绝对路径调用独立 Python 运行时。

## systemd 服务和定时器

安装脚本会创建：

| Unit | 用途 |
| --- | --- |
| `vps-dueguard-bot.service` | 运行 Telegram 长轮询 Bot |
| `vps-dueguard-daily.timer` | 运行每日 Telegram 报告 |
| `vps-dueguard-renewals.timer` | 运行续费提醒检查 |

可以从菜单管理，也可以手动执行：

```bash
sudo systemctl restart vps-dueguard-bot.service
sudo systemctl status vps-dueguard-bot.service
sudo systemctl list-timers 'vps-dueguard-*'
```

查看日志：

```bash
sudo journalctl -u vps-dueguard-bot.service -n 100 --no-pager
sudo journalctl -u vps-dueguard-daily.service -n 100 --no-pager
sudo journalctl -u vps-dueguard-renewals.service -n 100 --no-pager
```

## 卸载

打开菜单：

```bash
vpsm
```

选择 **完整卸载**。

卸载流程使用两次空回车确认。任意一次输入非空内容都会取消卸载。

卸载会删除：

- `/opt/vps-dueguard`
- `/opt/vps-dueguard-runtime`
- `/usr/local/bin/vpsm`
- 所有 `vps-dueguard-*` systemd units
- 配置文件
- 服务商 Cookie
- 提醒状态
- 原始 clone 源码目录，前提是检测到项目安全标记

卸载不会删除共享系统包，例如 `curl`、`wget`、`rsync` 或系统 Python。也不会删除 `/root/.config/uv`、`/root/.cache/uv` 这类用户级 uv 缓存或配置，因为它们可能被其他项目使用。

## 本地开发

Windows PowerShell：

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
python -m pytest
```

Linux：

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
python -m pytest
```

开发和调试时可以直接使用 Python 命令：

```bash
python -m vps_dueguard list
python -m vps_dueguard list --provider provider-a
python -m vps_dueguard list --json
python -m vps_dueguard notify test
python -m vps_dueguard notify daily
python -m vps_dueguard notify renewals
python -m vps_dueguard bot
```

## 故障排查

### Telegram 返回 `No providers configured`

打开菜单：

```bash
vpsm
```

进入服务商管理，至少添加一个服务商，测试查询，然后在 Telegram 中发送 `/refresh`。

### Telegram 返回没有有效服务

可能原因：

- 服务商账号下没有有效 VPS
- 服务商面板 HTML 结构发生变化
- 登录失败
- 验证码或 2FA 阻止登录
- Cookie 过期后重新登录失败
- 服务商 URL、用户名或密码不正确

从菜单运行服务商测试并查看日志：

```bash
sudo journalctl -u vps-dueguard-bot.service -n 100 --no-pager
```

### 查询很慢

第一次查询可能较慢，因为需要登录每个服务商并读取服务详情页。后续查询会使用 Cookie 和 Telegram Bot 5 分钟缓存，通常会更快。

只有需要新数据时再使用 `/refresh`。

## 隐私与安全

- `config.yaml` 会明文保存服务商密码和 Telegram Token。
- `config.yaml`、Cookie 会话、状态文件、缓存和虚拟环境都会被 git 忽略。
- Linux 菜单会以 `600` 权限写入 `config.yaml`。
- 如果配置文件、Cookie、截图、日志或 Telegram Bot 输出包含账号、Token、服务、续费、流量或 URL 细节，请不要公开发布到 Issue。
- Telegram Bot 只响应配置中的 `chat_id`。
- 卸载脚本删除 clone 源码目录前，会检查项目标记和高风险路径。
- 安全问题建议私下报告，见 [SECURITY.md](SECURITY.md)。

## 项目结构

```text
vps_dueguard/
  client.py          # 登录、会话缓存、服务商抓取
  parser.py          # WHMCS/Lagom 页面解析
  notifications.py   # Telegram、报告、提醒、Bot 指令
  menu_config.py     # vpsm.sh 使用的安全 YAML 读写工具
  cli.py             # Typer CLI
tests/               # parser、config、session、notification 测试
vpsm.sh              # Linux 菜单安装和管理脚本
config.example.yaml  # 配置示例
```

## License

本项目使用 [MIT License](LICENSE)。

直接第三方依赖及许可证说明见 [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md)。
