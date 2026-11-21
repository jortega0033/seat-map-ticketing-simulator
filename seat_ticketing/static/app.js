(function () {
  "use strict";

  var BASE = "/api/v1";
  var SHOW = BASE + "/shows/show-a";
  var TOKEN_KEY = "seatmap.token";
  var TOKEN_RE = /^[0-9a-f]{32}$/;
  var POLL_MS = 5000;

  var token = null;
  var state = null;
  var clockOffset = 0; // server_time - local seconds at fetch
  var selection = new Set();
  var busy = false;
  var seatButtons = {};
  var mapBuilt = false;

  var el = {
    map: document.getElementById("seat-map"),
    hold: document.getElementById("hold-button"),
    release: document.getElementById("release-button"),
    reload: document.getElementById("reload-button"),
    summary: document.getElementById("selection-summary"),
    status: document.getElementById("action-status"),
    remaining: document.getElementById("remaining-status"),
    expiry: document.getElementById("hold-expiry")
  };

  function setStatus(kind, text) {
    el.status.setAttribute("data-kind", kind);
    el.status.textContent = text;
  }

  function nowSec() { return Date.now() / 1000; }

  // ---- token ----
  function readStoredToken() {
    try {
      var t = window.localStorage.getItem(TOKEN_KEY);
      return t && TOKEN_RE.test(t) ? t : null;
    } catch (e) { return null; }
  }
  function storeToken(t) {
    try { window.localStorage.setItem(TOKEN_KEY, t); } catch (e) { /* in-memory only */ }
  }

  // ---- http ----
  function api(method, path, body) {
    var headers = { "Accept": "application/json" };
    if (token) headers["X-Session-Token"] = token;
    var opts = { method: method, headers: headers, cache: "no-store" };
    if (body !== undefined) {
      headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    return fetch(path, opts).then(function (res) {
      return res.text().then(function (txt) {
        var data = null;
        try { data = txt ? JSON.parse(txt) : null; } catch (e) { data = null; }
        return { ok: res.ok, status: res.status, data: data };
      });
    });
  }

  function errorOf(r) {
    var e = r.data && r.data.error;
    return {
      code: (e && e.code) || "error",
      message: (e && e.message) || ("Request failed (" + r.status + ")."),
      conflicts: (e && e.conflicts) || [],
      state: (e && r.data.state) || (r.data && r.data.error && r.data.error.state) || (r.data && r.data.state) || null
    };
  }

  function ensureToken() {
    token = readStoredToken();
    if (token) return Promise.resolve();
    return api("POST", BASE + "/session", {}).then(function (r) {
      if (r.ok && r.data && TOKEN_RE.test(r.data.token || "")) {
        token = r.data.token;
        storeToken(token);
      } else {
        throw new Error("Could not start a session.");
      }
    });
  }

  // ---- rendering ----
  function buildMap(rows) {
    el.map.textContent = "";
    seatButtons = {};
    rows.forEach(function (row) {
      var div = document.createElement("div");
      div.className = "row";
      var label = document.createElement("span");
      label.className = "row-label";
      label.textContent = row.row;
      label.setAttribute("aria-hidden", "true");
      var seats = document.createElement("div");
      seats.className = "seats";
      row.seats.forEach(function (s) {
        var b = document.createElement("button");
        b.type = "button";
        b.className = "seat";
        b.setAttribute("data-seat", s.id);
        var id = document.createElement("span");
        id.className = "seat-id";
        id.textContent = s.id;
        var st = document.createElement("span");
        st.className = "seat-state";
        b.appendChild(id);
        b.appendChild(st);
        b.addEventListener("click", onSeatClick);
        seats.appendChild(b);
        seatButtons[s.id] = b;
      });
      div.appendChild(label);
      div.appendChild(seats);
      el.map.appendChild(div);
    });
    mapBuilt = true;
  }

  function seatStatus(id) {
    if (!state) return null;
    for (var i = 0; i < state.rows.length; i++) {
      var seats = state.rows[i].seats;
      for (var j = 0; j < seats.length; j++) if (seats[j].id === id) return seats[j].status;
    }
    return null;
  }

  function renderSeats() {
    state.rows.forEach(function (row) {
      row.seats.forEach(function (s) {
        var b = seatButtons[s.id];
        if (!b) return;
        var label, word, pressed = false;
        b.classList.remove("available", "held_own", "held_other");
        b.classList.add(s.status);
        if (s.status === "held_other") {
          label = s.id + ", held by someone else";
          word = "Taken";
          b.disabled = true;
          b.setAttribute("aria-disabled", "true");
          b.removeAttribute("aria-pressed");
          b.removeAttribute("title");
        } else if (s.status === "held_own") {
          label = s.id + ", held by you";
          word = "Yours";
          b.disabled = false;
          b.removeAttribute("aria-disabled");
          b.removeAttribute("aria-pressed");
          b.title = "Activate to release this hold";
        } else {
          pressed = selection.has(s.id);
          label = s.id + ", available";
          word = pressed ? "Pick" : "Free";
          b.disabled = false;
          b.removeAttribute("aria-disabled");
          b.removeAttribute("title");
          b.setAttribute("aria-pressed", pressed ? "true" : "false");
        }
        b.setAttribute("aria-label", label);
        b.lastChild.textContent = word;
      });
    });
  }

  function renderSummary() {
    var ids = Array.from(selection).sort();
    el.summary.textContent = ids.length ? "Selected: " + ids.join(", ") : "No seats selected";
    el.hold.disabled = busy || ids.length === 0;
  }

  function renderRemaining() {
    var r = state.remaining;
    el.remaining.textContent = "Remaining: " + r.available + " available, " + r.held + " held, " + r.total + " total";
  }

  function ownSeats() {
    var out = [];
    if (!state) return out;
    state.rows.forEach(function (row) {
      row.seats.forEach(function (s) { if (s.status === "held_own") out.push(s); });
    });
    return out;
  }

  function renderExpiry() {
    var own = ownSeats();
    if (!own.length) { el.expiry.textContent = ""; return; }
    var earliest = Math.min.apply(null, own.map(function (s) { return s.expires_at; }));
    var left = Math.max(0, Math.ceil(earliest - (nowSec() + clockOffset)));
    el.expiry.textContent = left > 0
      ? "Your earliest hold expires in " + left + "s."
      : "Your earliest hold has expired. Reload seats.";
  }

  // Returns list of dropped selected seat ids.
  // keepSelection (background poll): leave seats that were taken by others selected,
  // so a stale submit still reaches the server and gets the explicit conflict message.
  function applyState(s, keepSelection) {
    if (state && typeof s.version === "number" && s.version < state.version) return [];
    state = s;
    clockOffset = s.server_time - nowSec();
    if (!mapBuilt) buildMap(s.rows);
    var dropped = [];
    if (!keepSelection) Array.from(selection).forEach(function (id) {
      if (seatStatus(id) !== "available") { selection.delete(id); dropped.push(id); }
    });
    renderSeats();
    renderSummary();
    renderRemaining();
    renderExpiry();
    return dropped.sort();
  }

  function fmtTime(sec) {
    return new Date(sec * 1000).toLocaleTimeString();
  }

  function setBusy(v) {
    busy = v;
    el.release.disabled = v;
    el.reload.disabled = v;
    Object.keys(seatButtons).forEach(function (k) {
      if (v) seatButtons[k].setAttribute("aria-busy", "true");
      else seatButtons[k].removeAttribute("aria-busy");
    });
    renderSummary();
  }

  function networkMsg() {
    return "Network problem: could not reach the server. Your selection is kept. Try again.";
  }

  // ---- actions ----
  function load(manual) {
    if (busy) return Promise.resolve();
    return (token ? Promise.resolve() : ensureToken()).then(function () {
      return api("GET", SHOW);
    }).then(function (r) {
      if (!r.ok) {
        if (manual) setStatus("error", errorOf(r).message);
        return;
      }
      var dropped = applyState(r.data, !manual);
      if (manual) {
        if (dropped.length) setStatus("info", "No longer available and unselected: " + dropped.join(", ") + ".");
        else setStatus("info", "Seats reloaded.");
      }
    }).catch(function () {
      if (manual) setStatus("error", networkMsg());
    });
  }

  function onSeatClick(ev) {
    if (busy) return;
    var id = ev.currentTarget.getAttribute("data-seat");
    var st = seatStatus(id);
    if (st === "held_own") { releaseOne(id); return; }
    if (st === "held_other") return;
    if (selection.has(id)) selection.delete(id); else selection.add(id);
    renderSeats();
    renderSummary();
  }

  function doHold() {
    var ids = Array.from(selection).sort();
    if (busy || !ids.length) return;
    setBusy(true);
    api("POST", SHOW + "/holds", { seats: ids }).then(function (r) {
      if (r.ok) {
        selection.clear();
        applyState(r.data);
        var held = r.data.held || ids;
        var exp = null;
        ownSeats().forEach(function (s) {
          if (held.indexOf(s.id) >= 0 && (exp === null || s.expires_at < exp)) exp = s.expires_at;
        });
        setStatus("success", "Held " + held.join(", ") + (exp !== null ? " until " + fmtTime(exp) + "." : "."));
        return;
      }
      var e = errorOf(r);
      if (r.status === 409) {
        if (e.state) applyState(e.state);
        var c = e.conflicts.length ? e.conflicts : [];
        var verb = c.length === 1 ? " is" : " are";
        setStatus("conflict", "Conflict: " + (c.length ? c.join(", ") : "A seat") + (c.length ? verb : " is") +
          " held by someone else. No seats were held.");
      } else {
        // keep selection of seats still available; refresh quietly first
        setStatus("error", e.message);
      }
    }).catch(function () {
      setStatus("error", networkMsg());
    }).then(function () {
      setBusy(false);
      renderSeats();
    });
  }

  function releaseOne(id) {
    setBusy(true);
    api("DELETE", SHOW + "/holds/" + encodeURIComponent(id)).then(function (r) {
      if (r.ok) {
        applyState(r.data);
        setStatus("success", "Released " + id + ".");
      } else {
        var e = errorOf(r);
        setStatus("error", e.message);
        setBusy(false);
        return load(false);
      }
    }).catch(function () {
      setStatus("error", networkMsg());
    }).then(function () { setBusy(false); renderSeats(); });
  }

  function doRelease() {
    if (busy) return;
    var ids = ownSeats().map(function (s) { return s.id; });
    if (!ids.length) { setStatus("info", "You have no holds to release."); return; }
    setBusy(true);
    var done = [];
    var failure = null;
    var chain = Promise.resolve();
    ids.forEach(function (id) {
      chain = chain.then(function () {
        if (failure) return;
        return api("DELETE", SHOW + "/holds/" + encodeURIComponent(id)).then(function (r) {
          if (r.ok) { applyState(r.data); done.push(id); }
          else if (r.status === 404) { /* already gone */ }
          else failure = errorOf(r).message;
        });
      });
    });
    chain.catch(function () {
      failure = networkMsg();
    }).then(function () {
      if (failure) {
        setStatus("error", (done.length ? "Released " + done.join(", ") + ". " : "") + failure);
      } else if (done.length) {
        setStatus("success", "Released " + done.join(", ") + ".");
      } else {
        setStatus("info", "Your holds had already expired or been released.");
      }
      setBusy(false);
      return load(false);
    });
  }

  // ---- init ----
  el.hold.addEventListener("click", doHold);
  el.release.addEventListener("click", doRelease);
  el.reload.addEventListener("click", function () { load(true); });

  ensureToken().then(function () {
    return api("GET", SHOW).then(function (r) {
      if (!r.ok) throw new Error(errorOf(r).message);
      applyState(r.data);
    });
  }).catch(function (e) {
    var msg = e instanceof TypeError ? networkMsg() : (e && e.message) || networkMsg();
    el.map.textContent = "";
    var p = document.createElement("p");
    p.textContent = "Seats could not be loaded. Use Reload seats to try again.";
    el.map.appendChild(p);
    setStatus("error", msg);
  }).then(function () {
    // Poll and countdown run even after a failed first load so the page recovers.
    setInterval(function () { load(false); }, POLL_MS);
    setInterval(function () { if (state) renderExpiry(); }, 1000);
  });
})();
