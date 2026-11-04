/* NLZ-Stellen - liest data/jobs.json und zeigt die Stellen an.
 *
 * Alle Texte kommen von fremden Karriereseiten. Sie werden daher
 * ausschliesslich als Textknoten eingefuegt, nie als HTML.
 */
(function () {
  "use strict";

  var DATA_URL = "data/jobs.json";
  var PRIO_LABEL = { A: "GLB", B: "Sport", C: "Sonstige" };

  var state = {
    jobs: [],
    clubs: {},
    settings: { new_badge_days: 7 },
    generated: null,
    view: "new",
    search: "",
    club: "",
    open: {}
  };

  var el = {
    summary: document.getElementById("summary"),
    status: document.getElementById("status"),
    list: document.getElementById("list"),
    clubList: document.getElementById("clubList"),
    filters: document.getElementById("filters"),
    tabs: document.getElementById("tabs"),
    search: document.getElementById("search"),
    clubFilter: document.getElementById("clubFilter"),
    generated: document.getElementById("generated"),
    infoToggle: document.getElementById("infoToggle"),
    infoBox: document.getElementById("infoBox")
  };

  /* ---------- Hilfsfunktionen ---------- */

  function node(tag, className, text) {
    var n = document.createElement(tag);
    if (className) { n.className = className; }
    if (text !== undefined && text !== null && text !== "") {
      n.textContent = String(text);
    }
    return n;
  }

  function parseDate(value) {
    if (!value) { return null; }
    var d = new Date(value);
    return isNaN(d.getTime()) ? null : d;
  }

  function formatDate(value) {
    var d = parseDate(value);
    if (!d) { return ""; }
    return d.toLocaleDateString("de-DE", {
      day: "2-digit", month: "2-digit", year: "numeric"
    });
  }

  function daysSince(value) {
    var d = parseDate(value);
    if (!d) { return Infinity; }
    return (Date.now() - d.getTime()) / 86400000;
  }

  function isNew(job) {
    // "Neu" heisst: nach dem Erstlauf dazugekommen. Die beim Erstlauf
    // vorgefundenen Stellen sind Bestand (initial), kein Fund - sonst waere
    // nach dem ersten Lauf eine Woche lang alles neu. Der Scraper setzt das
    // Kennzeichen; dieselbe Unterscheidung steuert auch die Pushes.
    return job.status === "offen" && !job.initial &&
      daysSince(job.first_seen) <= (state.settings.new_badge_days || 7);
  }

  function isNewSport(job) {
    // Der Reiter "Neu" zeigt ausschliesslich Stellen mit Sportbezug.
    // Neue Stellen ohne Sportbezug stehen nur unter "Sonstige".
    return isNew(job) && (job.priority === "A" || job.priority === "B");
  }

  /* ---------- Beschreibung aufbauen ----------
   * Der Scraper liefert "## Ueberschrift" und "- Aufzaehlungspunkt".
   * Daraus werden echte Elemente, aber nur mit Textinhalt.
   */
  function renderDescription(text) {
    var wrap = node("div", "desc");
    if (!text) { return wrap; }
    var lines = String(text).split("\n");
    var list = null;
    var buffer = [];

    function flushParagraph() {
      if (!buffer.length) { return; }
      wrap.appendChild(node("p", null, buffer.join(" ")));
      buffer = [];
    }

    lines.forEach(function (raw) {
      var line = raw.trim();
      if (!line) { flushParagraph(); list = null; return; }
      if (line.indexOf("## ") === 0) {
        flushParagraph(); list = null;
        wrap.appendChild(node("h4", null, line.slice(3)));
        return;
      }
      if (line.indexOf("- ") === 0) {
        flushParagraph();
        if (!list) { list = node("ul"); wrap.appendChild(list); }
        list.appendChild(node("li", null, line.slice(2)));
        return;
      }
      list = null;
      buffer.push(line);
    });
    flushParagraph();
    return wrap;
  }

  /* ---------- Karten ---------- */

  function badge(cls, label) { return node("span", "badge " + cls, label); }

  function plural(count, one, many) {
    return count + " " + (count === 1 ? one : many);
  }

  function chip(text, cls) {
    return text ? node("span", "chip" + (cls ? " " + cls : ""), text) : null;
  }

  function buildCard(job) {
    var card = node("article", "card" + (job.status === "geschlossen" ? " is-closed" : ""));
    var head = node("button", "card-head");
    head.type = "button";
    head.setAttribute("aria-expanded", state.open[job.id] ? "true" : "false");

    var top = node("div", "card-top");
    top.appendChild(node("span", "club", job.club));
    top.appendChild(badge(String(job.priority || "C").toLowerCase(),
                          PRIO_LABEL[job.priority] || "Sonstige"));
    if (isNew(job)) { top.appendChild(badge("new", "neu")); }
    if (job.status === "geschlossen") { top.appendChild(badge("closed", "geschlossen")); }
    head.appendChild(top);

    head.appendChild(node("h2", "card-title", job.title));

    var chips = node("div", "chips");
    [
      chip("gefunden am " + formatDate(job.first_seen)),
      chip(job.published_at ? "veröffentlicht " + formatDate(job.published_at) : null),
      chip(job.location),
      chip(job.employment_type),
      chip(job.department),
      chip(job.deadline ? "Frist " + formatDate(job.deadline) : null, "deadline"),
      chip(job.status === "geschlossen" && job.closed_at
        ? "entfernt am " + formatDate(job.closed_at) : null)
    ].forEach(function (c) { if (c) { chips.appendChild(c); } });
    head.appendChild(chips);
    card.appendChild(head);

    var body = node("div", "card-body");
    body.hidden = !state.open[job.id];
    body.appendChild(renderDescription(job.description));

    var actions = node("div", "actions");
    if (job.url) {
      var main = node("a", "btn", "Zur Originalanzeige");
      main.href = job.url;
      main.target = "_blank";
      main.rel = "noopener noreferrer";
      actions.appendChild(main);
    }
    if (job.apply_url && job.apply_url !== job.url) {
      var apply = node("a", "btn secondary", "Direkt bewerben");
      apply.href = job.apply_url;
      apply.target = "_blank";
      apply.rel = "noopener noreferrer";
      actions.appendChild(apply);
    }
    body.appendChild(actions);

    var reasonBits = [];
    if (job.priority_reason) { reasonBits.push("Einstufung: " + job.priority_reason); }
    if (job.contact) { reasonBits.push("Ansprechpartner: " + job.contact); }
    if (job.source_label) { reasonBits.push("Quelle: " + job.source_label); }
    if (reasonBits.length) {
      body.appendChild(node("p", "reason", reasonBits.join(" · ")));
    }
    card.appendChild(body);

    head.addEventListener("click", function () {
      var open = !state.open[job.id];
      state.open[job.id] = open;
      head.setAttribute("aria-expanded", open ? "true" : "false");
      body.hidden = !open;
    });
    return card;
  }

  /* ---------- Auswahl ---------- */

  function matchesSearch(job, needle) {
    if (!needle) { return true; }
    var haystack = [job.title, job.club, job.description, job.department,
                    job.location, job.employment_type].join(" ").toLowerCase();
    return needle.split(/\s+/).every(function (word) {
      return haystack.indexOf(word) !== -1;
    });
  }

  function visibleJobs() {
    var needle = state.search.trim().toLowerCase();
    return state.jobs.filter(function (job) {
      if (state.view === "closed") {
        if (job.status !== "geschlossen") { return false; }
      } else if (state.view === "new") {
        if (!isNewSport(job)) { return false; }
      } else {
        if (job.status === "geschlossen") { return false; }
        if (job.priority !== state.view) { return false; }
      }
      if (state.club && job.club_short !== state.club) { return false; }
      return matchesSearch(job, needle);
    });
  }

  function countFor(view) {
    return state.jobs.filter(function (job) {
      if (view === "closed") { return job.status === "geschlossen"; }
      if (view === "new") { return isNewSport(job); }
      return job.status === "offen" && job.priority === view;
    }).length;
  }

  /* ---------- Vereinsansicht ---------- */

  function buildClubCard(short, club) {
    var card = node("div", "club-card");
    card.appendChild(node("h3", null, club.name || short));

    var stats = node("div", "club-stats");
    stats.appendChild(chip((club.open_glb || 0) + "× GLB"));
    stats.appendChild(chip(plural(club.open_sport || 0, "Sportstelle", "Sportstellen")));
    stats.appendChild(chip(plural(club.open_total || 0, "Stelle offen", "Stellen offen")));
    card.appendChild(stats);

    if (club.last_success) {
      card.appendChild(node("p", "club-meta",
        "Letzter erfolgreicher Abruf: " + formatDate(club.last_success)));
    }

    var sources = club.sources || {};
    Object.keys(sources).forEach(function (id) {
      var src = sources[id];
      var bits = [src.label || id];
      if (src.manual) {
        bits.push("manuell beobachten");
      } else if (src.last_count !== null && src.last_count !== undefined) {
        bits.push(plural(src.last_count, "Stelle", "Stellen"));
      }
      card.appendChild(node("p", "club-meta", "• " + bits.join(" – ")));
      if (src.manual && src.manual_hint) {
        card.appendChild(node("div", "warn", src.manual_hint));
      }
    });

    if (club.last_error && club.last_error.message) {
      card.appendChild(node("div", "warn",
        "Letzter Fehler (" + formatDate(club.last_error.at) + "): " +
        club.last_error.message));
    }

    var spec = club.speculative || {};
    var specText = {
      yes: "Initiativbewerbung möglich",
      no: "Initiativbewerbung wird nicht angenommen",
      limited: "Initiativbewerbung nur mit geringer Aussicht",
      unknown: "Initiativbewerbung: kein Hinweis auf der Seite"
    }[String(spec.allowed)] || null;
    if (specText) { card.appendChild(node("p", "club-meta", specText)); }
    if (spec.note) { card.appendChild(node("p", "club-meta", spec.note)); }

    var links = node("div", "club-links");
    if (spec.url) {
      var a = node("a", null, "Karriereseite öffnen");
      a.href = spec.url; a.target = "_blank"; a.rel = "noopener noreferrer";
      links.appendChild(a);
    }
    if (club.speculative_portal && club.speculative_portal.url) {
      var b = node("a", null, "Initiativbewerbung");
      b.href = club.speculative_portal.url;
      b.target = "_blank"; b.rel = "noopener noreferrer";
      links.appendChild(b);
    }
    if (links.childNodes.length) { card.appendChild(links); }
    return card;
  }

  /* ---------- Zeichnen ---------- */

  function render() {
    Array.prototype.forEach.call(el.tabs.querySelectorAll("button"), function (b) {
      b.setAttribute("aria-selected", b.dataset.view === state.view ? "true" : "false");
    });
    Array.prototype.forEach.call(el.tabs.querySelectorAll(".count"), function (c) {
      c.textContent = countFor(c.dataset.count);
    });

    var clubsView = state.view === "clubs";
    el.filters.hidden = clubsView;
    el.list.hidden = clubsView;
    el.clubList.hidden = !clubsView;

    if (clubsView) {
      el.clubList.textContent = "";
      el.status.hidden = true;
      Object.keys(state.clubs)
        .sort(function (a, b) {
          return (state.clubs[a].name || a).localeCompare(state.clubs[b].name || b, "de");
        })
        .forEach(function (short) {
          el.clubList.appendChild(buildClubCard(short, state.clubs[short]));
        });
      return;
    }

    var jobs = visibleJobs();
    el.list.textContent = "";
    if (!jobs.length) {
      el.status.hidden = false;
      if (state.search || state.club) {
        el.status.textContent = "Keine Stelle passt zu dieser Suche.";
      } else if (state.view === "new") {
        el.status.textContent = "Gerade keine neue Sportstelle. Hier " +
          "stehen Stellen mit Sportbezug, die nach dem Erstlauf " +
          "dazugekommen sind – " + (state.settings.new_badge_days || 7) +
          " Tage lang. Stellen ohne Sportbezug erscheinen hier nie.";
      } else if (state.view === "A") {
        // Der Grundlagenbereich ist eng gefasst. Ist hier nichts, liegt das
        // in der Regel nicht an einem Fehler, sondern daran, dass solche
        // Stellen selten offen ausgeschrieben werden. Dann hilft der Reiter
        // "Vereine" mit den Initiativbewerbungen weiter.
        el.status.textContent = "Gerade ist keine GLB-Stelle offen. GLB " +
          "heißt hier: NLZ-Mannschaften der Altersklassen U9 bis U11. " +
          "Fußballschulen, Feriencamps und Partnervereine stehen unter " +
          "„Sport“. Für den Grundlagenbereich lohnt der Reiter „Vereine“ " +
          "mit den Initiativbewerbungen.";
      } else {
        el.status.textContent = "In diesem Bereich ist gerade nichts offen.";
      }
      return;
    }
    el.status.hidden = true;
    jobs.forEach(function (job) { el.list.appendChild(buildCard(job)); });
  }

  function renderSummary() {
    var open = state.jobs.filter(function (j) { return j.status === "offen"; });
    var sport = open.filter(function (j) { return j.priority === "A" || j.priority === "B"; });
    var glb = open.filter(function (j) { return j.priority === "A"; });
    el.summary.textContent = plural(sport.length, "Sportstelle", "Sportstellen") +
      " offen, davon " + glb.length + " im Grundlagenbereich · " +
      plural(open.length, "Stelle", "Stellen") + " gesamt";
    el.generated.textContent = state.generated
      ? formatDate(state.generated) + ", " +
        parseDate(state.generated).toLocaleTimeString("de-DE",
          { hour: "2-digit", minute: "2-digit" }) + " Uhr"
      : "–";
  }

  function fillClubFilter() {
    var seen = {};
    state.jobs.forEach(function (j) {
      if (j.club_short && !seen[j.club_short]) { seen[j.club_short] = j.club; }
    });
    Object.keys(seen)
      .sort(function (a, b) { return seen[a].localeCompare(seen[b], "de"); })
      .forEach(function (short) {
        var opt = node("option", null, seen[short]);
        opt.value = short;
        el.clubFilter.appendChild(opt);
      });
  }

  /* ---------- Start ---------- */

  function wire() {
    el.tabs.addEventListener("click", function (ev) {
      var btn = ev.target.closest("button[data-view]");
      if (!btn) { return; }
      state.view = btn.dataset.view;
      render();
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
    el.search.addEventListener("input", function () {
      state.search = el.search.value; render();
    });
    el.clubFilter.addEventListener("change", function () {
      state.club = el.clubFilter.value; render();
    });
    el.infoToggle.addEventListener("click", function () {
      var open = el.infoBox.hidden;
      el.infoBox.hidden = !open;
      el.infoToggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
  }

  function load() {
    fetch(DATA_URL, { cache: "no-cache" })
      .then(function (res) {
        if (!res.ok) { throw new Error("HTTP " + res.status); }
        return res.json();
      })
      .then(function (data) {
        state.jobs = Array.isArray(data.jobs) ? data.jobs : [];
        state.clubs = data.clubs || {};
        state.settings = data.settings || state.settings;
        state.generated = data.generated_at || null;
        state.jobs.sort(function (a, b) {
          return String(b.first_seen || "").localeCompare(String(a.first_seen || ""));
        });
        fillClubFilter();
        renderSummary();
        render();
      })
      .catch(function (err) {
        el.status.hidden = false;
        el.status.textContent = "Die Stellenliste konnte nicht geladen werden (" +
          err.message + "). Beim ersten Aufruf hilft meist ein Neuladen.";
        el.summary.textContent = "Daten nicht verfügbar";
      });
  }

  wire();
  load();

  if ("serviceWorker" in navigator) {
    window.addEventListener("load", function () {
      navigator.serviceWorker.register("sw.js").catch(function () { /* egal */ });
    });
  }
})();
