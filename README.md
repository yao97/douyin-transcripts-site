# 抖音逐字稿库

13 位抖音博主 · **1235 篇**逐字稿 · 约 **800 万字**，全部由本地 Whisper + LLM 流水线从视频音频转写生成。

每篇包含：内容总结（核心主旨 / 核心干货要点 / 内容整体逻辑）+ 完整逐字稿 + 封面图 + 关键词标签。

## 在线浏览

**workbuddy 发布**：https://douyin-transcripts.app.workbuddy.host/

**GitHub Pages**：https://yao97.github.io/douyin-transcripts-site/ （需先按下方「启用 GitHub Pages」开启一次）

| 页面 | 说明 |
|---|---|
| `index.html` | 全部逐字稿，支持全文搜索（标题/摘要/逐字稿/主播/关键词）、按主播与关键词筛选、四种排序 |
| `authors.html` | 按主播浏览，13 位博主卡片含抖音主页直达 |
| `doc.html?id=<作者>/<文件名>` | 单篇阅读：封面、总结、逐字稿、md 原文下载、抖音原视频跳转、前后篇导航 |

## 主播

| 主播 | 抖音主页 |
|---|---|
| 巫师财经 | [@dy3zphvur7m9](https://www.douyin.com/user/dy3zphvur7m9) |
| 程前朋友圈 | [@3276187176547131](https://www.douyin.com/user/3276187176547131) |
| 阿库财经Finance | [主页](https://www.douyin.com/user/) |
| 罗永浩的十字路口 | [主页](https://www.douyin.com/user/) |
| 这很容易 | [主页](https://www.douyin.com/user/) |
| 识藏 | [主页](https://www.douyin.com/user/) |
| 罗天行 | [主页](https://www.douyin.com/user/) |
| 钦文和他的朋友们 | [主页](https://www.douyin.com/user/) |
| 魏远麟律师 广州 | [主页](https://www.douyin.com/user/) |
| 天爱Talk | [主页](https://www.douyin.com/user/) |
| 青年不惑 | [主页](https://www.douyin.com/user/) |
| AAA麟西 | [主页](https://www.douyin.com/user/) |
| 乡 愁 | [主页](https://www.douyin.com/user/) |

> 具体账号见 `authors.html` 页面（数据来自各篇 md 头部的「抖音账号」字段）。

## 目录结构

```
douyin-transcripts-site/
├── index.html              # 首页（列表 + 搜索 + 筛选）
├── authors.html            # 按主播浏览
├── doc.html                # 单篇阅读壳
├── data/
│   ├── index.json          # 索引 1.13MB —— 元数据 + 摘要首句，首屏只下这个
│   └── docs/<作者>/<id>.json  # 正文分片 ≈11KB/篇 —— summary + transcript，按需拉
├── transcripts/<作者>/*.md # 逐字稿原文（可直接下载）
├── assets/covers/<作者>/*.jpg  # 封面（已缩至宽 720px / JPEG q82）
├── build_site.py           # 构建脚本
└── .nojekyll               # 让 GitHub Pages 不过滤下划线目录
```

### 为什么拆成两层

GitHub Pages **不开启 gzip**（响应无 `Content-Encoding`），缓存也只有 `max-age=600`。
早期把所有正文塞进一个 `transcripts.json`（22.2MB），实测从 GitHub 拉完要 **141 秒**，
每次刷新都要重来一遍，站点基本不可用。

拆成「索引 + 分片」后：

| | 体积 | 实测耗时 |
|---|---|---|
| 首屏 `index.json` | 1.13 MB | **5 秒** |
| 单篇正文分片 | ≈11 KB | 0.9 秒 |

搜索也相应改成两层：标题/主播/关键词/摘要首句在索引里**即时过滤**；
正文走分片**串行懒加载**（每批 12 个），命中数边扫边加，标题栏显示「正文中…」。

## 数据来源与流水线

内容由本地流水线从抖音视频音频转写生成，不含任何音视频文件。

```
下载音频 (.m4a)
  → Whisper small 转写（ASR，8766 服务）
  → LLM 提炼三段式内容总结（Ollama / 本地模型）
  → 渲染 Markdown（头部元数据 + 总结 + 逐字稿）
  → build_site.py 压缩封面 + 生成静态站
```

流水线代码见 [yao97/douyin-content-pipeline](https://github.com/yao97/douyin-content-pipeline)。

## 本地重建

```bash
# 全量（压缩封面 + 复制 md + 生成页面）
python build_site.py

# 只重建页面（复用已压好的封面，几秒完成）
python build_site.py --pages

# 强制重压封面
python build_site.py --covers
```

依赖：`Pillow`。源数据默认读 `D:\视频\媒体知识库\博主`，见脚本顶部 `SRC_ROOT` / `OUT_ROOT`。

## 启用 GitHub Pages

部署由 `.github/workflows/pages.yml` 自动完成，**首次需要手动开启一次**：

1. 仓库 → **Settings** → 左侧 **Pages**
2. **Build and deployment → Source** 选 **GitHub Actions**（不是 `Deploy from a branch`）
3. 保存后无需再操作 —— 之后每次 push 到 `main` 会自动重新部署

也可以在 Actions 页面点 **Deploy to GitHub Pages → Run workflow** 手动触发首次部署。

> 若在开启 Source 之前就推送过，会看到 `Setup Pages` 步骤失败（Pages 尚未启用），
> 开启 Source 后重新 Run workflow 即可，与代码内容无关。

## 声明

逐字稿由公开视频音频自动转写生成，仅用于个人学习与内容研究。版权归原作者及平台所有。若权利人认为内容侵权，请提 issue 或联系删除。
