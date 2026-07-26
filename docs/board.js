/* ==========================================================================
   Live re-creation of the e-paper board.

   Mirrors what display.py actually does:
   - the clock only changes when the panel refreshes, not every second;
   - departures inside show_arrival_minutes_threshold (10 min) count down in
     minutes, everything further out shows a departure time;
   - a refresh flashes the panel while the ink settles.
   The refresh interval is sped up here; the real default is 300 s.
   ========================================================================== */

(function () {
  "use strict";

  var REFRESH_MS = 20000;
  var MINUTES_THRESHOLD = 10;   // config.display.show_arrival_minutes_threshold
  var MAX_ITEMS = 5;            // config.display.max_items

  var POOL = [
    { line: "1T", dest: "Käpylä via Bulevardi" },
    { line: "7",  dest: "Meilahden sairaala via Päärautatieas." },
    { line: "9",  dest: "Ilmala via Päärautatieas." }
  ];

  var board = document.getElementById("board");
  var clockEl = document.getElementById("clock");
  var rowsEl = document.getElementById("rows");
  if (!board || !clockEl || !rowsEl) return;

  var rowEls = Array.prototype.slice.call(rowsEl.querySelectorAll(".row"));
  if (rowEls.length < MAX_ITEMS) return;

  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  var poolIndex = 0;
  var departures = [];
  var timer = null;
  var visible = true;

  function nextFromPool() {
    var item = POOL[poolIndex % POOL.length];
    poolIndex += 1;
    return item;
  }

  function pad(n) {
    return n < 10 ? "0" + n : String(n);
  }

  function hhmm(date) {
    return pad(date.getHours()) + ":" + pad(date.getMinutes());
  }

  function seed() {
    var now = Date.now();
    var offsets = [5, 11, 15, 16, 21];   // minutes, as in the reference render
    departures = offsets.map(function (min) {
      var item = nextFromPool();
      return { line: item.line, dest: item.dest, at: now + min * 60000 };
    });
  }

  function advance() {
    var now = Date.now();
    // Drop anything that has left, and top the list back up to max_items.
    departures = departures.filter(function (d) {
      return d.at - now > -30000;
    });
    while (departures.length < MAX_ITEMS) {
      var last = departures.length
        ? departures[departures.length - 1].at
        : now + 4 * 60000;
      var item = nextFromPool();
      departures.push({
        line: item.line,
        dest: item.dest,
        at: last + (4 + (poolIndex % 3)) * 60000
      });
    }
  }

  function render() {
    var now = new Date();
    clockEl.textContent = hhmm(now);

    departures.slice(0, MAX_ITEMS).forEach(function (dep, i) {
      var el = rowEls[i];
      var mins = Math.max(0, Math.round((dep.at - now.getTime()) / 60000));
      el.querySelector(".row__line").textContent = dep.line;
      el.querySelector(".row__dest").textContent = dep.dest;
      el.querySelector(".row__time").textContent =
        mins <= MINUTES_THRESHOLD ? String(mins) : hhmm(new Date(dep.at));
    });
  }

  /* A Waveshare full refresh inverts the panel a couple of times before the
     new frame settles. Two short flashes read as the real thing. */
  function refresh() {
    if (reduceMotion.matches) {
      advance();
      render();
      return;
    }
    board.classList.add("is-refreshing");
    setTimeout(function () { board.classList.remove("is-refreshing"); }, 110);
    setTimeout(function () { board.classList.add("is-refreshing"); }, 210);
    setTimeout(function () {
      board.classList.remove("is-refreshing");
      advance();
      render();
    }, 330);
  }

  function start() {
    if (timer) return;
    timer = setInterval(function () {
      if (visible && !document.hidden) refresh();
    }, REFRESH_MS);
  }

  function stop() {
    clearInterval(timer);
    timer = null;
  }

  seed();
  render();

  if ("IntersectionObserver" in window) {
    new IntersectionObserver(function (entries) {
      visible = entries[0].isIntersecting;
      if (visible) { start(); } else { stop(); }
    }, { threshold: 0.15 }).observe(board);
  } else {
    start();
  }

  document.addEventListener("visibilitychange", function () {
    if (document.hidden) { stop(); } else if (visible) { start(); }
  });
})();
