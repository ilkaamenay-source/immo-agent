// Relais Cloudflare Worker : Telegram -> GitHub Actions (gratuit).
// Variables à définir dans Cloudflare (Settings > Variables and Secrets) :
//   BOT_TOKEN        token du bot Telegram            (Secret)
//   TG_SECRET        mot de passe inventé par toi, repris dans setWebhook   (Secret)
//   ALLOWED_CHAT_ID  ton identifiant de chat Telegram (texte)
//   GH_REPO          ex: ilkaamenay-source/immo-agent (texte)
//   GH_TOKEN         jeton GitHub "fine-grained" avec Actions : Read and write (Secret)
export default {
  async fetch(request, env) {
    if (request.method !== "POST") return new Response("ok");
    if (request.headers.get("X-Telegram-Bot-Api-Secret-Token") !== env.TG_SECRET) {
      return new Response("forbidden", { status: 403 });
    }
    let update;
    try { update = await request.json(); } catch { return new Response("ok"); }
    const msg = update.message || update.edited_message;
    if (!msg || !msg.text) return new Response("ok");
    if (String(msg.chat.id) !== String(env.ALLOWED_CHAT_ID)) return new Response("ok"); // ignore les inconnus

    const text = msg.text.slice(0, 1000);
    const gh = await fetch(
      `https://api.github.com/repos/${env.GH_REPO}/actions/workflows/telegram.yml/dispatches`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${env.GH_TOKEN}`,
          Accept: "application/vnd.github+json",
          "X-GitHub-Api-Version": "2022-11-28",
          "User-Agent": "immo-agent-relay",
        },
        body: JSON.stringify({ ref: "main", inputs: { chat_id: String(msg.chat.id), text } }),
      }
    );
    const reply = gh.status === 204
      ? (text.startsWith("/") ? null : "⏳ Analyse en cours… réponse dans 30 à 90 secondes.")
      : `⚠️ Impossible de lancer l'analyse (GitHub a répondu ${gh.status}). Vérifie le jeton GH_TOKEN.`;
    if (reply) {
      await fetch(`https://api.telegram.org/bot${env.BOT_TOKEN}/sendMessage`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ chat_id: msg.chat.id, text: reply }),
      });
    }
    return new Response("ok");
  },
};
