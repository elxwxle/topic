const BASE_URL = "http://127.0.0.1:8000";

async function postJson(path, body) {
  const response = await fetch(`${BASE_URL}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    throw new Error(`API 錯誤：${response.status}`);
  }

  return await response.json();
}

export async function askBus(question, sessionId = "web-demo") {
  return await postJson("/ask", {
    question,
    session_id: sessionId,
  });
}

export async function askBusMore(sessionId = "web-demo", cursor = null) {
  return await postJson("/ask-more", {
    session_id: sessionId,
    cursor,
  });
}