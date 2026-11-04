/* Finance bot Mini App: accounts list, add / edit form, account details. Plain JS, no build step.
 * Every API call sends Telegram.WebApp.initData; the server checks its signature and the ADMINS list.
 * Amounts travel as integers in minor units (amount * 100). */
(function () {
  "use strict";

  var tg = (window.Telegram && window.Telegram.WebApp) || null;
  var app = document.getElementById("app");
  var toastEl = document.getElementById("toast");
  var T = {};  // texts in the user's language, from /api/me
  var CARD_TYPES = ["cash", "uzcard", "humo", "visa", "mastercard"];
  var BRAND = { uzcard: "UZCARD", humo: "HUMO", visa: "VISA", mastercard: "MASTERCARD" };
  var ICON_BACK = '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 5l-7 7 7 7"/></svg>';
  var ICON_EDIT = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 20h4L19 9l-4-4L4 16v4z"/></svg>';
  var ICON_PLUS = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg>';

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
    for (var i = 2; i < arguments.length; i++) {
      var child = arguments[i];
      if (child === null || child === undefined || child === false) continue;
      el.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
    }
    return el;
  }

  // No-break spaces between thousands, so an amount never wraps
  function group(digits) { return digits.replace(/\B(?=(\d{3})+(?!\d))/g, " "); }

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
    var clean = String(text || "").replace(/[\s  ']/g, "").replace(",", ".");
    if (!clean) return 0;
    if (!/^\d{1,13}(\.\d{1,2})?$/.test(clean)) return null;
    var parts = clean.split(".");
    var cents = parts[1] ? (parts[1] + "0").slice(0, 2) : "00";
    return parseInt(parts[0], 10) * 100 + parseInt(cents, 10);
  }

  function minorToInput(minor, currency) {
    if (!minor) return "";
    var abs = Math.abs(minor), whole = Math.floor(abs / 100), cents = abs % 100;
    return group(String(whole)) + (cents ? "." + (cents < 10 ? "0" : "") + cents : "");
  }

  function ddmm(iso) { var p = iso.split("-"); return p[2] + "." + p[1]; }

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

  var toastTimer = null;
  function toast(text, isError) {
    toastEl.textContent = text;
    toastEl.className = "toast" + (isError ? " err" : "");
    toastEl.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { toastEl.hidden = true; }, 2600);
  }

  function haptic(kind) {
    try { if (tg && tg.HapticFeedback) tg.HapticFeedback.notificationOccurred(kind); } catch (e) { /* old client */ }
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

  var ERROR_TEXTS = {
    name: "err_name", last4: "err_last4", last4_taken: "err_last4_taken", amount: "err_amount",
    currency_locked: "err_currency_locked", not_found: "err_not_found", auth: "err_auth", forbidden: "err_forbidden"
  };

  function errorText(err) {
    if (err && err.message && (err.code === "auth" || err.code === "forbidden")) return err.message;
    var key = err && ERROR_TEXTS[err.code];
    return key && T[key] ? T[key] : (T.err_generic || "Error");
  }

  // ---- Navigation ----

  function go(hash) { location.hash = hash; }

  function parentOf(hash) {
    var m = hash.match(/^#\/edit\/(\d+)$/);
    if (m) return "#/card/" + m[1];
    return "#/";
  }

  function setBackButton(hash) {
    if (!tg || !tg.BackButton) return;
    if (hash === "#/" || hash === "") tg.BackButton.hide(); else tg.BackButton.show();
  }

  function render() {
    var hash = location.hash || "#/";
    setBackButton(hash);
    window.scrollTo(0, 0);
    var m;
    if ((m = hash.match(/^#\/card\/(\d+)$/))) return showCard(+m[1]);
    if ((m = hash.match(/^#\/edit\/(\d+)$/))) return showForm(+m[1]);
    if (hash === "#/new") return showForm(null);
    return showMain();
  }

  function mount() {
    app.textContent = "";
    for (var i = 0; i < arguments.length; i++) if (arguments[i]) app.appendChild(arguments[i]);
  }

  function loading() { mount(h("div", { class: "center" }, T.loading || "…")); }

  function failed(err) {
    mount(h("div", { class: "center" }, errorText(err)));
  }

  function topBar(title, back, extra) {
    return h("div", { class: "bar" },
      h("button", { class: "icon-btn", type: "button", "aria-label": tr("back"), html: ICON_BACK, onclick: function () { go(back); } }),
      h("span", { class: "title" }, title),
      extra || null);
  }

  // ---- Screen 1: accounts ----

  function showMain() {
    loading();
    api("GET", "accounts").then(function (data) {
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
    }).catch(failed);
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

  // ---- Screen 2: add / edit ----

  function showForm(accountId) {
    if (accountId === null) return drawForm(null);
    loading();
    api("GET", "accounts/" + accountId).then(function (data) { drawForm(data.account); }).catch(failed);
  }

  function drawForm(acc) {
    var state = {
      type: acc ? (acc.card_type || (acc.kind === "cash" ? "cash" : "uzcard")) : "uzcard",
      currency: acc ? acc.currency : "UZS",
      credit: acc ? acc.is_credit : false
    };
    var back = acc ? "#/card/" + acc.id : "#/";

    var name = h("input", { class: "inp", maxlength: "40", autocomplete: "off", "aria-label": tr("lbl_name"), value: acc ? acc.name : "" });
    var last4 = h("input", { class: "inp", inputmode: "numeric", maxlength: "4", pattern: "[0-9]*", autocomplete: "off", "aria-label": tr("lbl_last4"), value: acc && acc.last4 ? acc.last4 : "", placeholder: "0000" });
    var balance = h("input", { class: "inp", inputmode: "decimal", autocomplete: "off", "aria-label": tr("lbl_balance"),
      value: acc ? minorToInput(acc.is_credit ? acc.debt_minor : acc.balance_minor, acc.currency) : "", placeholder: "0" });
    var limit = h("input", { class: "inp", inputmode: "decimal", autocomplete: "off", "aria-label": tr("lbl_limit"),
      value: acc && acc.is_credit ? minorToInput(acc.credit_limit_minor, acc.currency) : "", placeholder: "0" });
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
        if (v !== null && el.value.trim()) el.value = minorToInput(v, state.currency) || "0";
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
      api(acc ? "PUT" : "POST", acc ? "accounts/" + acc.id : "accounts", payload).then(function (data) {
        haptic("success");
        toast(tr("saved"));
        go(acc ? "#/card/" + data.account.id : "#/");
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
        h("div", { class: "fld" }, h("span", { class: "lbl" }, tr("lbl_type")), h.apply(null, ["div", { class: "chips" }].concat(typeChips))),
        h("label", { class: "fld" }, h("span", { class: "lbl" }, tr("lbl_name")), name),
        h("div", { class: "grid2" },
          h("label", { class: "fld" }, h("span", { class: "lbl" }, tr("lbl_last4")), last4),
          h("div", { class: "fld" }, h("span", { class: "lbl" }, tr("lbl_currency")),
            h.apply(null, ["div", { style: "display:flex;gap:8px" }].concat(curChips)))),
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

  // ---- Screen 3: account details ----

  function showCard(accountId) {
    loading();
    api("GET", "accounts/" + accountId).then(function (data) {
      var acc = data.account, month = data.month, stamp = stampInfo(acc);
      var meta = [acc.last4 ? "•••• " + acc.last4 : null, acc.currency];
      if (acc.is_credit && acc.credit_limit_minor) meta.push(tr("limit_line", { amount: num(acc.credit_limit_minor, acc.currency) }));

      var ops = h("div", { class: "slip ops" }, h("div", { class: "perf b" }));
      if (!data.operations.length) ops.appendChild(h("div", { class: "mute", style: "font-size:14px;text-align:center" }, tr("no_ops")));
      data.operations.forEach(function (op) {
        var label = op.kind === "income" ? tr("op_income") : op.kind === "transfer" ? tr("op_transfer") : (op.category || tr("op_expense"));
        var incoming = op.direction === "in";
        ops.appendChild(h("div", { class: "op" },
          h("span", { class: "d mute" }, ddmm(op.date)),
          h("span", { class: "c" }, label),
          h("span", { class: "ld" }),
          h("span", { class: "a" + (incoming ? " blue" : "") }, (incoming ? "+" : "−") + short(op.amount_minor, op.currency))));
      });

      var amount = acc.is_credit ? -acc.debt_minor : acc.balance_minor;
      mount(
        topBar(acc.name, "#/", h("button", { class: "icon-btn", type: "button", "aria-label": tr("edit"), html: ICON_EDIT, onclick: function () { go("#/edit/" + acc.id); } })),
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
          h("button", { class: "link-danger", type: "button", onclick: function () { remove(acc, data.has_operations); } }, tr("delete")))
      );
    }).catch(failed);
  }

  function confirmBox(text, done) {
    if (tg && tg.showConfirm && tg.isVersionAtLeast && tg.isVersionAtLeast("6.2")) {
      try { tg.showConfirm(text, done); return; } catch (e) { /* fall back below */ }
    }
    done(window.confirm(text));
  }

  function remove(acc, hasOperations) {
    confirmBox(tr(hasOperations ? "confirm_archive" : "confirm_delete", { name: acc.name }), function (ok) {
      if (!ok) return;
      api("DELETE", "accounts/" + acc.id).then(function (data) {
        haptic("success");
        toast(tr(data.result === "archived" ? "archived" : "deleted"));
        go("#/");
      }).catch(function (err) { haptic("error"); toast(errorText(err), true); });
    });
  }

  // ---- Start ----

  if (tg) {
    try {
      tg.ready();
      tg.expand();
      if (tg.setHeaderColor) tg.setHeaderColor("#22302E");
      if (tg.setBackgroundColor) tg.setBackgroundColor("#22302E");
      if (tg.BackButton) tg.BackButton.onClick(function () { go(parentOf(location.hash || "#/")); });
    } catch (e) { /* older Telegram clients lack some methods */ }
  }

  loading();
  api("GET", "me").then(function (data) {
    T = data.texts || {};
    document.documentElement.lang = data.lang || "uz";
    document.title = tr("title_main");
    window.addEventListener("hashchange", render);
    render();
  }).catch(failed);
})();
