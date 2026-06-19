# Spec: Publish

## Purpose

将生成的音频/视频通过 cloudflared 隧道公开访问，同时保留本地副本。

## Contract

### `publish(media_path: str) -> MediaOutput`

- **Input**: 本地文件或目录路径
- **Output**: MediaOutput with public_url populated
- **Process**:
  1. 启动 Python HTTP server 服务该目录
  2. 启动 cloudflared 隧道端口转发
  3. 验证 URL 可达（HEAD 请求）
  4. 返回 public_url

### `serve_dir(dir_path: str) -> str`

- 服务整个目录（用于试听页等多文件场景）
- 返回 public base URL

### Tunnel Management

- 复用现有隧道（检测 8899 端口是否已被转发）
- 隧道进程管理：启动/停止/状态查询
- 超时：自动 24h 后断开

## Boundary Cases

- cloudflared 未安装 → 抛 PublishError + 安装提示
- 端口冲突 → 递增端口号重试
- 网络不可达 → 仅保存本地文件，public_url = None
- 空目录 → 拒绝服务
