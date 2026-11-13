/* Hosted deployments talk to the public API address; local use (localhost or a LAN address) keeps using this computer. */
(function () {
  var h = location.hostname;
  if (!/^(localhost|127\.|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)/.test(h)) window.RW_API_BASE = "https://canvas-dispatch-front-gen.trycloudflare.com";
})();
