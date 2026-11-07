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
    if (!p || typeof p !== "object") throw new Error("Escolha um vídeo válido do YouTube.");
    const url = videoUrl(p.url);
    if (!url) throw new Error("Escolha um vídeo válido do YouTube.");
    const text = x => typeof x === "string" ? x.slice(0,500) : "";
    // Saved native preferences are authoritative. Caller paths, quality and authorization are ignored.
    return {url, title:text(p.title), channel:text(p.channel), thumbnail:thumbnail(p.thumbnail)};
  }
  function settingsPayload(p) {
    if (!p || typeof p !== "object") throw new Error("Preferências inválidas.");
    const result = {};
    if ("defaultFormat" in p) {if (!["mp3","mp4"].includes(p.defaultFormat)) throw new Error("Formato inválido.");result.defaultFormat=p.defaultFormat;}
    for (const [name,values] of [["mp3Quality",[128,192,320]],["mp4Quality",[360,720,1080]]]) {
      if (name in p) {if (!values.includes(p[name])) throw new Error("Qualidade inválida.");result[name]=p[name];}
    }
    for (const name of ["openFolder","authorizedDownloads"]) {
      if (name in p) {if (typeof p[name] !== "boolean") throw new Error("Preferência inválida.");result[name]=p[name];}
    }
    if ("defaultFolder" in p) {if (typeof p.defaultFolder !== "string" || p.defaultFolder.length > 32767) throw new Error("Pasta inválida."); result.defaultFolder=p.defaultFolder; result.folderMode="default";}
    return result;
  }
  function thumbnail(value) {
    try { const u = new URL(value); return u.protocol === "https:" && ["i.ytimg.com", "i9.ytimg.com", "img.youtube.com"].includes(u.hostname) ? u.href : ""; }
    catch { return ""; }
  }
  const status = {queued:"Na fila", preparing:"Preparando sua música…", downloading:"Baixando mídia…", converting:"Convertendo mídia…", completed:"Arquivo salvo com sucesso!", cancelled:"Download cancelado", error:"Não foi possível concluir o download"};
  globalThis.OMD = Object.freeze({videoUrl, pageUrl, downloadPayload, settingsPayload, thumbnail, status, active:new Set(["queued","preparing","downloading","converting"])});
})();
