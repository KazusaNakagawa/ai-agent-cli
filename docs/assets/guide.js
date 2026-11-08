/* brief-lens user guide — shared behaviour.
 *
 * Each page declares <html data-root="…" data-page="…"> and holds only its own
 * <main id="content">. This script builds the sidebar, top bar, in-page table
 * of contents, heading anchors, copy buttons and the previous/next pager from
 * the single NAV list below, so adding a page means one entry here.
 *
 * DOM is built with createElement/textContent only (never innerHTML with
 * page-derived text), and heading ids are URL-encoded in hrefs.
 */
(function () {
  "use strict";

  var NAV = [
    { title: "はじめに", items: [
      { id: "index", href: "index.html", label: "brief-lens とは" },
      { id: "getting-started", href: "guide/getting-started.html", label: "インストールと初回セットアップ" },
      { id: "basics", href: "guide/basics.html", label: "画面の基本" }
    ]},
    { title: "ブリーフィング", items: [
      { id: "lens", href: "guide/lens.html", label: "視点を設定する（Portfolio ほか）" },
      { id: "run", href: "guide/run.html", label: "ブリーフィングを生成する（Run）" },
      { id: "briefing", href: "guide/briefing.html", label: "ブリーフィングを読む（Briefing）" },
      { id: "chat", href: "guide/chat.html", label: "質問する（Q&A Chat）" }
    ]},
    { title: "そのほかの画面", items: [
      { id: "journal", href: "guide/journal.html", label: "Journal" },
      { id: "monitor", href: "guide/monitor.html", label: "Monitor と Usage" },
      { id: "workspace", href: "guide/workspace.html", label: "Workspace" },
      { id: "settings", href: "guide/settings.html", label: "Config（設定画面）" }
    ]},
    { title: "運用とリファレンス", items: [
      { id: "source", href: "guide/source.html", label: "ソースから使う・毎日の運用" },
      { id: "configuration", href: "guide/configuration.html", label: "設定ファイル" },
      { id: "troubleshooting", href: "guide/troubleshooting.html", label: "困ったときは" },
      { id: "how-it-works", href: "guide/how-it-works.html", label: "仕組み" }
    ]}
  ];

  var REPO = "https://github.com/KazusaNakagawa/ai-agent-cli";
  var NPM = "https://www.npmjs.com/package/brief-lens";

  var root = document.documentElement.getAttribute("data-root") || "";
  var pageId = document.documentElement.getAttribute("data-page") || "";
  var content = document.getElementById("content");
  if (!content) return;

  function el(tag, attrs, text) {
    var node = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) { node.setAttribute(k, attrs[k]); });
    }
    if (text != null) node.textContent = text;
    return node;
  }

  var flat = [];
  NAV.forEach(function (g) { g.items.forEach(function (it) { flat.push({ group: g.title, item: it }); }); });
  var currentIndex = -1;
  flat.forEach(function (entry, i) { if (entry.item.id === pageId) currentIndex = i; });

  /* ---- Sidebar ---- */
  var sidebar = document.getElementById("sidebar");
  var navLinks = [];
  if (sidebar) {
    var brand = el("a", { class: "brand", href: root + "index.html" });
    brand.appendChild(el("span", { class: "brand__mark", "aria-hidden": "true" }, "b"));
    var brandText = el("span", null, "brief-lens");
    brandText.appendChild(el("span", { class: "brand__sub" }, "ユーザーガイド"));
    brand.appendChild(brandText);
    sidebar.appendChild(brand);

    var searchWrap = el("div", { class: "nav-search" });
    var search = el("input", { type: "search", placeholder: "ページを絞り込む", "aria-label": "ページを絞り込む" });
    searchWrap.appendChild(search);
    sidebar.appendChild(searchWrap);

    var nav = el("nav", { "aria-label": "ガイド" });
    NAV.forEach(function (g) {
      var group = el("div", { class: "nav__group" });
      group.appendChild(el("div", { class: "nav__group-title" }, g.title));
      var ul = el("ul", { class: "nav__list" });
      g.items.forEach(function (it) {
        var li = el("li");
        var a = el("a", { class: "nav__link", href: root + it.href }, it.label);
        if (it.id === pageId) a.setAttribute("aria-current", "page");
        li.appendChild(a);
        ul.appendChild(li);
        navLinks.push({ li: li, group: group, label: it.label });
      });
      group.appendChild(ul);
      nav.appendChild(group);
    });
    var empty = el("div", { class: "nav__empty", hidden: "" }, "該当するページがありません");
    nav.appendChild(empty);
    sidebar.appendChild(nav);

    var footer = el("div", { class: "sidebar__footer" });
    footer.appendChild(el("a", { href: REPO }, "GitHub リポジトリ"));
    footer.appendChild(el("a", { href: NPM }, "npm: brief-lens"));
    sidebar.appendChild(footer);

    search.addEventListener("input", function () {
      var q = search.value.trim().toLowerCase();
      var shown = 0;
      navLinks.forEach(function (n) {
        var hit = !q || n.label.toLowerCase().indexOf(q) !== -1;
        n.li.hidden = !hit;
        if (hit) shown += 1;
      });
      NAV.forEach(function (_, gi) {
        var groupEl = nav.children[gi];
        var anyVisible = Array.prototype.some.call(groupEl.querySelectorAll("li"), function (li) { return !li.hidden; });
        groupEl.hidden = !anyVisible;
      });
      empty.hidden = shown !== 0;
    });
  }

  /* ---- Top bar ---- */
  var main = document.querySelector(".main");
  if (main) {
    var bar = el("header", { class: "topbar" });
    var menuBtn = el("button", { class: "icon-btn menu-toggle", type: "button", "aria-label": "メニューを開く", "aria-expanded": "false" });
    menuBtn.appendChild(el("span", { "aria-hidden": "true" }, "☰"));
    menuBtn.appendChild(el("span", { class: "btn-label" }, "メニュー"));
    bar.appendChild(menuBtn);
    var crumbs = el("nav", { class: "crumbs", "aria-label": "パンくずリスト" });
    crumbs.appendChild(el("a", { href: root + "index.html" }, "ガイド"));
    if (currentIndex > 0) {
      crumbs.appendChild(el("span", { "aria-hidden": "true" }, "/"));
      crumbs.appendChild(document.createTextNode(flat[currentIndex].group));
    }
    bar.appendChild(crumbs);
    bar.appendChild(el("span", { class: "topbar__spacer" }));
    var themeBtn = el("button", { class: "icon-btn", type: "button", "aria-label": "テーマを切り替える" });
    bar.appendChild(themeBtn);
    main.insertBefore(bar, main.firstChild);

    var themeIcon = el("span", { "aria-hidden": "true" });
    var themeText = el("span", { class: "btn-label" });
    themeBtn.appendChild(themeIcon);
    themeBtn.appendChild(themeText);
    function themeLabel() {
      var dark = document.documentElement.getAttribute("data-theme") === "dark";
      themeIcon.textContent = dark ? "☀" : "☾";
      themeText.textContent = dark ? "ライト" : "ダーク";
    }
    themeLabel();
    themeBtn.addEventListener("click", function () {
      var next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", next);
      try { localStorage.setItem("guide-theme", next); } catch (e) { /* storage may be unavailable */ }
      themeLabel();
    });

    var scrim = document.getElementById("scrim");
    function setNav(open) {
      document.body.classList.toggle("nav-open", open);
      menuBtn.setAttribute("aria-expanded", open ? "true" : "false");
    }
    menuBtn.addEventListener("click", function () { setNav(!document.body.classList.contains("nav-open")); });
    if (scrim) scrim.addEventListener("click", function () { setNav(false); });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") setNav(false); });
  }

  /* ---- Heading ids, anchors and in-page TOC ---- */
  var headings = Array.prototype.slice.call(content.querySelectorAll("h2, h3"));
  headings.forEach(function (h, i) {
    if (!h.id) h.id = "s" + (i + 1);
    var a = el("a", { class: "anchor", href: "#" + encodeURIComponent(h.id), "aria-label": "この見出しへのリンク" }, "#");
    h.appendChild(a);
  });
  var h2s = headings.filter(function (h) { return h.tagName === "H2"; });
  if (h2s.length >= 3 && !content.hasAttribute("data-no-toc")) {
    var toc = el("nav", { class: "toc", "aria-label": "このページの内容" });
    toc.appendChild(el("div", { class: "toc__title" }, "このページの内容"));
    // h2 entries are numbered; h3 entries nest under their h2 in a bullet list.
    var ol = el("ol");
    var lastH2 = null;
    var sub = null;
    headings.forEach(function (h) {
      var label = h.firstChild && h.firstChild.nodeType === 3 ? h.firstChild.textContent : h.textContent.replace(/#$/, "");
      var a = el("a", { href: "#" + encodeURIComponent(h.id) }, label.trim());
      if (h.tagName === "H3" && lastH2) {
        if (!sub) { sub = el("ul"); lastH2.appendChild(sub); }
        var subLi = el("li");
        subLi.appendChild(a);
        sub.appendChild(subLi);
        return;
      }
      lastH2 = el("li");
      sub = null;
      lastH2.appendChild(a);
      ol.appendChild(lastH2);
    });
    toc.appendChild(ol);
    var lead = content.querySelector(".lead");
    var anchorNode = lead ? lead.nextSibling : (content.querySelector("h1") || {}).nextSibling;
    content.insertBefore(toc, anchorNode || null);
  }

  /* ---- Copy buttons on code blocks ---- */
  Array.prototype.forEach.call(content.querySelectorAll("pre"), function (pre) {
    var btn = el("button", { class: "copy-btn", type: "button" }, "コピー");
    btn.addEventListener("click", function () {
      var code = pre.querySelector("code") || pre;
      var text = code.textContent;
      var done = function () {
        btn.textContent = "コピーしました";
        setTimeout(function () { btn.textContent = "コピー"; }, 1500);
      };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(done, function () {});
      }
    });
    pre.appendChild(btn);
  });

  /* ---- Previous / next ---- */
  if (currentIndex !== -1) {
    var pager = el("nav", { class: "pager", "aria-label": "前後のページ" });
    function pagerLink(entry, label, cls) {
      var a = el("a", { href: root + entry.item.href, class: cls });
      a.appendChild(el("span", { class: "pager__label" }, label));
      a.appendChild(el("span", { class: "pager__title" }, entry.item.label));
      return a;
    }
    if (currentIndex > 0) pager.appendChild(pagerLink(flat[currentIndex - 1], "前へ", "pager--prev"));
    else pager.appendChild(el("span"));
    if (currentIndex < flat.length - 1) pager.appendChild(pagerLink(flat[currentIndex + 1], "次へ", "pager--next"));
    content.appendChild(pager);
  }

  var foot = el("footer", { class: "page-footer" });
  foot.appendChild(document.createTextNode("brief-lens / My World Briefing — MIT License. "));
  var src = el("a", { href: REPO }, "ソースコード");
  foot.appendChild(src);
  content.appendChild(foot);
})();
