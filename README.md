# Archive Quote Alignment API

档案引文定位服务：给定原文与一组有序引文，返回每条引文在原文中的字符起止偏移。
提供精确匹配（`/quotes/align`）与容错模糊匹配（`/quotes/align-fuzzy`）两个接口。

## 启动

```bash
docker compose up --build
```

服务地址：**http://localhost:8000**（端口 **8000**），新旧接口均通过该端口访问：

- 精确匹配：`POST http://localhost:8000/quotes/align`
- 模糊匹配：`POST http://localhost:8000/quotes/align-fuzzy`
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

### `POST /quotes/align-fuzzy`

请求中的每条引文是一个对象，`text` 为引文内容，`max_edits` 为该引文允许的最大
Levenshtein 编辑距离（插入、删除、替换均计 1，取值 **0～2**，必填）。

```json
{
  "text": "Archive  text\nwith repeats. Archive text.",
  "quotes": [
    {"text": "Archiv text", "max_edits": 1},
    {"text": "repeets", "max_edits": 1},
    {"text": "Archive text", "max_edits": 0},
    {"text": "zzzzzzzzzzz", "max_edits": 2}
  ]
}
```

响应（无法定位的引文为 `null`；`edit_distance` 为该片段实际付出的编辑距离）：

```json
{
  "results": [
    {"start": 0, "end": 13, "edit_distance": 1},
    {"start": 19, "end": 26, "edit_distance": 1},
    {"start": 28, "end": 40, "edit_distance": 0},
    null
  ]
}
```

`start` / `end` 为**原始文本**的字符偏移（`end` 为开区间），可直接用于 `text[start:end]` 切片。
编辑距离以 **Unicode 码元（code point）** 为单位计算（CJK、emoji 等单字符均计 1，而非按字节）。

### `GET /health`

返回 `{"status": "ok"}`。

## 匹配规则

- **空白折叠**：匹配时先将原文与引文中的连续空白（空格、换行、制表符等）折叠为单个空格；返回的偏移始终指向原始文本的原始字符。
- **精确匹配**（`/quotes/align`）：折叠空白后必须逐字相同才算定位成功。
- **模糊匹配**（`/quotes/align-fuzzy`）：在折叠空白后的文本上，以 Unicode 码元为单位计算
  Levenshtein 距离（插入、删除、替换代价均为 1），枚举出距离不超过该引文 `max_edits`
  的所有非空原文片段；`max_edits` 为 0 时与精确匹配等价。
- **重复引文**：同一引文出现多次时，各次匹配互不重叠，且保持引文数组的顺序。
- **联合选择**：从各引文的候选位置中整体选出一组互不重叠、保持数组顺序的定位，目标依次为：
  1. 最大化成功定位的引文条数；
  2. （仅模糊匹配）最小化已定位片段的编辑距离总和；
  3. 最小化已定位片段之间跳过的原文字符总数（首段之前、末段之后不计）；
  4. 仍并列时取偏移序列字典序最小（即最早）的一组。
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
