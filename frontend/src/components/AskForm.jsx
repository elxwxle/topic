import { useState } from "react";
import { askBus } from "../services/busApi";

function AskForm() {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!question.trim()) {
      setError("請先輸入問題");
      return;
    }

    try {
      setLoading(true);
      setError("");
      const data = await askBus(question, "web-demo");
      setResult(data);
    } catch (err) {
      setError(err.message || "查詢失敗");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <form onSubmit={handleSubmit}>
        <input
          type="text"
          placeholder="例如：如何到雲科"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
        />
        <button type="submit" disabled={loading}>
          {loading ? "查詢中..." : "送出查詢"}
        </button>
      </form>

      {error && <p>{error}</p>}

      {result && (
        <div>
          <h2>查詢結果</h2>
          <pre>{JSON.stringify(result, null, 2)}</pre>
        </div>
      )}
    </div>
  );
}

export default AskForm;