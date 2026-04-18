const BASE_URL = "http://127.0.0.1:8000";

export async function askBus(question, sessionId = "web-demo") {
  const response = await fetch(`${BASE_URL}/ask`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      question,
      session_id: sessionId,
    }),
  });

  if (!response.ok) {
    throw new Error(`API 錯誤：${response.status}`);
  }

  return await response.json();
}