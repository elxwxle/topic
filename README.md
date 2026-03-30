# Yunlin Bus WebUI 專案

## 1. 檔案架構

```text
yunlin_bus_webui_project/
├─ README.md
└─ app/
   ├─ main.py
   ├─ bus_core.py
   ├─ requirements.txt
   └─ data/
      ├─ yunlin_bus_part1.md
      ├─ aliases.json
      ├─ stops_coords.json            # 你自己建立，從 sample 複製
      └─ stops_coords.sample.json
```

## 2. 每個檔案的用途

### `app/main.py`
FastAPI 入口，提供給 Open WebUI 呼叫的 API。

### `app/bus_core.py`
核心查詢模組，處理以下功能：
- 某站或某地怎麼走
- 通勤時間
- 如何回來
- 某車班次
- 某車有沒有到某站
- 某時間能不能到某處
- 最近站牌是哪裡
- 簡單自然語言問句 `/ask`

### `app/data/yunlin_bus_part1.md`
你的原始公車資料檔。

### `app/data/aliases.json`
地名簡稱對照表。

### `app/data/stops_coords.json`
站牌經緯度。最近站牌功能一定要靠這份檔案。

---

## 3. 準備資料

把你原本的 `yunlin_bus_part1.md` 複製到：

```text
app/data/yunlin_bus_part1.md
```

把範例座標檔複製成正式檔：

```bash
cp app/data/stops_coords.sample.json app/data/stops_coords.json
```

之後再慢慢把完整站牌座標補進去。

---

## 4. 安裝與啟動

進到 `app` 資料夾：

```bash
cd app
```

建立虛擬環境：

```bash
python -m venv .venv
```

Windows 啟用：

```bash
.venv\Scripts\activate
```

Linux / WSL 啟用：

```bash
source .venv/bin/activate
```

安裝套件：

```bash
pip install -r requirements.txt
```

啟動 API：

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

看到下面這種訊息就代表成功：

```text
Uvicorn running on http://0.0.0.0:8000
```

---

## 5. 測試 API

### 首頁

瀏覽器開：

```text
http://localhost:8000/
```

### Swagger 文件

```text
http://localhost:8000/docs
```

你可以直接在 `/docs` 測每個 API。

---

## 6. API 範例

### 查某車班次

POST `/route-schedule`

```json
{
  "route": "201"
}
```

### 查某站還有沒有車

POST `/stop-upcoming`

```json
{
  "stop": "雲林科技大學",
  "now": "09:00"
}
```

### 查某車有沒有到某站

POST `/route-reach`

```json
{
  "route": "201",
  "destination": "雲林科技大學"
}
```

### 查某站怎麼去

POST `/route-plan`

```json
{
  "destination": "雲林科技大學",
  "origin": "斗六火車站",
  "after": "08:00",
  "allow_transfer": true
}
```

### 如何回來

POST `/return-plan`

```json
{
  "from_place": "雲林科技大學",
  "destination": "斗六火車站",
  "after": "12:00",
  "allow_transfer": true
}
```

### 某時間能不能到

POST `/arrival-feasible`

```json
{
  "destination": "高鐵雲林站",
  "origin": "斗六火車站",
  "after": "08:00",
  "arrive_by": "10:00",
  "allow_transfer": true
}
```

### 通勤時間

POST `/travel-time`

```json
{
  "destination": "雲林科技大學",
  "origin": "斗六火車站",
  "after": "08:00",
  "allow_transfer": true
}
```

### 最近站牌

POST `/nearest-stop`

```json
{
  "lat": 23.700,
  "lon": 120.535
}
```

### 自然語言

POST `/ask`

```json
{
  "question": "201 公車幾點"
}
```

---

## 7. Open WebUI 怎麼接

如果 Open WebUI 是 Docker 跑的，API 不要填 `localhost`，通常要填：

```text
http://host.docker.internal:8000
```

如果這個不通，就改成你主機的區網 IP，例如：

```text
http://192.168.1.50:8000
```

然後在 Open WebUI 新增 Tool 或 Function，讓它呼叫：

```text
POST /ask
```

Body：

```json
{
  "question": "{{prompt}}"
}
```

也可以依需求分開做多個工具，例如：
- `/route-schedule`
- `/route-reach`
- `/stop-upcoming`
- `/route-plan`

---

## 8. 建議執行順序

1. 先把 `yunlin_bus_part1.md` 放進 `app/data/`
2. 先把 `stops_coords.sample.json` 複製成 `stops_coords.json`
3. 啟動 API
4. 用 `http://localhost:8000/docs` 手動測
5. 測通了再接 Open WebUI
6. 最後再補更多地名簡稱和完整站牌座標

---

## 9. 目前限制

- 最近站牌功能一定要靠 `stops_coords.json`
- `/ask` 目前是規則式判斷，不是完整 AI NLU
- 路徑規劃目前支援直達優先，其次一次轉乘
- 如果你之後要做更穩的台語回答，建議讓 API 先回傳結構化結果，再由模型生成台語句子
