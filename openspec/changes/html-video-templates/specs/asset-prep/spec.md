# Spec: Asset Offline Preparation

## Purpose

html-video 模板大量引用 Google Fonts (`fonts.googleapis.com`) 和 GSAP CDN (`cdn.jsdelivr.net`)。这些外部资源在中国网络环境下会超时，必须在渲染前离线化为本地资源。

## Contract

1. 预处理脚本将模板中所有外部 CSS/JS/字体引用替换为本地路径
2. 离线化后的模板在无网络环境下可正常渲染（Playwright 无外网请求）
3. 脚本幂等 — 重复运行不会重复下载
4. 下载失败不阻断 — 该资源回退到系统字体栈

## Details

### 脚本: `scripts/offline_html_video_assets.sh`

```bash
#!/bin/bash
# 扫描 /tmp/html-video/templates/ 下所有 index.html
# 对每个模板:
#   1. 提取 Google Fonts URL → 下载 CSS → 解析 @font-face → 下载 .woff2
#   2. 提取 GSAP CDN URL → 下载 .js
#   3. 替换 HTML 中 CDN URL → 本地相对路径
#   4. 写入 TEMPLATE_DIR/{name}/index.html
```

### 目标模板目录

将处理后的模板输出到 MediaForge 可访问的路径：
```
/tmp/html-video/templates/   →   /tmp/mediaforge-html-templates/
                                   ├── warm-grain/index.html
                                   ├── swiss-grid/index.html
                                   └── kinetic-type/index.html
```

### 资源映射

| 原始 URL | 本地路径 |
|---|---|
| `https://fonts.googleapis.com/css2?family=...` | `assets/fonts/{family}.css` |
| `https://fonts.gstatic.com/s/...` | `assets/fonts/{family}.woff2` |
| `https://cdn.jsdelivr.net/npm/gsap@3.14.2/...` | `assets/js/gsap.min.js` |

### 引擎端常量

```python
# html_video_templates.py
TEMPLATE_DIR = "/tmp/mediaforge-html-templates"
```

## Boundary Cases

| 场景 | 行为 |
|---|---|
| Google Fonts 下载超时 | 该字体跳过，CSS 中移除对应 `@font-face`，用系统字体栈 |
| GSAP 下载失败 | 报错退出（GSAP 是动画核心依赖，不可缺） |
| 模板已离线化过 | 跳过（检查本地文件存在） |
| 模板 HTML 中无外部资源 | 原样复制 |
| 模板不在首批 3 套中 | 跳过（仅处理 warm-grain/swiss-grid/kinetic-type） |
