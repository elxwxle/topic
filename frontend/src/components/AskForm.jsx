import { useState } from "react";
import { askBus, askBusMore } from "../services/busApi";

const SESSION_ID = "web-demo";

const MORE_KEYWORDS = [
  "下一班",
  "還有嗎",
  "還有",
  "繼續",
  "更晚",
  "下一個",
  "再下一班",
];

function isMoreQuestion(text) {
  return MORE_KEYWORDS.some((keyword) => text.includes(keyword));
}

function AskForm() {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState([
    {
      role: "assistant",
      text: "您好！我是 AI 站長～有任何關於公車路線、班次、票價的問題，都可以問我喔！",
    },
  ]);
  const [lastResult, setLastResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleSend = async (e) => {
    e.preventDefault();

    const question = input.trim();
    if (!question) return;

    setInput("");

    const userMessage = {
      role: "user",
      text: question,
    };

    setMessages((prev) => [...prev, userMessage]);

    try {
      setLoading(true);

      let data;

      if (isMoreQuestion(question)) {
        if (!lastResult) {
          const warning = {
            role: "assistant",
            text: "請先問一個公車問題，我才知道要幫你查哪一班喔。",
          };
          setMessages((prev) => [...prev, warning]);
          return;
        }

        data = await askBusMore(SESSION_ID, lastResult.cursor ?? null);
      } else {
        data = await askBus(question, SESSION_ID);
      }

      setLastResult(data);

      const assistantMessage = {
        role: "assistant",
        text: data.answer || "我有收到資料，但目前沒有產生回答文字。",
        debug: data,
      };

      setMessages((prev) => [...prev, assistantMessage]);
    } catch (err) {
      const errorMessage = {
        role: "assistant",
        text: err.message || "查詢失敗，請稍後再試。",
      };

      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="page-layout">
      <section className="left-panel">
        <section className="ad-section">
          <button className="carousel-btn">‹</button>

          <div className="ad-card">
            <div className="ad-image">圖片</div>
            <p>廣告 1</p>
          </div>

          <div className="ad-card">
            <div className="ad-image">圖片</div>
            <p>廣告 2</p>
          </div>

          <div className="ad-card">
            <div className="ad-image">圖片</div>
            <p>廣告 3</p>
          </div>

          <button className="carousel-btn">›</button>

          <div className="carousel-dots">
            <span className="dot active"></span>
            <span className="dot"></span>
            <span className="dot"></span>
          </div>
        </section>

        <section className="map-section">
          <div className="map-title">🗺️ 路線地圖</div>

          <div className="map-placeholder">
            <div className="map-pin">📍</div>
            <p>針對問題回答後的路線地圖</p>
            <span>此區域目前為分割區塊，尚未載入內容</span>
          </div>
        </section>
      </section>

      <section className="right-panel">
        <section className="station-master">
          <h1>AI 站長</h1>

          <div className="mascot-area">
            <div className="mascot-face">👩‍✈️</div>
            <p>雲林公車服務中</p>
          </div>
        </section>

        <section className="chat-area">
          {messages.map((message, index) => (
            <div key={index} className={`message ${message.role}`}>
              <p>{message.text}</p>

              {message.debug && (
                <details className="debug-box">
                  <summary>查看完整 JSON</summary>
                  <pre>{JSON.stringify(message.debug, null, 2)}</pre>
                </details>
              )}
            </div>
          ))}

          {loading && (
            <div className="message assistant">
              <p>查詢中，請稍等一下...</p>
            </div>
          )}
        </section>

        <form className="input-area" onSubmit={handleSend}>
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="請輸入您的問題，例如：雲科大下一班車"
          />

          <button type="submit" disabled={loading}>
            ➤
          </button>
        </form>
      </section>
    </main>
  );
}

export default AskForm;