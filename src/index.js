const MODEL = "@cf/meta/llama-3.1-8b-instruct";

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === "/api/health") {
      return Response.json({
        ok: true,
        app: "ORAK AI",
        engine: "Cloudflare Workers AI",
        model: MODEL
      });
    }

    if (url.pathname === "/api/chat" && request.method === "POST") {
      try {
        const body = await request.json();
        const incoming = Array.isArray(body.messages) ? body.messages : [];
        if (!incoming.length) {
          return Response.json({ error: "أرسلي رسالة أولاً." }, { status: 400 });
        }
        const messages = incoming
          .filter(m => m && ["user", "assistant"].includes(m.role) && typeof m.content === "string")
          .slice(-16);
        if (!messages.length) {
          return Response.json({ error: "صيغة الرسائل غير صحيحة." }, { status: 400 });
        }

        const result = await env.AI.run(MODEL, {
          messages: [
            { role: "system", content: "أنت ORAK AI، مساعد ذكي يتحدث العربية بوضوح وبأسلوب ودود. أجب بدقة، وصرّح عندما لا تعرف. لا تدّع امتلاك قدرات غير مفعّلة." },
            ...messages
          ],
          max_tokens: 900
        });

        const reply = typeof result?.response === "string"
          ? result.response
          : result?.choices?.[0]?.message?.content;
        if (!reply) {
          return Response.json({ error: "وصل رد غير متوقع من محرك الذكاء الاصطناعي." }, { status: 502 });
        }
        return Response.json({ reply, model: MODEL });
      } catch (error) {
        return Response.json({
          error: "تعذر تشغيل نموذج الذكاء الاصطناعي. تأكدي من تفعيل Workers AI في حساب Cloudflare.",
          detail: String(error?.message || error)
        }, { status: 502 });
      }
    }

    return env.ASSETS.fetch(request);
  }
};
