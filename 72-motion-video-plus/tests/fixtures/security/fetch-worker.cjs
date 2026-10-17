// MG-029 fixture: a plain child that fetches the URLs given as argv
// and prints one line per URL: "<url> reached" or "<url> blocked".
// Used to prove the network namespace policy with an ordinary Node
// process as well as with the browser: inside the namespace the
// recorder URLs are unreachable; outside it they answer.
"use strict";
const net = require("node:net");

function tcpProbe(host, port) {
  return new Promise((resolveProbe) => {
    const socket = net.connect({ host, port, timeout: 6000 }, () => {
      socket.end();
      resolveProbe(true);
    });
    socket.on("timeout", () => {
      socket.destroy();
      resolveProbe(false);
    });
    socket.on("error", () => resolveProbe(false));
  });
}

(async () => {
  for (const url of process.argv.slice(2)) {
    if (url.startsWith("tcp://")) {
      // tcp://host:port -- a bare connection probe, for endpoints
      // that are not HTTP recorders (the sandbox egress proxy).
      const rest = url.slice("tcp://".length);
      const idx = rest.lastIndexOf(":");
      const ok = await tcpProbe(rest.slice(0, idx), Number(rest.slice(idx + 1)));
      process.stdout.write(url + (ok ? " reached\n" : " blocked\n"));
      continue;
    }
    try {
      const res = await fetch(url);
      await res.text();
      process.stdout.write(url + " reached\n");
    } catch {
      process.stdout.write(url + " blocked\n");
    }
  }
})();
