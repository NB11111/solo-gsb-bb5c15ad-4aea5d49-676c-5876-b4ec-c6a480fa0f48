# Archive Quote Alignment API

档案引文定位服务：给定原文与一组有序引文，返回每条引文在原文中的字符起止偏移。

## 启动

```bash
docker compose up --build
```

服务地址：**http://localhost:8000**（端口 **8000**）

- 健康检查：`GET http://localhost:8000/health`
- 交互式文档：`http://localhost:8000/docs`

## API

### `POST /quotes/align`

请求体：

```json
{
  "text": "Archive  text\nwith repeats. Archive text.",
  "quotes": ["Archive text", "repeats", "Archive text", "absent"]
}
```

响应（`results` 与 `quotes` 一一对应，无法定位的引文为 `null`）：

```json
{
  "results": [
    {"start": 0, "end": 13},
    {"start": 19, "end": 26},
    {"start": 28, "end": 40},
    null
  ]
}
```

`start` / `end` 为**原始文本**的字符偏移（`end` 为开区间），可直接用于 `text[start:end]` 切片。

### `GET /health`

返回 `{"status": "ok"}`。

## 匹配规则

- **空白折叠**：匹配时将原文与引文中的连续空白（空格、换行、制表符等）视为单个空格；返回的偏移始终指向原始文本的原始字符。
- **重复引文**：同一引文出现多次时，各次匹配互不重叠，且保持引文数组的顺序。
- **联合选择**：从各引文的候选位置中整体选出一组互不重叠、保持数组顺序的定位，目标依次为：
  1. 最大化成功定位的引文条数；
  2. 最小化已定位片段之间跳过的原文字符总数（首段之前、末段之后不计）；
  3. 仍并列时取偏移序列字典序最小的一组。
- 空引文或纯空白引文视为无法定位，返回 `null`。

## 本地开发（可选）

```bash
python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/uvicorn app.main:app --reload --port 8000
.venv/bin/pytest            # 运行测试
```

## 项目结构

```
app/
  align.py   # 归一化、候选生成与联合选择（动态规划）
  main.py    # FastAPI 路由与请求/响应模型
tests/       # pytest 测试
Dockerfile
docker-compose.yml
```
