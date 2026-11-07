/* Shared, side-effect-free input validation. No page code is evaluated. */
(() => {
  "use strict";
  const HOSTS = new Set(["youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"]);
  function videoUrl(value) {
    try {
      const u = new URL(value);
      if (u.protocol !== "https:" || u.username || u.password || (u.port && u.port !== "443") || !HOSTS.has(u.hostname)) return null;
      let id;
      if (u.hostname === "youtu.be") id = u.pathname.slice(1);
      else if (u.pathname === "/watch") id = u.searchParams.get("v");
      else if (/^\/(shorts|live)\//.test(u.pathname)) id = u.pathname.split("/")[2];
      if (!/^[A-Za-z0-9_-]{11}$/.test(id || "")) return null;
      return `https://www.youtube.com/watch?v=${id}`;
    } catch { return null; }
  }
  function pageUrl(value) {
    try { const u = new URL(value); return u.protocol === "https:" && !u.username && !u.password && (!u.port || u.port === "443") && HOSTS.has(u.hostname) && u.hostname !== "youtu.be"; }
    catch { return false; }
  }
  function downloadPayload(p) {
    if (!p || typeof p !== "object" || p.authorized !== true) throw new Error("Confirme que você tem autorização para baixar esta mídia.");
    const url = videoUrl(p.url);
    if (!url) throw new Error("Escolha um vídeo válido do YouTube.");
    const format = p.format || "mp3";
    const quality = Number(p.quality || (format === "mp4" ? 720 : 192));
    if (!["mp3", "m4a", "opus", "mp4"].includes(format) || !(format === "mp4" ? [360,720,1080] : [128,192,320]).includes(quality)) throw new Error("Formato ou qualidade inválidos.");
    const text = x => typeof x === "string" ? x.slice(0,500) : "";
    return {url, format, quality, authorized:true, title:text(p.title), channel:text(p.channel), thumbnail:thumbnail(p.thumbnail)};
  }
  function thumbnail(value) {
    try { const u = new URL(value); return u.protocol === "https:" && ["i.ytimg.com", "i9.ytimg.com", "img.youtube.com"].includes(u.hostname) ? u.href : ""; }
    catch { return ""; }
  }
  const status = {queued:"Na fila", preparing:"Preparando sua música…", downloading:"Baixando mídia…", converting:"Convertendo mídia…", completed:"Arquivo salvo com sucesso!", cancelled:"Download cancelado", error:"Não foi possível concluir o download"};
  globalThis.OMD = Object.freeze({videoUrl, pageUrl, downloadPayload, thumbnail, status, active:new Set(["queued","preparing","downloading","converting"])});
})();
