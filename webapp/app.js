/* Finance bot Mini App. Plain JS, no build step.
 * Screens (hash routes): Home "#/", History "#/history", Report "#/report", Settings "#/settings",
 * new / edit operation "#/op/new" and "#/op/{id}", budgets "#/budgets", cards "#/cards", "#/card/{id}",
 * "#/edit/{id}" and "#/new" (add a card).
 * Every API call sends Telegram.WebApp.initData; the server checks its signature and the ADMINS list.
 * Amounts travel as integers in minor units (amount * 100). */
(function () {
  "use strict";

  var tg = (window.Telegram && window.Telegram.WebApp) || null;
  var app = document.getElementById("app");
  var toastEl = document.getElementById("toast");
  var T = {};  // texts in the user's language, from /api/me
  var LANG = "uz";
  var AI = false;  // AI configured on the server (the report's advice box)
  var CARD_TYPES = ["cash", "uzcard", "humo", "visa", "mastercard"];
  var BRAND = { uzcard: "UZCARD", humo: "HUMO", visa: "VISA", mastercard: "MASTERCARD" };
  var LANG_NAMES = [["uz", "O'ZBEKCHA"], ["ru", "РУССКИЙ"], ["en", "ENGLISH"]];
  var ICON_BACK = '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 5l-7 7 7 7"/></svg>';
  var ICON_CLOSE = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>';
  var ICON_EDIT = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 20h4L19 9l-4-4L4 16v4z"/></svg>';
  var ICON_PLUS = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg>';
  var ICON_SEARCH = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#8FA19B" stroke-width="2.4" stroke-linecap="round" aria-hidden="true"><circle cx="11" cy="11" r="6"/><path d="M20 20l-4.5-4.5"/></svg>';
  var ICON_SPARK = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#FBFAF4" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3l2.2 5.8L20 11l-5.8 2.2L12 19l-2.2-5.8L4 11l5.8-2.2z"/></svg>';
  var TAB_ICONS = {
    home: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linejoin="round" aria-hidden="true"><path d="M4 11l8-7 8 7v9h-5v-6H9v6H4z"/></svg>',
    history: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><path d="M5 6h14M5 12h14M5 18h9"/></svg>',
    plus: '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg>',
    report: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><path d="M5 20V10M12 20V4M19 20v-7"/></svg>',
    settings: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><path d="M4 7h10M18 7h2M4 17h4M12 17h8"/><circle cx="16" cy="7" r="2"/><circle cx="10" cy="17" r="2"/></svg>'
  };

  // ---- Helpers ----

  function tr(key, vars) {
    var text = T[key] || key;
    if (vars) {
      Object.keys(vars).forEach(function (k) { text = text.split("{" + k + "}").join(vars[k]); });
    }
    return text;
  }

  // h("div", {class: "x", onclick: fn}, child, "text", ...) -> element; strings become text nodes
  function h(tag, attrs) {
    var el = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      var v = attrs[k];
      if (v === null || v === undefined || v === false) return;
      if (k.slice(0, 2) === "on") el.addEventListener(k.slice(2), v);
      else if (k === "html") el.innerHTML = v;  // only for the static icons above
      else if (k === "style") el.style.cssText = v;
      else el.setAttribute(k, v === true ? "" : v);
    });
    for (var i = 2; i < arguments.length; i++) add(el, arguments[i]);
    return el;
  }

  function add(el, child) {
    if (child === null || child === undefined || child === false) return;
    if (Array.isArray(child)) { child.forEach(function (c) { add(el, c); }); return; }
    el.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
  }

  // No-break spaces between thousands, so an amount never wraps
  function group(digits) { return digits.replace(/\B(?=(\d{3})+(?!\d))/g, " "); }

  // 125000000 (minor) -> "1 250 000"; USD keeps cents: 12345 -> "123.45"
  function num(minor, currency) {
    var abs = Math.abs(minor);
    var whole = Math.floor(abs / 100), cents = abs % 100;
    if (currency === "USD") return group(String(whole)) + "." + (cents < 10 ? "0" : "") + cents;
    return group(String(Math.round(abs / 100)));
  }

  function sign(minor) { return minor < 0 ? "−" : ""; }

  // Amount with its currency: "1 250 000 so'm" / "$123.45"
  function money(minor, currency) {
    if (currency === "USD") return sign(minor) + "$" + num(minor, currency);
    return sign(minor) + num(minor, currency) + " " + tr("sum");
  }

  // Amount for list columns: "1 250 000" / "$123.45"
  function short(minor, currency) {
    return sign(minor) + (currency === "USD" ? "$" : "") + num(minor, currency);
  }

  // "1 250 000,50" -> 125000050; null when invalid
  function parseMinor(text) {
    var clean = String(text || "").replace(/[\s  ']/g, "").replace(",", ".");
    if (!clean) return 0;
    if (!/^\d{1,13}(\.\d{1,2})?$/.test(clean)) return null;
    var parts = clean.split(".");
    var cents = parts[1] ? (parts[1] + "0").slice(0, 2) : "00";
    return parseInt(parts[0], 10) * 100 + parseInt(cents, 10);
  }

  function minorToInput(minor) {
    if (!minor) return "";
    var abs = Math.abs(minor), whole = Math.floor(abs / 100), cents = abs % 100;
    return group(String(whole)) + (cents ? "." + (cents < 10 ? "0" : "") + cents : "");
  }

  // Live grouping while typing: "1250000" -> "1 250 000", decimals kept ("12.5")
  function groupTyped(text) {
    var clean = String(text || "").replace(/[^\d.,]/g, "").replace(",", ".");
    var dot = clean.indexOf(".");
    var whole = dot < 0 ? clean : clean.slice(0, dot);
    var frac = dot < 0 ? null : clean.slice(dot + 1).replace(/\./g, "").slice(0, 2);
    whole = whole.replace(/^0+(?=\d)/, "").slice(0, 13);
    return group(whole) + (frac === null ? "" : "." + frac);
  }

  // "12850.37" -> "12 850.37"
  function rateText(rate) {
    var parts = String(rate).split(".");
    return group(parts[0]) + (parts[1] ? "." + parts[1].slice(0, 2) : "");
  }

  function pad(n) { return (n < 10 ? "0" : "") + n; }
  function ddmm(iso) { var p = iso.split("-"); return p[2] + "." + p[1]; }
  function isoDay(d) { return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()); }
  function todayIso() { return isoDay(new Date()); }
  function yesterdayIso() { var d = new Date(); d.setDate(d.getDate() - 1); return isoDay(d); }
  function nowLocal() { var d = new Date(); return isoDay(d) + "T" + pad(d.getHours()) + ":" + pad(d.getMinutes()); }

  function tagInfo(acc) {
    if (acc.is_credit) return { text: tr("tag_credit"), color: "var(--red)" };
    if (acc.card_type === "cash") return { text: tr("tag_cash"), color: "var(--ink)" };
    if (BRAND[acc.card_type]) return { text: BRAND[acc.card_type], color: "var(--blue)" };
    return { text: tr("tag_card"), color: "var(--blue)" };
  }

  function stampInfo(acc) {
    var label = acc.card_type === "cash" ? tr("tag_cash") : (BRAND[acc.card_type] || tr(acc.is_credit ? "tag_credit" : "tag_card"));
    var color = acc.is_credit ? "var(--red)" : (acc.card_type === "cash" ? "var(--ink)" : "var(--blue)");
    return { text: label, color: color };
  }

  // Chip label of an account: its name, plus "·1234" when the name does not show the digits
  function accLabel(acc) {
    var name = acc.name;
    if (acc.last4 && name.indexOf(acc.last4) < 0) name += " ·" + acc.last4;
    return name;
  }

  function opTitle(op) {
    if (op.kind === "transfer") return tr("op_transfer");
    var name = op.category || tr(op.kind === "income" ? "op_income" : "op_expense");
    return op.subcategory ? name + " › " + op.subcategory : name;
  }

  function opAmount(op, cls) {
    if (op.kind === "transfer") return h("span", { class: cls + " mute" }, short(op.amount_minor, op.currency));
    var income = op.kind === "income";
    return h("span", { class: cls + (income ? " blue" : "") }, (income ? "+" : "−") + short(op.amount_minor, op.currency));
  }

  var toastTimer = null;
  function toast(text, isError) {
    toastEl.textContent = text;
    toastEl.className = "toast" + (isError ? " err" : "");
    toastEl.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { toastEl.hidden = true; }, isError ? 3600 : 2600);
  }

  function haptic(kind) {
    try { if (tg && tg.HapticFeedback) tg.HapticFeedback.notificationOccurred(kind); } catch (e) { /* old client */ }
  }

  function confirmBox(text, done) {
    if (tg && tg.showConfirm && tg.isVersionAtLeast && tg.isVersionAtLeast("6.2")) {
      try { tg.showConfirm(text, done); return; } catch (e) { /* fall back below */ }
    }
    done(window.confirm(text));
  }

  // ---- API ----

  function ApiError(status, code, message) { this.status = status; this.code = code; this.message = message; }

  function api(method, path, body) {
    var opts = { method: method, headers: { "X-Telegram-Init-Data": (tg && tg.initData) || "" } };
    if (body !== undefined) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    return fetch("api/" + path, opts).then(function (res) {
      return res.json().catch(function () { return {}; }).then(function (data) {
        if (!res.ok) throw new ApiError(res.status, data.error || "error", data.message);
        return data;
      });
    });
  }

  function qs(params) {
    return Object.keys(params).filter(function (k) { return params[k] !== null && params[k] !== undefined && params[k] !== ""; })
      .map(function (k) { return encodeURIComponent(k) + "=" + encodeURIComponent(params[k]); }).join("&");
  }

  var ERROR_TEXTS = {
    name: "err_name", last4: "err_last4", last4_taken: "err_last4_taken", amount: "err_amount",
    currency_locked: "err_currency_locked", not_found: "err_not_found", auth: "err_auth", forbidden: "err_forbidden",
    category: "err_category", account: "err_account", same_account: "err_same_account",
    currency_mismatch: "err_currency_mismatch", date: "err_date", note: "err_note", locked: "err_locked",
    start: "err_start", rate: "err_rate", salary_day: "err_salary_day"
  };

  function errorText(err) {
    if (err && err.message && (err.code === "auth" || err.code === "forbidden")) return err.message;
    var key = err && ERROR_TEXTS[err.code];
    return key && T[key] ? T[key] : (T.err_generic || "Error");
  }

  // ---- Navigation ----
  // In-app steps are counted, so Back returns to where the user came from (History -> edit -> History);
  // a screen opened directly falls back to its parent.

  var depth = 0;
  var TAB_ROUTES = ["#/", "#/history", "#/report", "#/settings"];

  function go(hash) { depth++; location.hash = hash; }
  function replace(hash) { location.replace(hash); }
  function tabTo(hash) { depth = 0; replace(hash); }

  function parentOf(hash) {
    var m;
    if ((m = hash.match(/^#\/edit\/(\d+)$/))) return "#/card/" + m[1];
    if (/^#\/card\/\d+$/.test(hash) || hash === "#/new") return "#/cards";
    if (hash === "#/budgets") return "#/settings";
    return "#/";
  }

  function back() {
    if (depth > 0) { depth--; history.back(); return; }
    replace(parentOf(location.hash || "#/"));
  }

  function setBackButton(hash) {
    if (!tg || !tg.BackButton) return;
    if (TAB_ROUTES.indexOf(hash) >= 0 || hash === "") tg.BackButton.hide(); else tg.BackButton.show();
  }

  var renderId = 0;  // a late answer of a screen that was left must not draw over the new one

  function render() {
    var hash = location.hash || "#/";
    renderId++;
    setBackButton(hash);
    window.scrollTo(0, 0);
    app.classList.remove("tabbed");
    var m;
    if ((m = hash.match(/^#\/card\/(\d+)$/))) return showCard(+m[1]);
    if ((m = hash.match(/^#\/edit\/(\d+)$/))) return showForm(+m[1]);
    if ((m = hash.match(/^#\/op\/(\d+)$/))) return showOp(+m[1]);
    if (hash === "#/op/new") return showOp(null);
    if (hash === "#/new") return showForm(null);
    if (hash === "#/cards") return showCards();
    if (hash === "#/history") return showHistory();
    if (hash === "#/report") return showReport();
    if (hash === "#/settings") return showSettings();
    if (hash === "#/budgets") return showBudgets();
    return showHome();
  }

  // Load data for the current screen; drop the answer if the user has moved on meanwhile
  function load(promise, draw) {
    var id = renderId;
    return promise.then(function (data) { if (id === renderId) draw(data); })
      .catch(function (err) { if (id === renderId) failed(err); });
  }

  function mount() {
    app.textContent = "";
    for (var i = 0; i < arguments.length; i++) add(app, arguments[i]);
  }

  function loading(tab) { mount(h("div", { class: "center" }, T.loading || "…"), tab ? tabBar(tab) : null); if (tab) app.classList.add("tabbed"); }

  function failed(err) {
    mount(h("div", { class: "center" }, errorText(err)));
  }

  function topBar(title, onBack, extra, icon) {
    return h("div", { class: "bar" },
      h("button", { class: "icon-btn", type: "button", "aria-label": icon === ICON_CLOSE ? tr("close") : tr("back"), html: icon || ICON_BACK, onclick: onBack }),
      h("span", { class: "title" }, title),
      extra || null);
  }

  function hero(title, right) {
    return h("div", { class: "hero" + (right ? " split" : "") },
      h("div", { class: "stack" },
        h("span", { class: "brand" }, "FINANCE AI"),
        h("span", { class: "h1 sm" }, title)),
      right || null);
  }

  function tabBar(active) {
    function tab(key, hash, label) {
      return h("button", { class: "tab" + (active === key ? " on" : ""), type: "button", "aria-current": active === key ? "page" : null,
        onclick: function () { if (active !== key) tabTo(hash); } },
        h("span", { html: TAB_ICONS[key], style: "display:flex" }), label);
    }
    return h("nav", { class: "tabs", "aria-label": tr("tabs_label") },
      tab("home", "#/", tr("tab_home")),
      tab("history", "#/history", tr("tab_history")),
      h("button", { class: "tab", type: "button", "aria-label": tr("add_op"), onclick: function () { go("#/op/new"); } },
        h("span", { class: "plus", html: TAB_ICONS.plus })),
      tab("report", "#/report", tr("tab_report")),
      tab("settings", "#/settings", tr("tab_settings")));
  }

  function withTabs(tab, nodes) {
    mount(nodes, tabBar(tab));
    app.classList.add("tabbed");
  }

  function seg(items, current, onPick, small, disabled) {
    return h("div", { class: "seg-wrap", role: "tablist" }, items.map(function (item) {
      var on = item[0] === current;
      return h("button", { class: "seg" + (small ? " sm" : "") + (on ? " on" : ""), type: "button", role: "tab",
        "aria-selected": on ? "true" : "false", disabled: disabled ? true : null,
        onclick: function () { if (!on) onPick(item[0]); } }, item[1]);
    }));
  }

  function rateSource(rate) {
    if (!rate) return "";
    var src = tr("rate_src_" + rate.source);
    return rate.date && rate.source !== "manual" ? src + ", " + ddmm(rate.date) : src;
  }

  // ---- Home ----

  function showHome() {
    loading("home");
    load(api("GET", "home"), drawHome);
  }

  function pairValue(pair, signChar, cls) {
    var nodes = [h("span", { class: "v " + cls }, (pair.uzs_minor ? signChar : "") + num(pair.uzs_minor, "UZS"))];
    if (pair.usd_minor) nodes.push(h("span", { class: "x " + cls }, signChar + "$" + num(pair.usd_minor, "USD")));
    return nodes;
  }

  function drawHome(data) {
    var months = tr("months").split(",");
    var rateNode = data.rate
      ? h("div", { class: "rate" }, h("span", null, tr("rate_line", { rate: rateText(data.rate.rate) })), h("span", { class: "src" }, rateSource(data.rate)))
      : h("div", { class: "rate" }, h("span", null, tr("rate_none")));

    var total = h("div", { class: "slip home-total" },
      h("div", { class: "perf b" }),
      h("span", { class: "cap mute" }, tr("total_balance")),
      h("span", { class: "big" }, money(data.balance.uzs_minor, "UZS")),
      data.balance.usd_minor ? h("span", { class: "mute sub" }, "+ " + money(data.balance.usd_minor, "USD")) : null,
      h("div", { class: "sep" }),
      h("div", { class: "month" },
        h("div", null, h("span", { class: "cap mute" }, tr("cap_expense")), pairValue(data.expense, "−", "red")),
        h("div", null, h("span", { class: "cap mute" }, tr("cap_income")), pairValue(data.income, "+", "blue"))),
      data.limit ? limitBlock(data.limit) : null);

    var strip = h("div", { class: "strip" }, data.accounts.map(function (acc) {
      var tag = tagInfo(acc);
      var amount = acc.is_credit ? -acc.debt_minor : acc.balance_minor;
      return h("button", { class: "slip mcard", type: "button", onclick: function () { go("#/card/" + acc.id); } },
        h("span", { class: "t", style: "color:" + tag.color }, tag.text + (acc.last4 ? " ·" + acc.last4 : "")),
        h("span", { class: "n" + (acc.is_credit && acc.debt_minor ? " red" : "") }, short(amount, acc.currency)));
    }));
    if (!data.accounts.length) {
      strip.appendChild(h("button", { class: "mcard add", type: "button", onclick: function () { go("#/new"); } }, "+ " + tr("add_card")));
    }

    var ops = h("div", { class: "slip ops home" }, h("div", { class: "perf b" }));
    if (!data.recent.length) ops.appendChild(h("div", { class: "mute", style: "font-size:14px;text-align:center" }, tr("no_ops")));
    data.recent.forEach(function (op) { ops.appendChild(opLine(op)); });

    withTabs("home", [
      hero(months[data.month - 1] || "", rateNode),
      total,
      h("div", { class: "section tight" },
        h("span", { class: "name" }, tr("sec_cards")),
        h("button", { class: "link", type: "button", onclick: function () { go("#/cards"); } }, tr("link_all"))),
      strip,
      h("div", { class: "section tight", style: "padding-top:6px" },
        h("span", { class: "name" }, tr("recent_ops")),
        h("button", { class: "link", type: "button", onclick: function () { tabTo("#/history"); } }, tr("link_history"))),
      ops
    ]);
  }

  function limitBlock(limit) {
    var over = limit.spent_minor > limit.limit_minor;
    var text = over ? tr("limit_over", { percent: limit.percent })
      : tr("limit_left", { percent: limit.percent, amount: num(limit.left_minor, "UZS") });
    return h("div", { class: "limit" },
      h("div", { class: "lh" }, h("span", null, tr("limit_title")), h("span", { class: over ? "red" : "mute" }, text)),
      h("div", { class: "meter" + (over ? " over" : "") }, h("div", { style: "width:" + Math.min(limit.percent, 100) + "%" })));
  }

  function opLine(op) {
    return h("button", { class: "op tap", type: "button", onclick: function () { go("#/op/" + op.id); } },
      h("span", { class: "d mute" }, ddmm(op.date)),
      h("span", { class: "c" }, op.kind === "transfer" ? tr("op_transfer") : (op.category || tr(op.kind === "income" ? "op_income" : "op_expense"))),
      h("span", { class: "ld" }),
      opAmount(op, "a"));
  }

  // ---- New / edit operation ----

  function showOp(txId) {
    loading();
    var calls = [api("GET", "form")];
    if (txId) calls.push(api("GET", "operations/" + txId));
    load(Promise.all(calls), function (res) { drawOp(res[0], res[1] ? res[1].operation : null); });
  }

  function drawOp(form, op) {
    var editing = !!op;
    var accounts = form.accounts.slice();
    // An archived account of the edited operation is still shown (only the active ones can be picked anew)
    [op && op.account, op && op.to_account].forEach(function (acc) {
      if (acc && !accounts.some(function (a) { return a.id === acc.id; })) accounts.push(acc);
    });
    var state = {
      kind: op ? op.kind : "expense",
      currency: op ? op.currency : "UZS",
      category: op ? op.category : null,
      sub: op ? op.subcategory : null,
      account: op ? op.account.id : null,
      from: op && op.kind === "transfer" ? op.account.id : null,
      to: op && op.to_account ? op.to_account.id : null,
      when: op ? op.occurred_at : null  // null = now
    };
    if (!op && !accounts.some(function (a) { return a.currency === "UZS"; }) && accounts.length) state.currency = accounts[0].currency;

    var amount = h("input", { class: "amount-in", inputmode: "decimal", autocomplete: "off", "aria-label": tr("lbl_amount"),
      placeholder: "0", value: op ? minorToInput(op.amount_minor) : "" });
    var curLabel = h("span", { class: "cur" });
    var note = h("input", { class: "inp sm", maxlength: "200", autocomplete: "off", "aria-label": tr("lbl_note"),
      placeholder: tr("note_ph"), value: op && op.note ? op.note : "" });
    var dateShown = h("span", { class: "shown" });
    var dateInput = h("input", { type: "datetime-local", "aria-label": tr("lbl_date"), max: nowLocal(), value: state.when || nowLocal() });
    var segBox = h("div");
    var curChips = h("span", { style: "display:flex;gap:6px;margin-top:4px" });
    var middle = h("div", { style: "display:flex;flex-direction:column;gap:18px" });
    var saveBtn = h("button", { class: "btn primary", type: "button", onclick: save }, tr("save"));

    amount.addEventListener("input", function () {
      var before = amount.value;
      var grouped = groupTyped(before);
      if (grouped !== before) amount.value = grouped;
      amount.classList.remove("bad");
    });
    dateInput.addEventListener("change", function () {
      state.when = dateInput.value || null;
      if (state.when && state.when > nowLocal()) state.when = null;
      drawDate();
    });
    dateInput.addEventListener("click", function () {
      try { if (dateInput.showPicker) dateInput.showPicker(); } catch (e) { /* not allowed here */ }
    });

    function drawDate() {
      var v = state.when || nowLocal();
      var day = v.slice(0, 10), time = v.slice(11, 16);
      dateShown.textContent = day === todayIso() ? tr("today_at", { time: time })
        : day === yesterdayIso() ? tr("yesterday_at", { time: time }) : ddmm(day) + "." + day.slice(0, 4) + ", " + time;
    }

    function ofCurrency() { return accounts.filter(function (a) { return a.currency === state.currency && (a.is_active !== false || a.id === state.account || a.id === state.from || a.id === state.to); }); }

    function chip(label, on, onclick, cls, disabled) {
      return h("button", { class: "chip" + (cls ? " " + cls : "") + (on ? " on" : ""), type: "button", "aria-pressed": on ? "true" : "false",
        disabled: disabled ? true : null, onclick: onclick }, label);
    }

    function accountChips(selected, pick, lockedTo) {
      var list = ofCurrency();
      if (!list.length) return h("span", { class: "empty-line" }, tr("no_acc_currency", { currency: state.currency }));
      return h("div", { class: "chips" }, list.map(function (acc) {
        var locked = lockedTo !== undefined && lockedTo !== acc.id;
        var label = accLabel(acc) + (acc.is_active === false ? " (" + tr("archived_tag") + ")" : "");
        return chip(label, selected === acc.id, function () { pick(acc.id); sync(); }, null, locked || (acc.is_active === false && selected !== acc.id));
      }));
    }

    function sync() {
      segBox.textContent = "";
      segBox.appendChild(seg([["expense", tr("seg_expense")], ["income", tr("seg_income")], ["transfer", tr("seg_transfer")]],
        state.kind, function (kind) { state.kind = kind; state.category = null; state.sub = null; sync(); }, false, editing));

      curLabel.textContent = state.currency === "USD" ? "USD" : tr("sum");
      curChips.textContent = "";
      ["UZS", "USD"].forEach(function (cur) {
        curChips.appendChild(chip(cur, state.currency === cur, function () {
          state.currency = cur; state.account = state.from = state.to = null; sync();
        }, "s" + (state.currency === cur ? "" : " off"), editing && state.currency !== cur));
      });

      var valid = ofCurrency();
      function firstValid() { var a = valid.filter(function (x) { return x.is_active !== false; })[0]; return a ? a.id : null; }
      if (!valid.some(function (a) { return a.id === state.account; })) state.account = firstValid();

      middle.textContent = "";
      if (state.kind === "transfer") {
        if (!valid.some(function (a) { return a.id === state.from; })) state.from = firstValid();
        if (!valid.some(function (a) { return a.id === state.to; }) || state.to === state.from) {
          var other = valid.filter(function (a) { return a.id !== state.from && a.is_active !== false; })[0];
          state.to = other ? other.id : null;
        }
        middle.appendChild(h("div", { class: "fld gap8" }, h("span", { class: "lbl" }, tr("lbl_from")),
          accountChips(state.from, function (id) { if (state.to === id) state.to = state.from; state.from = id; }, editing ? state.from : undefined)));
        middle.appendChild(h("div", { class: "fld gap8" }, h("span", { class: "lbl" }, tr("lbl_to")),
          accountChips(state.to, function (id) { if (state.from === id) state.from = state.to; state.to = id; }, editing ? state.to : undefined)));
      } else {
        var cats = form.categories[state.kind] || [];
        var catBox = h("div", { class: "chips" }, cats.map(function (c) {
          return chip(c.name, state.category === c.name, function () {
            if (state.category !== c.name) { state.category = c.name; state.sub = null; }
            sync();
          });
        }));
        if (!cats.length) catBox.appendChild(h("span", { class: "empty-line" }, tr("no_categories")));
        var current = cats.filter(function (c) { return c.name === state.category; })[0];
        var subBox = null;
        if (current && current.subcategories.length) {
          subBox = h("div", { class: "chips" }, current.subcategories.map(function (s) {
            return chip(s, state.sub === s, function () { state.sub = state.sub === s ? null : s; sync(); }, "sub");
          }));
        }
        middle.appendChild(h("div", { class: "fld gap8" }, h("span", { class: "lbl" }, tr("lbl_category")), catBox, subBox));
        middle.appendChild(h("div", { class: "fld gap8" },
          h("span", { class: "lbl" }, tr(state.kind === "income" ? "lbl_account_in" : "lbl_payment")),
          accountChips(state.account, function (id) { state.account = id; })));
      }
      drawDate();
    }

    function fail(key, el) {
      if (el) { el.classList.add("bad"); if (el.focus) el.focus(); }
      toast(tr(key), true);
      haptic("error");
    }

    function save() {
      var minor = parseMinor(amount.value);
      if (!minor) return fail("err_amount", amount);
      var body = { kind: state.kind, amount_minor: minor, note: note.value.trim() || null, occurred_at: state.when };
      if (state.kind === "transfer") {
        if (!state.from || !state.to) return fail("err_account");
        if (state.from === state.to) return fail("err_same_account");
        body.from_account_id = state.from;
        body.to_account_id = state.to;
      } else {
        if (!state.category) return fail("err_category");
        if (!state.account) return fail("err_account");
        body.currency = state.currency;
        body.category = state.category;
        body.subcategory = state.sub;
        body.account_id = state.account;
      }
      if (!editing && !body.occurred_at) delete body.occurred_at;  // the server stamps "now"
      saveBtn.disabled = true;
      api(editing ? "PUT" : "POST", editing ? "operations/" + op.id : "operations", body).then(function (data) {
        haptic("success");
        if (data.over_limit && data.over_limit.length) toast(tr("warn_over_limit", { names: data.over_limit.join(", ") }), true);
        else toast(tr("saved"));
        back();
      }).catch(function (err) {
        saveBtn.disabled = false;
        haptic("error");
        if (err.code === "amount") amount.classList.add("bad");
        toast(errorText(err), true);
      });
    }

    function remove() {
      confirmBox(tr(op.kind === "transfer" ? "confirm_delete_transfer" : "confirm_delete_op"), function (ok) {
        if (!ok) return;
        api("DELETE", "operations/" + op.id).then(function () {
          haptic("success");
          toast(tr("op_deleted"));
          back();
        }).catch(function (err) { haptic("error"); toast(errorText(err), true); });
      });
    }

    mount(
      topBar(tr(editing ? "title_editop" : "title_newop"), back, null, ICON_CLOSE),
      segBox,
      h("div", { class: "slip op-form" },
        h("div", { class: "perf t" }), h("div", { class: "perf b" }),
        h("label", { class: "amount-fld" },
          h("span", { class: "lbl" }, tr("lbl_amount")),
          h("span", { class: "amount-row" }, amount, curLabel),
          curChips),
        h("div", { class: "dash" }),
        middle,
        h("div", { class: "grid2" },
          h("label", { class: "fld gap8" }, h("span", { class: "lbl" }, tr("lbl_note")), note),
          h("label", { class: "fld gap8 date-fld" }, h("span", { class: "lbl" }, tr("lbl_date")), dateShown, dateInput))),
      h("div", { class: "spacer" }),
      h("div", { class: "actions" }, saveBtn,
        editing ? h("button", { class: "link-danger", type: "button", onclick: remove }, tr("delete_op")) : null)
    );
    sync();
    if (!editing) setTimeout(function () { try { amount.focus(); } catch (e) { /* ignore */ } }, 50);
  }

  // ---- History ----

  var historyState = { q: "", kind: "all", account: "" };

  function showHistory() {
    var list = h("div", { class: "slip hist" }, h("div", { class: "perf b" }));
    var moreBtn = h("button", { class: "more", type: "button", hidden: true }, tr("load_more"));
    var hint = h("div", { class: "hint-line" }, tr("history_hint"));
    var search = h("input", { "aria-label": tr("search"), placeholder: tr("search_ph"), value: historyState.q, type: "search", enterkeyhint: "search" });
    var filterBox = h("div", { class: "filters" });
    var accounts = [];
    var nextOffset = 0, lastDay = null, busy = false, query = 0;
    var id = renderId;

    function drawFilters() {
      filterBox.textContent = "";
      [["all", tr("f_all")], ["expense", tr("f_expense")], ["income", tr("f_income")]].forEach(function (f) {
        filterBox.appendChild(h("button", { class: "fchip" + (historyState.kind === f[0] ? " on" : ""), type: "button",
          "aria-pressed": historyState.kind === f[0] ? "true" : "false",
          onclick: function () { historyState.kind = f[0]; drawFilters(); reload(); } }, f[1]));
      });
      var select = h("select", { class: "fchip" + (historyState.account ? " on" : ""), "aria-label": tr("f_all_accounts") },
        h("option", { value: "" }, tr("f_all_accounts")));
      accounts.forEach(function (acc) {
        var opt = h("option", { value: String(acc.id) }, accLabel(acc));
        if (String(acc.id) === historyState.account) opt.selected = true;
        select.appendChild(opt);
      });
      select.addEventListener("change", function () { historyState.account = select.value; drawFilters(); reload(); });
      filterBox.appendChild(select);
    }

    function dayLabel(day) {
      var base = day === todayIso() ? tr("day_today") + " · " : day === yesterdayIso() ? tr("day_yesterday") + " · " : "";
      return base + ddmm(day) + (day.slice(0, 4) !== todayIso().slice(0, 4) ? "." + day.slice(0, 4) : "");
    }

    function row(op) {
      var meta = [op.occurred_at.slice(11, 16)];
      if (op.kind === "transfer") meta.push(op.account + " → " + (op.to_account || "?"));
      else meta.push(op.account);
      if (op.note) meta.push(op.note);
      return h("button", { class: "hrow", type: "button", onclick: function () { go("#/op/" + op.id); } },
        h("span", { class: "main" }, h("span", { class: "t" }, opTitle(op)), h("span", { class: "m" }, meta.join(" · "))),
        opAmount(op, "amt"));
    }

    function reload() {
      query++;
      nextOffset = 0; lastDay = null;
      list.textContent = "";
      list.appendChild(h("div", { class: "perf b" }));
      list.appendChild(h("div", { class: "empty mute" }, T.loading || "…"));
      busy = false;
      fetchPage(true);
    }

    function fetchPage(first) {
      if (busy || nextOffset === null) return;
      busy = true;
      var mine = query;
      api("GET", "operations?" + qs({ q: historyState.q.trim(), kind: historyState.kind, account_id: historyState.account, offset: nextOffset, limit: 30 }))
        .then(function (data) {
          if (mine !== query || id !== renderId) return;
          busy = false;
          if (first) { list.textContent = ""; list.appendChild(h("div", { class: "perf b" })); }
          if (first && !data.operations.length) list.appendChild(h("div", { class: "empty mute" }, tr("nothing_found")));
          data.operations.forEach(function (op) {
            if (op.date !== lastDay) {
              if (lastDay !== null) list.appendChild(h("div", { class: "dsep" }));
              list.appendChild(h("div", { class: "day" }, dayLabel(op.date)));
              lastDay = op.date;
            }
            list.appendChild(row(op));
          });
          nextOffset = data.next_offset;
          moreBtn.hidden = nextOffset === null;
          hint.hidden = !data.total;
        })
        .catch(function (err) { if (mine === query) { busy = false; toast(errorText(err), true); } });
    }

    moreBtn.addEventListener("click", function () { fetchPage(false); });
    var timer = null;
    search.addEventListener("input", function () {
      clearTimeout(timer);
      timer = setTimeout(function () { historyState.q = search.value; reload(); }, 300);
    });
    if ("IntersectionObserver" in window) {
      new IntersectionObserver(function (entries) {
        if (entries[0].isIntersecting && !moreBtn.hidden) fetchPage(false);
      }, { rootMargin: "200px" }).observe(moreBtn);
    }

    drawFilters();
    withTabs("history", [
      hero(tr("tab_history")),
      h("label", { class: "search" }, h("span", { html: ICON_SEARCH, style: "display:flex" }), search),
      filterBox, list, hint, moreBtn
    ]);
    reload();
    api("GET", "accounts").then(function (data) {
      if (id !== renderId) return;
      accounts = data.accounts;
      drawFilters();
    }).catch(function () { /* the filter just stays without accounts */ });
  }

  // ---- Report ----

  var reportPeriod = "month";
  var adviceCache = {};

  function showReport() {
    loading("report");
    load(api("GET", "report?period=" + reportPeriod), drawReport);
  }

  function stampFor(change) {
    if (change === null || change === undefined) return null;
    var up = change > 0, down = change < 0;
    var color = up ? "var(--red)" : down ? "var(--blue)" : "var(--ink)";
    var label = up ? tr("stamp_more") : down ? tr("stamp_less") : tr("stamp_same");
    return h("div", { class: "stamp2", style: "color:" + color },
      h("div", null, h("b", null, (up ? "▲ " : down ? "▼ " : "") + Math.abs(change) + "%"), h("span", null, label)));
  }

  function reportSection(data, sec) {
    var cur = sec.currency;
    var maxAmount = sec.categories.length ? sec.categories[0].amount_minor : 0;
    var slip = h("div", { class: "slip rep" }, h("div", { class: "perf t" }), h("div", { class: "perf b" }));
    add(slip, stampFor(sec.change_percent));
    add(slip, h("div", { class: "head" },
      h("span", { class: "cap mute" }, ddmm(data.start) + " — " + ddmm(data.last_day) + " · " + tr("cap_expense") + (cur === "USD" ? " · USD" : "")),
      h("span", { class: "big" }, short(sec.expense_minor, cur)),
      sec.change_percent !== null ? h("span", { class: "mute", style: "font-size:12px" }, tr("vs_" + data.period)) : null));
    add(slip, h("div", { class: "sep" }));
    sec.categories.forEach(function (c, i) {
      var subs = null;
      var btn = h("button", { class: "cat", type: "button", "aria-expanded": "false" },
        h("span", { class: "cr" }, h("span", { class: "nm" }, c.name === "—" ? tr("no_sub") : c.name), h("span", { class: "ld" }), h("span", { class: "a" }, short(c.amount_minor, cur))),
        h("span", { class: "sbar" + (i === 0 ? " hi" : ""), style: "width:" + Math.max(maxAmount ? c.amount_minor * 100 / maxAmount : 0, 2).toFixed(1) + "%" }));
      btn.addEventListener("click", function () {
        if (subs) { subs.remove(); subs = null; btn.setAttribute("aria-expanded", "false"); return; }
        subs = h("div", { class: "subs" }, h("span", { class: "mute", style: "font-size:12px" }, T.loading || "…"));
        btn.after(subs);
        btn.setAttribute("aria-expanded", "true");
        var box = subs;
        api("GET", "report/subcategories?" + qs({ period: data.period, category: c.name, currency: cur, converted: sec.converted ? 1 : 0 })).then(function (res) {
          box.textContent = "";
          res.subcategories.forEach(function (s) {
            box.appendChild(h("div", { class: "cr" }, h("span", { class: "nm" }, s.name || tr("no_sub")), h("span", { class: "ld" }), h("span", { class: "a" }, short(s.amount_minor, cur))));
          });
        }).catch(function (err) { box.textContent = errorText(err); });
      });
      slip.appendChild(btn);
    });
    if (sec.categories.length) add(slip, h("div", { class: "sep" }));
    add(slip, h("div", { class: "tot" }, h("span", null, tr("cap_income")), h("span", { class: "blue" }, (sec.income_minor ? "+" : "") + short(sec.income_minor, cur))));
    add(slip, h("div", { class: "tot" }, h("span", null, tr("remainder")), h("span", { class: sec.balance_minor < 0 ? "red" : "" }, short(sec.balance_minor, cur))));
    return slip;
  }

  function adviceBox(period) {
    if (!AI) return null;
    var cached = adviceCache[period];
    if (cached === null) return null;  // asked before: nothing to say
    var box = h("div", { class: "advice", "aria-live": "polite" }, h("span", { html: ICON_SPARK, style: "display:flex" }));
    var body = h("div", { class: "skel", "aria-label": tr("ai_loading") }, h("i", { style: "width:92%" }), h("i", { style: "width:78%" }), h("i", { style: "width:55%" }));
    box.appendChild(body);
    function fill(text) {
      if (!text) { box.remove(); return; }
      body.replaceWith(h("span", { class: "txt" }, tr("ai_advice") + " " + text));
    }
    if (cached !== undefined) { fill(cached); return box; }
    api("GET", "advice?period=" + period).then(function (res) {
      adviceCache[period] = res.text || null;
      if (reportPeriod === period) fill(res.text);
    }).catch(function () { if (reportPeriod === period) box.remove(); });
    return box;
  }

  function drawReport(data) {
    var periods = [["week", tr("seg_week")], ["month", tr("seg_month")], ["year", tr("seg_year")]];
    var sections = data.sections.length ? data.sections.map(function (sec) { return reportSection(data, sec); })
      : [h("div", { class: "slip rep" }, h("div", { class: "perf t" }), h("div", { class: "perf b" }),
        h("span", { class: "cap mute" }, ddmm(data.start) + " — " + ddmm(data.last_day)),
        h("div", { class: "empty mute", style: "padding:10px 0" }, tr("report_empty")))];
    withTabs("report", [
      hero(tr("tab_report")),
      seg(periods, reportPeriod, function (p) { reportPeriod = p; showReport(); }, true),
      sections,
      data.sections.length ? adviceBox(data.period) : null
    ]);
  }

  // ---- Settings ----

  function showSettings() {
    loading("settings");
    load(api("GET", "settings"), drawSettings);
  }

  function saveSettings(body, after) {
    return api("PUT", "settings", body).then(function (data) {
      haptic("success");
      if (after) after(data);
      return data;
    }).catch(function (err) { haptic("error"); toast(errorText(err), true); throw err; });
  }

  function drawSettings(s) {
    var rateRow, rateEdit;
    var dayN = h("span", { class: "n" }, String(s.salary_day));
    var dayTimer = null;
    var day = s.salary_day;
    var decBtn = h("button", { class: "mini", type: "button", "aria-label": tr("dec") }, "−");
    var incBtn = h("button", { class: "mini", type: "button", "aria-label": tr("inc") }, "+");
    function stepDay(delta) {
      day = Math.min(28, Math.max(1, day + delta));
      dayN.textContent = String(day);
      decBtn.disabled = day <= 1; incBtn.disabled = day >= 28;
      clearTimeout(dayTimer);
      dayTimer = setTimeout(function () { saveSettings({ salary_day: day }); }, 450);
    }
    decBtn.addEventListener("click", function () { stepDay(-1); });
    incBtn.addEventListener("click", function () { stepDay(1); });
    decBtn.disabled = day <= 1; incBtn.disabled = day >= 28;

    var manual = s.rate_manual;
    var rateInput = h("input", { class: "inp sm", inputmode: "decimal", autocomplete: "off", "aria-label": tr("rate_input"),
      placeholder: "12 850", value: manual && s.rate ? rateText(s.rate.rate) : "" });
    var rateSave = h("button", { class: "mini on", type: "button", style: "height:40px" }, tr("save"));
    rateEdit = h("div", { class: "rate-edit", hidden: !manual },
      h("label", { class: "fld" }, h("span", { class: "lbl" }, tr("rate_input")), rateInput), rateSave);
    var autoBtn = h("button", { class: "mini" + (manual ? "" : " on"), type: "button", "aria-pressed": manual ? "false" : "true" }, tr("rate_auto"));
    var manualBtn = h("button", { class: "mini" + (manual ? " on" : ""), type: "button", "aria-pressed": manual ? "true" : "false" }, tr("rate_manual"));
    var rateSub = h("span", null, s.rate ? tr("rate_line", { rate: rateText(s.rate.rate) }) + " · " + rateSource(s.rate) : tr("rate_none"));
    function setRate(data) {
      s = data;
      rateSub.textContent = data.rate ? tr("rate_line", { rate: rateText(data.rate.rate) }) + " · " + rateSource(data.rate) : tr("rate_none");
      autoBtn.classList.toggle("on", !data.rate_manual);
      manualBtn.classList.toggle("on", data.rate_manual);
    }
    autoBtn.addEventListener("click", function () {
      rateEdit.hidden = true;
      manualBtn.classList.remove("on"); autoBtn.classList.add("on");
      if (s.rate_manual) saveSettings({ rate_mode: "auto" }, setRate);
    });
    manualBtn.addEventListener("click", function () {
      rateEdit.hidden = false;
      autoBtn.classList.remove("on"); manualBtn.classList.add("on");
      if (!rateInput.value && s.rate) rateInput.value = rateText(s.rate.rate);
      rateInput.focus();
    });
    rateSave.addEventListener("click", function () {
      var value = rateInput.value.replace(/[\s  ]/g, "").replace(",", ".");
      if (!/^\d{1,7}(\.\d{1,6})?$/.test(value) || !(parseFloat(value) > 0)) { rateInput.classList.add("bad"); toast(tr("err_rate"), true); return; }
      rateInput.classList.remove("bad");
      saveSettings({ rate_mode: "manual", rate: value }, function (data) { setRate(data); toast(tr("rate_saved")); });
    });
    rateRow = h("div", { class: "srow top" }, h("span", { class: "k" }, h("b", null, tr("set_rate")), rateSub),
      h("span", { style: "display:flex;gap:4px" }, autoBtn, manualBtn));

    function switchRow(kind, title, hint) {
      var on = s["advice_" + kind];
      var sw = h("button", { class: "sw" + (on ? "" : " off"), type: "button", role: "switch", "aria-checked": on ? "true" : "false",
        "aria-label": title + ": " + tr(on ? "sw_on" : "sw_off") });
      sw.addEventListener("click", function () {
        var next = !s["advice_" + kind];
        var body = {}; body["advice_" + kind] = next;
        sw.disabled = true;
        saveSettings(body, function (data) {
          s = data;
          sw.classList.toggle("off", !next);
          sw.setAttribute("aria-checked", next ? "true" : "false");
          sw.setAttribute("aria-label", title + ": " + tr(next ? "sw_on" : "sw_off"));
        }).then(function () { sw.disabled = false; }, function () { sw.disabled = false; });
      });
      return h("div", { class: "srow" }, h("span", { class: "k" }, h("b", null, title), h("span", null, hint)), sw);
    }

    var langs = h("div", { class: "slip langs" }, h("div", { class: "perf b" }), LANG_NAMES.map(function (l) {
      return h("button", { class: "mini big" + (LANG === l[0] ? " on" : ""), type: "button", lang: l[0], "aria-pressed": LANG === l[0] ? "true" : "false",
        onclick: function () {
          if (LANG === l[0]) return;
          saveSettings({ lang: l[0] }).then(function () { return loadTexts(); }).then(function () { render(); });
        } }, l[1]);
    }));

    withTabs("settings", [
      hero(tr("title_settings")),
      h("div", { class: "sec" }, tr("sec_money")),
      h("div", { class: "slip sslip" },
        h("button", { class: "srow", type: "button", onclick: function () { go("#/cards"); } },
          h("span", { class: "k" }, h("b", null, tr("set_cards")), h("span", null, tr("accounts_count", { n: s.accounts_count }))), h("span", { class: "v" }, "›")),
        h("div", { class: "dash" }),
        h("div", { class: "srow" }, h("span", { class: "k" }, h("b", null, tr("set_salary")), h("span", null, tr("set_salary_hint"))),
          h("span", { class: "stepper" }, decBtn, dayN, incBtn)),
        h("div", { class: "dash" }),
        rateRow, rateEdit,
        h("div", { class: "dash" }),
        h("button", { class: "srow", type: "button", onclick: function () { go("#/budgets"); } },
          h("span", { class: "k" }, h("b", null, tr("set_budgets")), h("span", null, tr("budgets_count", { n: s.budgets_count }))), h("span", { class: "v" }, "›"))),
      h("div", { class: "sec" }, tr("sec_ai")),
      h("div", { class: "slip sslip" },
        switchRow("weekly", tr("adv_weekly"), tr("adv_weekly_hint")),
        h("div", { class: "dash" }),
        switchRow("monthly", tr("adv_monthly"), tr("adv_monthly_hint"))),
      s.ai_configured ? null : h("div", { class: "note-dark" }, tr("ai_off_note")),
      h("div", { class: "sec" }, tr("sec_lang")),
      langs
    ]);
  }

  // ---- Budgets ----

  function showBudgets() {
    loading();
    load(api("GET", "budgets"), drawBudgets);
  }

  function drawBudgets(data, editing) {
    var list = h("div", { class: "slip budgets" }, h("div", { class: "perf b" }));
    if (!data.budgets.length) list.appendChild(h("div", { class: "empty mute" }, tr("budget_empty")));
    data.budgets.forEach(function (b, i) {
      if (i) list.appendChild(h("div", { class: "dash" }));
      var over = b.spent_minor >= b.limit_minor;
      list.appendChild(h("button", { class: "brow", type: "button", onclick: function () { drawBudgets(data, b); } },
        h("span", { class: "lh" }, h("span", { class: "nm" }, b.category), h("span", { class: over ? "red" : "" }, b.percent + "%")),
        h("span", { class: "meter" + (over ? " over" : ""), style: "display:block" }, h("span", { style: "display:block;width:" + Math.min(b.percent, 100) + "%" })),
        h("span", { class: "mm" }, short(b.spent_minor, b.currency) + " / " + short(b.limit_minor, b.currency))));
    });

    var formBox = editing ? budgetForm(data, editing === true ? null : editing) : null;
    mount(
      topBar(tr("title_budgets"), back),
      h("div", { class: "note", style: "padding:0 20px 12px" }, tr("budget_period", { start: ddmm(data.period.start), end: ddmm(data.period.last_day) })),
      formBox,
      formBox ? h("div", { style: "height:18px" }) : null,
      list,
      h("div", { class: "note" }, tr("budget_note")),
      h("div", { class: "spacer" }),
      editing ? null : h("div", { class: "actions" },
        h("button", { class: "btn primary", type: "button", onclick: function () { drawBudgets(data, true); } },
          h("span", { html: ICON_PLUS, style: "display:flex" }), tr("budget_add")))
    );
    if (formBox) window.scrollTo(0, 0);
  }

  function budgetForm(data, budget) {
    var state = { category: budget ? budget.category : null, currency: budget ? budget.currency : "UZS" };
    var amount = h("input", { class: "inp", inputmode: "decimal", autocomplete: "off", "aria-label": tr("lbl_month_limit"),
      placeholder: "0", value: budget ? minorToInput(budget.limit_minor) : "" });
    amount.addEventListener("input", function () { var g = groupTyped(amount.value); if (g !== amount.value) amount.value = g; amount.classList.remove("bad"); });
    var catBox = h("div", { class: "chips" });
    var curBox = h("div", { style: "display:flex;gap:8px" });
    function sync() {
      catBox.textContent = "";
      (budget ? [budget.category] : data.categories).forEach(function (name) {
        var taken = !budget && data.budgets.some(function (b) { return b.category === name; });
        catBox.appendChild(h("button", { class: "chip" + (state.category === name ? " on" : ""), type: "button",
          disabled: taken ? true : null,
          onclick: function () { state.category = name; sync(); } }, name));
      });
      curBox.textContent = "";
      ["UZS", "USD"].forEach(function (cur) {
        curBox.appendChild(h("button", { class: "chip" + (state.currency === cur ? " on" : ""), type: "button", style: "flex:1",
          onclick: function () { state.currency = cur; sync(); } }, cur));
      });
    }
    var saveBtn = h("button", { class: "btn primary", type: "button" }, tr("save"));
    saveBtn.addEventListener("click", function () {
      var minor = parseMinor(amount.value);
      if (!state.category) { toast(tr("err_category"), true); return; }
      if (!minor) { amount.classList.add("bad"); toast(tr("err_amount"), true); return; }
      saveBtn.disabled = true;
      api("PUT", "budgets", { category: state.category, currency: state.currency, amount_minor: minor }).then(function () {
        haptic("success"); toast(tr("saved")); showBudgets();
      }).catch(function (err) { saveBtn.disabled = false; haptic("error"); toast(errorText(err), true); });
    });
    var del = budget ? h("button", { class: "link-danger", type: "button", style: "color:var(--debt)", onclick: function () {
      confirmBox(tr("confirm_budget_delete", { name: budget.category }), function (ok) {
        if (!ok) return;
        api("DELETE", "budgets?" + qs({ category: budget.category })).then(function () {
          haptic("success"); toast(tr("budget_deleted")); showBudgets();
        }).catch(function (err) { haptic("error"); toast(errorText(err), true); });
      });
    } }, tr("budget_delete")) : null;
    sync();
    return h("div", { class: "slip bform" },
      h("div", { class: "perf t" }), h("div", { class: "perf b" }),
      h("span", { class: "cap" }, tr(budget ? "budget_edit" : "budget_new")),
      h("div", { class: "fld" }, h("span", { class: "lbl" }, tr("lbl_category")), catBox),
      h("div", { class: "grid2" },
        h("label", { class: "fld" }, h("span", { class: "lbl" }, tr("lbl_month_limit")), amount),
        h("div", { class: "fld" }, h("span", { class: "lbl" }, tr("lbl_currency")), curBox)),
      saveBtn,
      h("div", { class: "row2" },
        h("button", { class: "btn paper", type: "button", style: "border:2px solid var(--ink)", onclick: showBudgets }, tr("cancel"))),
      del);
  }

  // ---- Cards: list ----

  function showCards() {
    loading();
    load(api("GET", "accounts"), function (data) {
      var accounts = data.accounts;
      var hasUsd = accounts.some(function (a) { return a.currency === "USD"; });
      var sub = (hasUsd ? "+ " + money(data.totals.USD, "USD") + " · " : "") + tr("accounts_count", { n: data.count });

      var list = h("div", { class: "slip list" });
      if (!accounts.length) list.appendChild(h("div", { class: "empty mute" }, tr("no_accounts")));
      accounts.forEach(function (acc, i) {
        if (i) list.appendChild(h("div", { class: "dash", style: "margin: 0 16px" }));
        list.appendChild(accountRow(acc));
      });

      mount(
        h("div", { class: "hero" },
          h("span", { class: "brand" }, "FINANCE AI"),
          h("span", { class: "h1" }, tr("title_main"))),
        h("div", { class: "slip total" },
          h("div", { class: "perf b" }),
          h("span", { class: "mute lbl-sm" }, tr("total_balance")),
          h("span", { class: "big" }, money(data.totals.UZS, "UZS")),
          h("span", { class: "mute sub" }, sub)),
        h("div", { class: "section" },
          h("span", { class: "name" }, tr("section_accounts")),
          h("span", { class: "hint" }, tr("col_balance"))),
        list,
        h("div", { class: "spacer" }),
        h("div", { class: "actions" },
          h("button", { class: "btn primary", type: "button", onclick: function () { go("#/new"); } },
            h("span", { html: ICON_PLUS, style: "display:flex" }), tr("add_card")))
      );
    });
  }

  function accountRow(acc) {
    var tag = tagInfo(acc);
    var meta = [];
    if (acc.last4) meta.push("•••• " + acc.last4);
    if (acc.is_credit && acc.credit_limit_minor) meta.push(tr("limit_line", { amount: num(acc.credit_limit_minor, acc.currency) }));
    if (acc.currency === "USD") meta.push("USD");
    var amount = acc.is_credit
      ? h("span", { class: "amt red" }, short(-acc.debt_minor, acc.currency))
      : h("span", { class: "amt" }, short(acc.balance_minor, acc.currency));
    return h("button", { class: "row", type: "button", onclick: function () { go("#/card/" + acc.id); } },
      h("span", { class: "tag", style: "color:" + tag.color }, tag.text),
      h("span", { class: "main" },
        h("span", { class: "nm" }, acc.name),
        meta.length ? h("span", { class: "meta mute" }, meta.join(" · ")) : null),
      amount);
  }

  // ---- Cards: add / edit ----

  function showForm(accountId) {
    if (accountId === null) return drawForm(null);
    loading();
    load(api("GET", "accounts/" + accountId), function (data) { drawForm(data.account); });
  }

  function drawForm(acc) {
    var state = {
      type: acc ? (acc.card_type || (acc.kind === "cash" ? "cash" : "uzcard")) : "uzcard",
      currency: acc ? acc.currency : "UZS",
      credit: acc ? acc.is_credit : false
    };

    var name = h("input", { class: "inp", maxlength: "40", autocomplete: "off", "aria-label": tr("lbl_name"), value: acc ? acc.name : "" });
    var last4 = h("input", { class: "inp", inputmode: "numeric", maxlength: "4", pattern: "[0-9]*", autocomplete: "off", "aria-label": tr("lbl_last4"), value: acc && acc.last4 ? acc.last4 : "", placeholder: "0000" });
    var balance = h("input", { class: "inp", inputmode: "decimal", autocomplete: "off", "aria-label": tr("lbl_balance"),
      value: acc ? minorToInput(acc.is_credit ? acc.debt_minor : acc.balance_minor) : "", placeholder: "0" });
    var limit = h("input", { class: "inp", inputmode: "decimal", autocomplete: "off", "aria-label": tr("lbl_limit"),
      value: acc && acc.is_credit ? minorToInput(acc.credit_limit_minor) : "", placeholder: "0" });
    var credit = h("input", { type: "checkbox" });
    credit.checked = state.credit;

    var typeChips = CARD_TYPES.map(function (type) {
      return h("button", { class: "chip", type: "button", "data-v": type, onclick: function () { state.type = type; sync(); } },
        type === "cash" ? tr("tag_cash") : BRAND[type]);
    });
    var curChips = ["UZS", "USD"].map(function (cur) {
      return h("button", { class: "chip", type: "button", style: "flex: 1", "data-v": cur, onclick: function () { state.currency = cur; sync(); } }, cur);
    });

    var balanceLbl = h("span", { class: "lbl" });
    var limitFld = h("label", { class: "fld" }, h("span", { class: "lbl" }, tr("lbl_limit")), limit);
    var creditRow = h("label", { class: "check" }, credit,
      h("span", { style: "display:flex;flex-direction:column;gap:2px" },
        h("span", { class: "t1" }, tr("credit_title")),
        h("span", { class: "t2" }, tr("credit_hint"))));
    var creditDash = h("div", { class: "dash" });
    var note = h("div", { class: "note" });

    function sync() {
      state.credit = credit.checked && state.type !== "cash";
      typeChips.forEach(function (c) { c.classList.toggle("on", c.getAttribute("data-v") === state.type); });
      curChips.forEach(function (c) { c.classList.toggle("on", c.getAttribute("data-v") === state.currency); });
      var isCash = state.type === "cash";
      creditRow.hidden = creditDash.hidden = isCash;
      limitFld.hidden = !state.credit;
      last4.placeholder = isCash ? "—" : "0000";
      balanceLbl.textContent = tr(state.credit ? "lbl_debt" : "lbl_balance");
      note.textContent = tr("note_last4", { last4: /^\d{4}$/.test(last4.value) ? last4.value : "1234" });
    }
    credit.addEventListener("change", sync);
    last4.addEventListener("input", function () {
      last4.value = last4.value.replace(/\D/g, "").slice(0, 4);
      last4.classList.remove("bad");
      sync();
    });
    [name, balance, limit].forEach(function (el) { el.addEventListener("input", function () { el.classList.remove("bad"); }); });
    [balance, limit].forEach(function (el) {
      el.addEventListener("blur", function () {
        var v = parseMinor(el.value);
        if (v !== null && el.value.trim()) el.value = minorToInput(v) || "0";
      });
    });

    var saveBtn = h("button", { class: "btn primary", type: "button", onclick: save }, tr("save"));

    function invalid(el, key) { el.classList.add("bad"); el.focus(); toast(tr(key), true); haptic("error"); }

    function save() {
      var payload = {
        card_type: state.type, name: name.value.trim(), last4: last4.value.trim(), currency: state.currency,
        is_credit: state.credit, balance_minor: parseMinor(balance.value),
        credit_limit_minor: state.credit ? parseMinor(limit.value) : 0
      };
      if (!payload.name || payload.name.length > 40) return invalid(name, "err_name");
      if ((payload.last4 || state.type !== "cash") && !/^\d{4}$/.test(payload.last4)) return invalid(last4, "err_last4");
      if (payload.balance_minor === null) return invalid(balance, "err_amount");
      if (payload.credit_limit_minor === null) return invalid(limit, "err_amount");
      saveBtn.disabled = true;
      api(acc ? "PUT" : "POST", acc ? "accounts/" + acc.id : "accounts", payload).then(function () {
        haptic("success");
        toast(tr("saved"));
        back();
      }).catch(function (err) {
        saveBtn.disabled = false;
        haptic("error");
        var field = { name: name, last4: last4, last4_taken: last4, amount: balance }[err.code];
        if (field) field.classList.add("bad");
        toast(errorText(err), true);
      });
    }

    mount(
      topBar(tr(acc ? "title_edit" : "title_new"), back),
      h("div", { class: "slip form" },
        h("div", { class: "perf t" }), h("div", { class: "perf b" }),
        h("div", { class: "fld" }, h("span", { class: "lbl" }, tr("lbl_type")), h("div", { class: "chips" }, typeChips)),
        h("label", { class: "fld" }, h("span", { class: "lbl" }, tr("lbl_name")), name),
        h("div", { class: "grid2" },
          h("label", { class: "fld" }, h("span", { class: "lbl" }, tr("lbl_last4")), last4),
          h("div", { class: "fld" }, h("span", { class: "lbl" }, tr("lbl_currency")),
            h("div", { style: "display:flex;gap:8px" }, curChips))),
        h("label", { class: "fld" }, balanceLbl, balance),
        creditDash,
        creditRow,
        limitFld),
      note,
      h("div", { class: "spacer" }),
      h("div", { class: "actions" }, saveBtn)
    );
    sync();
  }

  // ---- Cards: details ----

  function showCard(accountId) {
    loading();
    load(api("GET", "accounts/" + accountId), function (data) {
      var acc = data.account, month = data.month, stamp = stampInfo(acc);
      var meta = [acc.last4 ? "•••• " + acc.last4 : null, acc.currency];
      if (acc.is_credit && acc.credit_limit_minor) meta.push(tr("limit_line", { amount: num(acc.credit_limit_minor, acc.currency) }));

      var ops = h("div", { class: "slip ops" }, h("div", { class: "perf b" }));
      if (!data.operations.length) ops.appendChild(h("div", { class: "mute", style: "font-size:14px;text-align:center" }, tr("no_ops")));
      data.operations.forEach(function (op) {
        var label = op.kind === "income" ? tr("op_income") : op.kind === "transfer" ? tr("op_transfer") : (op.category || tr("op_expense"));
        var incoming = op.direction === "in";
        ops.appendChild(h("button", { class: "op tap", type: "button", onclick: function () { go("#/op/" + op.id); } },
          h("span", { class: "d mute" }, ddmm(op.date)),
          h("span", { class: "c" }, label),
          h("span", { class: "ld" }),
          h("span", { class: "a" + (incoming ? " blue" : "") }, (incoming ? "+" : "−") + short(op.amount_minor, op.currency))));
      });

      var amount = acc.is_credit ? -acc.debt_minor : acc.balance_minor;
      mount(
        topBar(acc.name, back, h("button", { class: "icon-btn", type: "button", "aria-label": tr("edit"), html: ICON_EDIT, onclick: function () { go("#/edit/" + acc.id); } })),
        h("div", { class: "slip stamp-slip" },
          h("div", { class: "perf t" }), h("div", { class: "perf b" }),
          h("div", { class: "stamp", style: "color:" + stamp.color }, h("div", null, stamp.text)),
          h("span", { class: "mute lbl-sm" }, tr(acc.is_credit ? "debt" : "balance")),
          h("span", { class: "big" + (acc.is_credit && acc.debt_minor ? " red" : "") }, money(amount, acc.currency)),
          h("span", { class: "mute sub" }, meta.filter(Boolean).join(" · ")),
          h("div", { class: "dash", style: "margin: 14px 0 10px" }),
          h("div", { class: "month" },
            h("div", null, h("span", { class: "k mute" }, tr("month_expense")), h("span", { class: "v red" }, (month.expense_minor ? "−" : "") + short(month.expense_minor, acc.currency))),
            h("div", null, h("span", { class: "k mute" }, tr("month_income")), h("span", { class: "v blue" }, (month.income_minor ? "+" : "") + short(month.income_minor, acc.currency))))),
        h("div", { class: "section" }, h("span", { class: "name" }, tr("recent_ops"))),
        ops,
        h("div", { class: "spacer" }),
        h("div", { class: "actions" },
          h("button", { class: "btn paper", type: "button", onclick: function () { go("#/edit/" + acc.id); } }, tr("edit")),
          h("button", { class: "link-danger", type: "button", onclick: function () { removeAccount(acc, data.has_operations); } }, tr("delete")))
      );
    });
  }

  function removeAccount(acc, hasOperations) {
    confirmBox(tr(hasOperations ? "confirm_archive" : "confirm_delete", { name: acc.name }), function (ok) {
      if (!ok) return;
      api("DELETE", "accounts/" + acc.id).then(function (data) {
        haptic("success");
        toast(tr(data.result === "archived" ? "archived" : "deleted"));
        back();
      }).catch(function (err) { haptic("error"); toast(errorText(err), true); });
    });
  }

  // ---- Start ----

  function loadTexts() {
    return api("GET", "me").then(function (data) {
      T = data.texts || {};
      LANG = data.lang || "uz";
      AI = !!data.ai;
      adviceCache = {};
      document.documentElement.lang = LANG;
      document.title = tr("app_title");
    });
  }

  if (tg) {
    try {
      tg.ready();
      tg.expand();
      if (tg.setHeaderColor) tg.setHeaderColor("#22302E");
      if (tg.setBackgroundColor) tg.setBackgroundColor("#22302E");
      if (tg.setBottomBarColor) tg.setBottomBarColor("#1A2422");
      if (tg.BackButton) tg.BackButton.onClick(back);
    } catch (e) { /* older Telegram clients lack some methods */ }
  }

  loading();
  loadTexts().then(function () {
    window.addEventListener("hashchange", render);
    render();
  }).catch(failed);
})();
