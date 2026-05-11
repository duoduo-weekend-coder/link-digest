# 小红书视频支持设计

Date: 2026-05-10

## 目标

为小红书链接加入视频检测和音频转录能力。图文帖走现有文本抓取，视频帖走 yt-dlp 下载 + Groq Whisper 转录，支持可选 cookie 认证。

## 架构

只改两个文件：`extractors/xiaohongshu.py` 和 `app.py`。

### extractors/xiaohongshu.py

新增 `on_chunk` 参数，内部逻辑分两路：

```
extract_xiaohongshu(url, on_chunk=None)
  ├─ HTTP GET 页面，检测 og:video / <video> tag
  ├─ 是视频？
  │   ├─ _download_audio(url, workdir)                      # 无 cookie
  │   ├─ 失败 + XHS_COOKIES 存在？
  │   │   └─ _download_audio(url, workdir, cookies_file)    # 写 tmpfile 再试
  │   ├─ 还失败？→ fallback 文本抓取
  │   └─ 成功 → _transcribe_file(path, on_chunk) → 返回 transcript
  └─ 不是视频 → 走现有文本抓取逻辑
```

从 `audio.py` import `_download_audio` 和 `_transcribe_file`。接受这个轻度耦合，因为逻辑天然属于 audio 层。

现有纯文本抓取逻辑提取为内部函数 `_extract_text(url) -> dict`，供视频 fallback 和图文帖共用。

### Cookie 机制

```
XHS_COOKIES env var（Netscape cookie 格式字符串）
  └─ 写入 tempfile
      └─ yt-dlp --cookies <path>
          └─ with 块结束自动删除
```

无 `XHS_COOKIES` 时不写文件，直接走无认证下载。

### app.py

小红书分支从简单的 `asyncio.to_thread` 改为和 YouTube audio fallback 相同的 SSE + queue 模式：

```python
elif source_type == "xiaohongshu":
    loop = asyncio.get_running_loop()
    q: asyncio.Queue = asyncio.Queue()
    def _cb_xhs(idx, total, text, _q=q, _loop=loop):
        _loop.call_soon_threadsafe(_q.put_nowait, {"chunk_index": idx, "total": total, "text": text})
    task = asyncio.create_task(_run_extract_xiaohongshu(url, _cb_xhs, q))
    async for chunk_data in _drain_until_none(q):
        yield _sse("transcript_chunk", chunk_data)
    extracted = await task
```

图文帖 `on_chunk` 不会被调用，queue 只收到 sentinel，SSE 静默。

## 数据流

```
URL → detect_source_type → "xiaohongshu"
  → extract_xiaohongshu(url, on_chunk)
      → HTTP GET → 视频检测
      → [视频] yt-dlp → Groq Whisper → transcript
      → [图文] 文本抓取 → transcript
  → summarize_text → SSE result
```

返回结构与现有 extractor 一致：`{ok, source_type, title, transcript, notes, total_chunks?}`，`source_type` 始终为 `"xiaohongshu"`。

## Notes 字段约定

| 场景 | note |
|------|------|
| yt-dlp 成功（无 cookie） | `"Downloaded video audio with yt-dlp (no cookie)."` |
| yt-dlp 成功（有 cookie） | `"Downloaded video audio with yt-dlp (XHS_COOKIES used)."` |
| yt-dlp 失败，fallback 文本 | `"yt-dlp failed, fell back to text extraction."` |
| 图文帖文本抓取 | `"Best-effort public-page text extraction only."` |

## 错误处理

- 第一次 yt-dlp 失败：若 `XHS_COOKIES` 存在则重试，否则直接 fallback 文本
- 第二次 yt-dlp 仍失败：fallback 文本，note 说明原因
- 文本 fallback 也无内容：返回 `ok=False`，`app.py` 走现有 error SSE 路径

## 测试

新建 `tests/test_xiaohongshu.py`，三个 case：

1. **视频帖 + yt-dlp 成功（无 cookie）**
   - mock HTTP 返回含 `og:video` 的 HTML
   - mock `_download_audio` 成功、`_transcribe_file` 返回文本
   - 断言 `ok=True`、`source_type="xiaohongshu"`、transcript 非空、notes 含 "no cookie"

2. **视频帖 + 无 cookie 失败 + XHS_COOKIES 重试成功**
   - 第一次 `_download_audio` 抛 `subprocess.CalledProcessError`
   - 设置 `XHS_COOKIES` env var，第二次成功
   - 断言 `_download_audio` 被调用两次，notes 含 "XHS_COOKIES used"

3. **图文帖（无视频 tag）**
   - mock HTML 无 `og:video` 无 `<video>`
   - 断言 `_download_audio` 从未调用
   - 断言走文本抓取路径，`ok=True`

更新 `test_app.py` 中小红书相关集成测试，加 `on_chunk=None` 参数。

## 环境变量

| 变量 | 说明 | 必填 |
|------|------|------|
| `XHS_COOKIES` | Netscape 格式 cookie 字符串 | 否（无则仅尝试无认证下载） |

## 不在本次范围内

- 小红书短链（`xhslink.com`）的展开（router 已处理 domain 匹配，yt-dlp 会自动跟随重定向）
- 直播流支持
- Cookie 自动刷新
