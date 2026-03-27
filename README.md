# 音乐专辑多功能爬虫ß

从多个音乐数据库搜索专辑，保存到本地，自动上传到豆瓣。

## 安装

```bash
pip install -r requirements.txt
playwright install chromium
```

## 快速开始

### 一行命令完成所有操作（推荐）

```bash
./workflow.sh full "专辑名"
```

示例：搜索并添加 **Immanuel Wilkins Quartet: Live at the Village Vanguard**

```bash
./workflow.sh full "Immanuel Wilkins Village Vanguard"
```

交互流程：
1. 自动搜索 MusicBrainz 和 Apple Music
2. 显示结果列表，输入编号选择
3. 自动获取曲目列表和封面
4. 保存后询问是否上传豆瓣

### 单独命令

```bash
# 登录豆瓣（首次使用）
./workflow.sh login

# 搜索专辑
./workflow.sh search "专辑名"

# 添加专辑
./workflow.sh add "https://music.apple.com/cn/album/..."

# 列出本地专辑
./workflow.sh list

# 查看专辑详情
./workflow.sh show xmahll

# 上传到豆瓣
./workflow.sh upload xmahll

# 清空所有数据
./workflow.sh clear

# 检查环境
./workflow.sh check
```

## 工作流脚本命令

| 命令 | 说明 |
|------|------|
| `full <关键词>` | 交互式搜索 → 选择 → 添加 → 上传 |
| `search <关键词>` | 搜索专辑 |
| `add <URL>` | 添加专辑 |
| `list` | 列出本地专辑 |
| `show <ID>` | 显示专辑详情 |
| `upload <ID>` | 上传到豆瓣 |
| `clear` | 清空所有数据 |
| `login` | 登录豆瓣 |
| `check` | 检查环境配置 |

## 数据源

| 数据源 | 说明 | 备注 |
|--------|------|------|
| MusicBrainz | 免费开源，数据全面 | **无需配置** |
| Apple Music | 封面丰富 | **无需配置** |
| Discogs | 信息详细 | 需要 API Key |
| Spotify | 曲目全面 | 需要 API Key |

## 配置 API（可选）

编辑 `config.yaml`：

```yaml
# Spotify
scrapers:
  spotify:
    client_id: "your_client_id"
    client_secret: "your_client_secret"

# Discogs
  discogs:
    api_key: "your_api_key"
```

获取 API Keys:
- Spotify: https://developer.spotify.com/dashboard
- Discogs: https://www.discogs.com/settings/developers

## 数据存储

```
data/
├── albums/       # 专辑 JSON 文件
├── images/       # 封面图片
└── cookies/      # 登录状态
```
