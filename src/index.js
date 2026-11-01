const DEFAULT_MODEL = "@cf/meta/llama-3.1-8b-instruct";
const MAX_MESSAGES = 12;
const MAX_MESSAGE_LENGTH = 6000;

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json; charset=utf-8" }
  });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === "/api/health") {
      return json({ ok: true, service: "ORAK AI", version: "0.1.0" });
    }

    if (url.pathname === "/api/chat" && request.method === "POST") {
      if (!env.AI) {
        return json({
          error: "لم يتم تفعيل Cloudflare Workers AI بعد. تأكدي من إضافة AI binding."
        }, 503);
      }

      let body;
      try {
        body = await request.json();
      } catch {
        return json({ error: "صيغة الطلب غير صحيحة." }, 400);
      }

      const messages = Array.isArray(body.messages) ? body.messages : [];
      const safeMessages = messages
        .filter((m) => m && ["user", "assistant"].includes(m.role) && typeof m.content === "string")
        .slice(-MAX_MESSAGES)
        .map((m) => ({
          role: m.role,
          content: m.content.slice(0, MAX_MESSAGE_LENGTH)
        }));

      if (!safeMessages.length || safeMessages[safeMessages.length - 1].role !== "user") {
        return json({ error: "أرسلي رسالة أولاً." }, 400);
      }

      try {
        const result = await env.AI.run(env.MODEL_ID || DEFAULT_MODEL, {
          messages: [
            {
              role: "system",
              content: "أنت ORAK AI، مساعد ذكي يتحدث العربية بوضوح وبأسلوب ودود. أجب بدقة، وصرّح عندما لا تعرف. لا تدّع تنفيذ إجراءات لم تنفذها."
            },
            ...safeMessages
          ],
          max_tokens: 900
        });

        const reply = result?.response || result?.result?.response || "";
        if (!reply) return json({ error: "لم يصل رد من النموذج. حاولي مرة أخرى." }, 502);
        return json({ reply });
      } catch (error) {
        return json({
          error: "تعذر الاتصال بالنموذج حالياً.",
          detail: env.NODE_ENV === "development" ? String(error) : undefined
        }, 502);
      }
    }

    if (url.pathname.startsWith("/api/")) {
      return json({ error: "المسار غير موجود." }, 404);
    }

    return env.ASSETS.fetch(request);
  }
};
