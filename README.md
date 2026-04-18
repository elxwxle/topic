# Yunlin Bus WebUI Project

一個以 **雲林公車查詢** 為核心的問答系統，整合：

- OpenWebUI Tool
- FastAPI 後端
- 規則式 NLU
- 結構化資料查詢
- RAG 補充說明層
- 分頁查詢（`/ask-more`）
- Session State 管理
- Redis / Memory 雙模式狀態儲存

---

## 功能簡介

本系統主要處理：

- 某站下一班來的車
- 某路線是否有到某站
- 如何從某地到某地
- 從某地回某地
- 車程多久
- 幾點前能不能到
- 若今天末班車已過，回覆明天最早一班
- 查不到站名時，提供補充說明或候選資訊

---

## 設計原則

### 1. 結構化查詢優先
本系統不是單純聊天，而是優先把問題解析成結構化 schema，再查：

- `yun.json`
- `aliases.json`

這樣比純 LLM 更穩定，適合處理：

- 路線
- 站名
- 班次
- 時間條件
- 到達可行性

### 2. RAG 只做補充
當結構化查詢找不到結果，或使用者問的是說明型問題時，才進入 RAG fallback。

### 3. ask / ask-more 分離
- `/ask`：第一次查詢
- `/ask-more`：沿用上一個 cursor 往後看

### 4. Session State 管理
系統會保存每個 session 的：

- `last_schema`
- `last_cursor`

正式前端接好前，開發階段可暫時允許 `default` session。

### 5. Redis / Memory 雙模式
狀態儲存支援：

- `MemoryStateStore`：本機開發用
- `RedisStateStore`：正式環境建議使用

---

## 專案架構

```text
使用者
  ↓
OpenWebUI
  ↓
Tool Layer
  ├─ yunlin_bus_ask
  └─ yunlin_bus_ask_more
  ↓
FastAPI (main.py)
  ↓
Request Validation
  ↓
NLU (intent + slot filling + semantic parsing)
  ↓
Entity Resolver
  ├─ alias normalize
  ├─ stop normalize
  └─ attraction ↔ stop mapping
  ↓
Query Router / Decision Engine (router.py)
  ├─ Structured Retrieval
  │    ├─ bus_core.py
  │    ├─ data/api.json
  │    └─ data/aliases.json
  │
  └─ RAG Fallback
       ├─ rag_core.py
       └─ rag_docs/*.md
  ↓
Response Formatter
  ├─ route number formatting
  ├─ time formatting
  ├─ pagination
  └─ answer template
  ↓
State Manager
  ├─ MemoryStateStore
  └─ RedisStateStore
  ↓
Logging / Debug Trace
  ↓
回傳 OpenWebUI