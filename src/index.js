export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/api/health") return Response.json({ ok: true, app: env.APP_NAME || "ORAK AI" });
    if (url.pathname === "/api/chat" && request.method === "POST") {
      try {
        const body = await request.json();
        const messages = Array.isArray(body.messages) ? body.messages : [];
        if (!messages.length) return Response.json({ error: "أرسلي رسالة أولاً" }, { status: 400 });
        if (!env.AI_API_KEY) return Response.json({ error: "لم يتم إعداد مفتاح الذكاء الاصطناعي بعد. أضيفي AI_API_KEY في Cloudflare Secrets." }, { status: 503 });
        const base = (env.AI_BASE_URL || "https://api.openai.com/v1").replace(/\/$/, "");
        const upstream = await fetch(base + "/chat/completions", {
          method: "POST",
          headers: { "Authorization": "Bearer " + env.AI_API_KEY, "Content-Type": "application/json" },
          body: JSON.stringify({ model: env.AI_MODEL || "gpt-4o-mini", messages: [{ role: "system", content: "أنت ORAK AI، مساعد ذكي يتحدث العربية بوضوح وبأسلوب ودود. لا تدّع امتلاك قدرات غير مفعّلة." }, ...messages.slice(-20)], temperature: 0.7 })
        });
        const data = await upstream.json();
        if (!upstream.ok) return Response.json({ error: data.error?.message || "تعذر الاتصال بمزود النموذج" }, { status: upstream.status });
        return Response.json({ reply: data.choices?.[0]?.message?.content || "لم يصل رد من النموذج." });
      } catch { return Response.json({ error: "حدث خطأ في معالجة الطلب." }, { status: 500 }); }
    }
    return env.ASSETS.fetch(request);
  }
};