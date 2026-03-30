# Yunlin Bus WebUI Project

一個以 **雲林公車查詢** 為核心的問答系統，整合：

- **OpenWebUI Tool**
- **FastAPI 後端**
- **規則式 NLU**
- **結構化資料查詢**
- **RAG 補充說明層**

系統可以回答：

- 某站下一班來的車
- 某路線是否有到某站
- 如何從某地到某地
- 車程多久
- 幾點前能不能到
- 末班車已過時，回覆明天最早一班
- 查不到站名時，提供補充說明或候選資訊

---

## 專案特色

### 1. 結構化查詢優先
本系統的核心不是單純聊天，而是先把問題解析成結構化欄位，再查：

- `yun.json`
- `aliases.json`

這樣能比純 LLM 回答更準確地處理：

- 班次
- 路線
- 站名
- 時間條件
- 到達可行性

### 2. 一次只回答一班
第一次查詢只回：

- 下一班
- 最近一班
- 或明天最早一班

若使用者想繼續往後看，可使用 `/ask-more`。

### 3. 支援末班車已過邏輯
若今天現在之後已沒有班次，系統不會只說「沒有資料」，而會回答：

- 今天末班車已過
- 明天最早一班是什麼

### 4. 支援 RAG 補充說明
當結構化查詢找不到結果，或使用者問的是說明型問題時，系統會啟動 RAG fallback，從知識文件中補充：

- 景點與站名對照
- FAQ
- 路線說明
- 常見別名說明

---

## 專案架構

```text
使用者
  ↓
OpenWebUI
  ↓
Tool: yunlin_bus_ask / yunlin_bus_ask_more
  ↓
FastAPI (main.py)
  ↓
NLU (nlu.py)
  ↓
查詢決策
  ├─ Structured Retrieval
  │    ├─ bus_core.py
  │    ├─ data/yun.json
  │    └─ data/aliases.json
  │
  └─ RAG Fallback
       ├─ rag_core.py
       └─ rag_docs/*.md
  ↓
回答整形與分頁
  ↓
回傳 OpenWebUI