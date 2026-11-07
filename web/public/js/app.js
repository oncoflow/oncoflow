(function () {
  var root = document.documentElement;
  var radioLight = document.getElementById("theme-light");
  var radioDark = document.getElementById("theme-dark");
  var osDarkMql =
    typeof window !== "undefined" && typeof window.matchMedia === "function"
      ? window.matchMedia("(prefers-color-scheme: dark)")
      : null;

  function resolveEffectiveTheme(pref) {
    if (pref === "dark" || pref === "light") return pref;
    return osDarkMql && osDarkMql.matches ? "dark" : "light";
  }

  function applyThemePreference(pref) {
    var normalized = pref === "dark" || pref === "light" ? pref : "auto";
    root.setAttribute("data-theme-pref", normalized);
    var effective = resolveEffectiveTheme(normalized);
    root.setAttribute("data-theme", effective);
    if (radioLight && radioDark) {
      radioLight.checked = effective === "light";
      radioDark.checked = effective === "dark";
    }
    var themeMenuBtns = document.querySelectorAll("[data-menu-action='set-theme']");
    themeMenuBtns.forEach(function (btn) {
      var val = btn.getAttribute("data-theme-value");
      var isSelected = val === normalized;
      btn.setAttribute("aria-checked", isSelected ? "true" : "false");
      btn.classList.toggle("ds-menu__item--active", isSelected);
    });
  }

  function setTheme(mode) {
    var normalized = mode === "dark" || mode === "light" ? mode : "auto";
    applyThemePreference(normalized);
    try {
      fetch("/preferences", {
        method: "POST",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded",
          "HX-Request": "true",
        },
        body: "theme=" + encodeURIComponent(normalized),
      }).catch(function () {});
    } catch (_e) {}
  }

  // Initialize effective theme immediately on load (especially when preference is "auto")
  var initialPref = root.getAttribute("data-theme-pref") || root.getAttribute("data-theme") || "auto";
  applyThemePreference(initialPref);

  if (osDarkMql) {
    var onOsThemeChange = function () {
      var currentPref = root.getAttribute("data-theme-pref") || "auto";
      if (currentPref === "auto") {
        applyThemePreference("auto");
      }
    };
    if (typeof osDarkMql.addEventListener === "function") {
      osDarkMql.addEventListener("change", onOsThemeChange);
    } else if (typeof osDarkMql.addListener === "function") {
      osDarkMql.addListener(onOsThemeChange);
    }
  }

  if (radioLight) {
    radioLight.addEventListener("change", function () {
      if (radioLight.checked) setTheme("light");
    });
  }
  if (radioDark) {
    radioDark.addEventListener("change", function () {
      if (radioDark.checked) setTheme("dark");
    });
  }

  // Sidebar collapse toggle (M3 Navigation Rail on Desktop + Off-Canvas Drawer on Mobile/Tablet)
  var sbBtn = document.getElementById("sidebar-toggle");
  var mobileNavBtn = document.getElementById("mobile-nav-toggle");
  var sbBackdrop = document.getElementById("sidebar-backdrop");

  function setMobileNavOpen(open) {
    document.body.classList.toggle("ds-shell--mobile-nav-open", open);
    if (mobileNavBtn) {
      mobileNavBtn.setAttribute("aria-expanded", String(open));
    }
  }

  try {
    if (window.localStorage && window.localStorage.getItem("ds_sidebar_collapsed") === "true") {
      document.body.classList.add("ds-shell--sidebar-collapsed");
      if (sbBtn) sbBtn.setAttribute("aria-expanded", "false");
    }
  } catch (_e) {}
  if (sbBtn) {
    sbBtn.addEventListener("click", function () {
      if (window.innerWidth <= 1024) {
        setMobileNavOpen(false);
        return;
      }
      var collapsed = document.body.classList.toggle("ds-shell--sidebar-collapsed");
      sbBtn.setAttribute("aria-expanded", String(!collapsed));
      try {
        if (window.localStorage) {
          window.localStorage.setItem("ds_sidebar_collapsed", String(collapsed));
        }
      } catch (_e) {}
    });
  }
  if (mobileNavBtn) {
    mobileNavBtn.addEventListener("click", function () {
      var isOpen = document.body.classList.contains("ds-shell--mobile-nav-open");
      setMobileNavOpen(!isOpen);
    });
  }
  if (sbBackdrop) {
    sbBackdrop.addEventListener("click", function () {
      setMobileNavOpen(false);
    });
  }
  document.addEventListener("keydown", function (ev) {
    if (ev.key === "Escape" && document.body.classList.contains("ds-shell--mobile-nav-open")) {
      setMobileNavOpen(false);
    }
  });

  // Auto-collapse mobile filter drawers on small viewports (<= 768px) unless an active filter is set
  function syncMobileCollapsibleDrawers() {
    var isMobile = window.innerWidth <= 768;
    var hasActiveFilter = false;
    try {
      var sp = new URLSearchParams(window.location.search);
      hasActiveFilter = Boolean(
        (sp.get("search") && sp.get("search").trim()) ||
          (sp.get("urgency") && sp.get("urgency") !== "all") ||
          (sp.get("completeness") && sp.get("completeness") !== "all") ||
          (sp.get("specialty") && sp.get("specialty") !== "all"),
      );
    } catch (_e) {}

    document.querySelectorAll('details[data-mobile-collapsible="true"]').forEach(function (d) {
      if (!isMobile) {
        d.open = true;
      } else if (!d.hasAttribute("data-mobile-init")) {
        d.setAttribute("data-mobile-init", "true");
        d.open = hasActiveFilter;
      }
    });
  }
  syncMobileCollapsibleDrawers();
  window.addEventListener("resize", syncMobileCollapsibleDrawers, { passive: true });

  // Default worklist to Cards view on mobile viewports (<= 768px) unless display=table is explicitly requested
  function syncMobileWorklistDefaultDisplay() {
    if (window.innerWidth > 768) return;
    try {
      var sp = new URLSearchParams(window.location.search);
      if (sp.get("display") === "table" || sp.get("display") === "cards") return;
    } catch (_e) {}
    var tpl = document.getElementById("worklist-mobile-cards-tpl");
    var tableWrap = document.querySelector(".ds-table-wrap");
    if (tpl && tpl.content && tableWrap && tableWrap.parentNode) {
      var clone = tpl.content.cloneNode(true);
      tableWrap.parentNode.replaceChild(clone, tableWrap);
      tpl.parentNode.removeChild(tpl);
      var displaySelect = document.getElementById("f-display");
      if (displaySelect && displaySelect.value !== "cards") {
        displaySelect.value = "cards";
      }
    }
  }
  syncMobileWorklistDefaultDisplay();
  window.addEventListener("resize", syncMobileWorklistDefaultDisplay, { passive: true });

  // Toggle all accordions, toggle PDF expand, quick prompt chips, M3 Contextual Menus (...), and M3 Exposed Dropdown Menus
  function closeAllMenus(exceptEl) {
    document
      .querySelectorAll("details.ds-menu[open], details.ds-popover[open]")
      .forEach(function (m) {
        if (m !== exceptEl) m.open = false;
      });
    document.querySelectorAll(".ds-m3-select.is-open").forEach(function (sel) {
      if (sel !== exceptEl) {
        sel.classList.remove("is-open");
        var trig = sel.querySelector(".ds-m3-select__trigger");
        if (trig) trig.setAttribute("aria-expanded", "false");
      }
    });
    document.querySelectorAll(".ds-split-btn.is-open").forEach(function (sb) {
      if (sb !== exceptEl) {
        sb.classList.remove("is-open");
        var tBtn = sb.querySelector("[data-split-prompt-toggle]");
        if (tBtn) tBtn.setAttribute("aria-expanded", "false");
      }
    });
    document.querySelectorAll(".ds-fab-menu.is-open").forEach(function (fm) {
      if (fm !== exceptEl) {
        fm.classList.remove("is-open");
        var fmTrig = fm.querySelector(".ds-fab-menu__trigger");
        if (fmTrig) fmTrig.setAttribute("aria-expanded", "false");
      }
    });
  }

  // Upgrade native <select class="ds-select"> elements into Material Design 3 Exposed Dropdown Menus
  function initM3Selects(scopeRoot) {
    var scope = scopeRoot || document;
    scope.querySelectorAll("select.ds-select").forEach(function (select) {
      if (select.getAttribute("data-m3-upgraded") === "true") return;
      select.setAttribute("data-m3-upgraded", "true");
      select.classList.add("ds-select--native-hidden");
      select.tabIndex = -1;

      var wrapper = document.createElement("div");
      wrapper.className =
        "ds-m3-select" + (select.classList.contains("ds-select--sm") ? " ds-m3-select--sm" : "");

      var trigger = document.createElement("button");
      trigger.type = "button";
      trigger.className = "ds-m3-select__trigger";
      trigger.setAttribute("aria-haspopup", "listbox");
      trigger.setAttribute("aria-expanded", "false");

      var valueSpan = document.createElement("span");
      valueSpan.className = "ds-m3-select__value";
      var arrowSpan = document.createElement("span");
      arrowSpan.className = "ds-m3-select__arrow";
      arrowSpan.setAttribute("aria-hidden", "true");
      arrowSpan.innerHTML =
        '<svg class="ds-icon ds-icon--md" aria-hidden="true" viewBox="0 0 24 24"><path d="m6 9 6 6 6-6"/></svg>';

      trigger.appendChild(valueSpan);
      trigger.appendChild(arrowSpan);

      var panel = document.createElement("ul");
      panel.className = "ds-m3-select__panel";
      panel.setAttribute("role", "listbox");

      function buildIconHtml(iconId) {
        if (!iconId) return "";
        return (
          '<span class="ds-m3-select__icon" aria-hidden="true">' +
          '<svg class="ds-icon ds-icon--xs" aria-hidden="true" focusable="false"><use href="#' +
          iconId +
          '"></use></svg></span>'
        );
      }

      function syncFromSelect() {
        var selectedOpt = select.options[select.selectedIndex] || select.options[0];
        var iconId = selectedOpt ? selectedOpt.getAttribute("data-icon") : "";
        var textLabel = selectedOpt ? selectedOpt.textContent || "" : "";
        if (iconId) {
          valueSpan.innerHTML = buildIconHtml(iconId) + "<span></span>";
          var innerSpan = valueSpan.querySelector("span:last-child");
          if (innerSpan) innerSpan.textContent = textLabel;
        } else {
          valueSpan.textContent = textLabel;
        }
        panel.querySelectorAll(".ds-m3-select__option").forEach(function (li) {
          var isSel = li.getAttribute("data-value") === select.value;
          li.setAttribute("aria-selected", isSel ? "true" : "false");
        });
      }

      Array.prototype.forEach.call(select.options, function (opt) {
        var li = document.createElement("li");
        li.className = "ds-m3-select__option";
        li.setAttribute("role", "option");
        li.setAttribute("tabindex", "0");
        li.setAttribute("data-value", opt.value);
        li.setAttribute("aria-selected", opt.selected ? "true" : "false");

        var check = document.createElement("span");
        check.className = "ds-m3-select__check";
        check.setAttribute("aria-hidden", "true");
        check.innerHTML =
          '<svg class="ds-icon ds-icon--xs" aria-hidden="true" viewBox="0 0 24 24"><path d="m5 12.5 4.5 4.5L19 7.5"/></svg>';

        li.appendChild(check);
        var optIcon = opt.getAttribute("data-icon");
        if (optIcon) {
          var iconWrap = document.createElement("span");
          iconWrap.className = "ds-m3-select__icon";
          iconWrap.setAttribute("aria-hidden", "true");
          iconWrap.innerHTML =
            '<svg class="ds-icon ds-icon--xs" aria-hidden="true" focusable="false"><use href="#' +
            optIcon +
            '"></use></svg>';
          li.appendChild(iconWrap);
        }

        var label = document.createElement("span");
        label.className = "ds-m3-select__label";
        label.textContent = opt.textContent;

        li.appendChild(label);

        function chooseOption(ev) {
          ev.preventDefault();
          ev.stopPropagation();
          var prevVal = select.value;
          select.value = opt.value;
          syncFromSelect();
          wrapper.classList.remove("is-open");
          trigger.setAttribute("aria-expanded", "false");
          if (prevVal !== opt.value) {
            select.dispatchEvent(new Event("change", { bubbles: true }));
          }
        }

        li.addEventListener("click", chooseOption);
        li.addEventListener("keydown", function (ev) {
          var optionsList = Array.prototype.slice.call(
            panel.querySelectorAll(".ds-m3-select__option"),
          );
          var curIdx = optionsList.indexOf(li);
          if (ev.key === "Enter" || ev.key === " ") {
            chooseOption(ev);
          } else if (ev.key === "ArrowDown") {
            ev.preventDefault();
            var nextOpt = optionsList[(curIdx + 1) % optionsList.length];
            if (nextOpt) nextOpt.focus();
          } else if (ev.key === "ArrowUp") {
            ev.preventDefault();
            var prevOpt = optionsList[(curIdx - 1 + optionsList.length) % optionsList.length];
            if (prevOpt) prevOpt.focus();
          } else if (ev.key === "Home") {
            ev.preventDefault();
            if (optionsList[0]) optionsList[0].focus();
          } else if (ev.key === "End") {
            ev.preventDefault();
            if (optionsList[optionsList.length - 1]) optionsList[optionsList.length - 1].focus();
          } else if (ev.key === "Escape") {
            ev.preventDefault();
            wrapper.classList.remove("is-open");
            trigger.setAttribute("aria-expanded", "false");
            trigger.focus();
          }
        });
        panel.appendChild(li);
      });

      syncFromSelect();
      select.addEventListener("change", syncFromSelect);

      function openOrToggleM3Select(focusFirstOption) {
        var willOpen = !wrapper.classList.contains("is-open");
        closeAllMenus(wrapper);
        if (willOpen && typeof wrapper.getBoundingClientRect === "function") {
          var rect = wrapper.getBoundingClientRect();
          wrapper.classList.toggle("ds-m3-select--flip", rect.bottom + 240 > window.innerHeight);
        }
        wrapper.classList.toggle("is-open", willOpen);
        trigger.setAttribute("aria-expanded", willOpen ? "true" : "false");
        if (willOpen && focusFirstOption) {
          var activeLi =
            panel.querySelector(".ds-m3-select__option[aria-selected='true']") ||
            panel.querySelector(".ds-m3-select__option");
          if (activeLi) activeLi.focus();
        }
      }

      trigger.addEventListener("click", function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        openOrToggleM3Select(false);
      });

      trigger.addEventListener("keydown", function (ev) {
        if (ev.key === "ArrowDown" || ev.key === "ArrowUp") {
          ev.preventDefault();
          if (!wrapper.classList.contains("is-open")) {
            openOrToggleM3Select(true);
          } else {
            var activeLi =
              panel.querySelector(".ds-m3-select__option[aria-selected='true']") ||
              panel.querySelector(".ds-m3-select__option");
            if (activeLi) activeLi.focus();
          }
        }
      });

      wrapper.appendChild(trigger);
      wrapper.appendChild(panel);
      if (select.parentNode) {
        select.parentNode.insertBefore(wrapper, select.nextSibling);
      }
    });
  }
  initM3Selects(document);

  // M3 Non-blocking Co-Pilot Side Sheet (#ai-chat-drawer) & M3 Expressive FAB Menu (#ai-chat-fab)
  function syncVisualViewportForAiDrawer() {
    var drawer = document.getElementById("ai-chat-drawer");
    if (!drawer || !drawer.classList.contains("is-open")) {
      root.classList.remove("is-keyboard-open");
      if (drawer) drawer.classList.remove("is-keyboard-open");
      return;
    }
    var vv = window.visualViewport;
    var isMobile = window.innerWidth <= 768;
    var vvh = vv ? vv.height : window.innerHeight;
    var vvTop = vv ? vv.offsetTop : 0;

    root.style.setProperty("--ds-vvh", Math.round(vvh) + "px");
    root.style.setProperty("--ds-vv-offset-top", Math.round(vvTop) + "px");

    var activeEl = document.activeElement;
    var isChatInputFocused = Boolean(
      activeEl &&
        (activeEl.classList.contains("ds-chat__input") ||
          (activeEl.closest && activeEl.closest(".ds-copilot-drawer, .ds-chat"))) &&
        (activeEl.tagName === "TEXTAREA" || activeEl.tagName === "INPUT"),
    );
    var keyboardLikelyOpen =
      isMobile && (vvh < window.innerHeight * 0.82 || isChatInputFocused);

    root.classList.toggle("is-keyboard-open", keyboardLikelyOpen);
    drawer.classList.toggle("is-keyboard-open", keyboardLikelyOpen);
    if (keyboardLikelyOpen) {
      var log = drawer.querySelector(".ds-chat__log");
      if (log) {
        log.scrollTop = log.scrollHeight;
      }
    }
  }

  if (window.visualViewport) {
    window.visualViewport.addEventListener("resize", syncVisualViewportForAiDrawer, {
      passive: true,
    });
    window.visualViewport.addEventListener("scroll", syncVisualViewportForAiDrawer, {
      passive: true,
    });
  }
  window.addEventListener("resize", syncVisualViewportForAiDrawer, { passive: true });
  document.addEventListener("focusin", function (e) {
    var t = e.target;
    if (
      t instanceof HTMLElement &&
      (t.classList.contains("ds-chat__input") || t.closest(".ds-copilot-drawer, .ds-chat"))
    ) {
      window.setTimeout(syncVisualViewportForAiDrawer, 60);
      window.setTimeout(syncVisualViewportForAiDrawer, 260);
    }
  });
  document.addEventListener("focusout", function (e) {
    var t = e.target;
    if (
      t instanceof HTMLElement &&
      (t.classList.contains("ds-chat__input") || t.closest(".ds-copilot-drawer, .ds-chat"))
    ) {
      window.setTimeout(syncVisualViewportForAiDrawer, 100);
    }
  });
  syncVisualViewportForAiDrawer();

  function setChatDrawerOpen(isOpen) {
    var drawer = document.getElementById("ai-chat-drawer");
    if (!drawer) return;
    drawer.classList.toggle("is-open", isOpen);
    drawer.setAttribute("aria-hidden", isOpen ? "false" : "true");
    document.querySelectorAll("[data-action='toggle-chat-drawer']").forEach(function (btn) {
      btn.setAttribute("aria-expanded", isOpen ? "true" : "false");
    });
    var fab = document.getElementById("ai-chat-fab");
    if (fab) {
      fab.classList.remove("is-open");
      var fabTrig = fab.querySelector(".ds-fab-menu__trigger");
      if (fabTrig) fabTrig.setAttribute("aria-expanded", "false");
      fab.classList.toggle("is-hidden", isOpen);
    }
    syncVisualViewportForAiDrawer();
    if (isOpen && typeof syncAllSegmentedPills === "function") {
      syncAllSegmentedPills();
    }
    if (isOpen && window.innerWidth > 768) {
      var input = drawer.querySelector("textarea");
      if (input) {
        window.setTimeout(function () {
          input.focus();
        }, 140);
      }
    }
  }

  try {
    var params = new URLSearchParams(window.location.search);
    if (
      params.get("chat") === "open" ||
      window.location.hash === "#panel-chat" ||
      window.location.hash === "#ai-chat-drawer"
    ) {
      setChatDrawerOpen(true);
    }
  } catch (_e) {}

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      closeAllMenus(null);
      var drawer = document.getElementById("ai-chat-drawer");
      if (drawer && drawer.classList.contains("is-open")) {
        setChatDrawerOpen(false);
      }
    }
  });

  // One-click & double-click on a card, worklist row, agenda item, or queue job ([data-href]) opens it directly
  function handleDataHrefNavigation(e) {
    if (e.defaultPrevented) return;
    if (
      e.target.closest(
        "a, button, summary, details, input, select, textarea, dialog, form, label, .ds-m3-select, .ds-hovercard, .ds-field__clear, .ds-agenda-item__rank, [data-agenda-drag-handle]",
      )
    ) {
      return;
    }
    if (e.type === "click") {
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      try {
        var sel = window.getSelection ? String(window.getSelection()).trim() : "";
        if (sel.length > 0) return;
      } catch (_err) {}
    }
    var row = e.target.closest("[data-href]");
    if (!row) return;
    var href = row.getAttribute("data-href");
    if (href) {
      window.location.href = href;
    }
  }
  document.addEventListener("click", handleDataHrefNavigation);
  document.addEventListener("dblclick", handleDataHrefNavigation);
  document.addEventListener("keydown", function (e) {
    if (e.key !== "Enter" || e.defaultPrevented) return;
    var active = document.activeElement;
    if (!active || !active.hasAttribute || !active.hasAttribute("data-href")) return;
    var href = active.getAttribute("data-href");
    if (href) {
      e.preventDefault();
      window.location.href = href;
    }
  });

  // Material Design 3 Outlined Text Fields (floating inner-to-border label + trailing ✕ clear button)
  function syncM3FieldState(field, control) {
    if (!field || !control) return;
    var val = String(control.value || "");
    var hasVal = val.length > 0;
    field.classList.toggle("has-value", hasVal);
    field.classList.toggle("is-empty", !hasVal);
    field.classList.toggle("is-invalid", control.getAttribute("aria-invalid") === "true");
  }

  function initM3TextFields(rootScope) {
    var scope = rootScope || document;
    scope.querySelectorAll(".ds-field").forEach(function (field) {
      var control = field.querySelector(
        "input.ds-input:not([type='date']):not([type='file']):not([type='hidden']), textarea.ds-textarea",
      );
      if (!control) return;
      if (!control.hasAttribute("placeholder")) {
        control.setAttribute("placeholder", " ");
      }
      syncM3FieldState(field, control);
      if (field.getAttribute("data-m3-field-bound") === "true") return;
      field.setAttribute("data-m3-field-bound", "true");
      if (typeof window.requestAnimationFrame === "function") {
        window.requestAnimationFrame(function () {
          field.classList.add("is-ready");
        });
      } else {
        field.classList.add("is-ready");
      }

      control.addEventListener("input", function () {
        syncM3FieldState(field, control);
      });
      control.addEventListener("change", function () {
        syncM3FieldState(field, control);
      });
      if (control.form) {
        control.form.addEventListener("reset", function () {
          window.setTimeout(function () {
            syncM3FieldState(field, control);
          }, 0);
        });
      }

      if (
        control.tagName === "INPUT" &&
        !control.disabled &&
        !control.readOnly &&
        !field.querySelector(".ds-field__clear")
      ) {
        var clearBtn = document.createElement("button");
        clearBtn.type = "button";
        clearBtn.className = "ds-field__clear";
        clearBtn.setAttribute("aria-label", "Effacer le champ");
        clearBtn.setAttribute("title", "Effacer");
        clearBtn.setAttribute("data-testid", "btn_clear_" + (control.id || control.name || "field"));
        clearBtn.innerHTML =
          '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg>';
        clearBtn.addEventListener("click", function (ev) {
          ev.preventDefault();
          ev.stopPropagation();
          control.value = "";
          syncM3FieldState(field, control);
          control.dispatchEvent(new Event("input", { bubbles: true }));
          control.dispatchEvent(new Event("change", { bubbles: true }));
          control.focus();
        });
        field.appendChild(clearBtn);
      }
    });
  }
  initM3TextFields(document);

  document.addEventListener("click", function (e) {
    var parentMenu = e.target.closest(
      "details.ds-menu, details.ds-popover, .ds-m3-select, .ds-fab-menu",
    );
    if (!parentMenu) {
      closeAllMenus(null);
    } else if (e.target.closest("summary.ds-menu__trigger, summary.ds-popover__trigger")) {
      closeAllMenus(parentMenu);
    }

    var toggleFabMenuBtn = e.target.closest("[data-action='toggle-fab-menu']");
    if (toggleFabMenuBtn) {
      e.preventDefault();
      e.stopPropagation();
      var fabHost = toggleFabMenuBtn.closest(".ds-fab-menu");
      if (fabHost) {
        var willOpenFab = !fabHost.classList.contains("is-open");
        closeAllMenus(fabHost);
        fabHost.classList.toggle("is-open", willOpenFab);
        toggleFabMenuBtn.setAttribute("aria-expanded", willOpenFab ? "true" : "false");
      }
      return;
    }

    var openChatDrawerBtn = e.target.closest("[data-action='open-chat-drawer']");
    if (openChatDrawerBtn) {
      e.preventDefault();
      closeAllMenus(null);
      setChatDrawerOpen(true);
      return;
    }

    var fabPromptBtn = e.target.closest("[data-action='fab-quick-prompt']");
    if (fabPromptBtn) {
      e.preventDefault();
      closeAllMenus(null);
      setChatDrawerOpen(true);
      var promptText = fabPromptBtn.getAttribute("data-prompt") || "";
      var inputId = fabPromptBtn.getAttribute("data-target-input") || "chat-input";
      var chatInputEl = document.getElementById(inputId);
      if (chatInputEl) {
        chatInputEl.value = promptText;
        autoResizeChatInput(chatInputEl);
        window.setTimeout(function () {
          chatInputEl.focus();
        }, 160);
      }
      return;
    }

    var menuActionBtn = e.target.closest("[data-menu-action]");
    if (menuActionBtn) {
      var action = menuActionBtn.getAttribute("data-menu-action");
      var secName = menuActionBtn.getAttribute("data-section");
      closeAllMenus(null);

      if (action === "toggle-rail") {
        if (window.innerWidth <= 1024 && mobileNavBtn) {
          mobileNavBtn.click();
        } else if (sbBtn) {
          sbBtn.click();
        }
        return;
      }
      if (action === "set-theme") {
        var targetTheme = menuActionBtn.getAttribute("data-theme-value") || "auto";
        setTheme(targetTheme);
        return;
      }
      if (action === "toggle-theme") {
        var currentTheme = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
        setTheme(currentTheme);
        return;
      }
      if (action === "edit-section" && secName) {
        var editEl = document.querySelector("[data-testid='btn_edit_section_" + secName + "']");
        if (editEl) editEl.click();
        return;
      }
      if (action === "rerun-section" && secName) {
        var rerunEl = document.querySelector("[data-testid='btn_rerun_section_" + secName + "']");
        if (rerunEl) rerunEl.click();
        return;
      }
      if (action === "toggle-reasoning" && secName) {
        var parentSec = document.getElementById("section-" + secName);
        if (parentSec && parentSec.tagName === "DETAILS") parentSec.open = true;
        var reasEl = document.querySelector("[data-testid='reasoning-" + secName + "']");
        if (reasEl) {
          reasEl.open = !reasEl.open;
        }
        return;
      }
      if (action === "copy-section" && secName) {
        var secEl = document.getElementById("section-" + secName);
        if (secEl && navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(secEl.innerText.trim()).catch(function () {});
        }
        return;
      }
      if (action === "toggle-details") {
        var targetTestId = menuActionBtn.getAttribute("data-target-testid");
        var detailsEl = targetTestId
          ? document.querySelector("[data-testid='" + targetTestId + "']")
          : null;
        if (detailsEl) {
          var parentDetails = detailsEl.parentElement
            ? detailsEl.parentElement.closest("details.ds-section, details.ds-opinion")
            : null;
          if (parentDetails) parentDetails.open = true;
          detailsEl.open = !detailsEl.open;
        }
        return;
      }
      if (action === "copy-text") {
        var copyText = menuActionBtn.getAttribute("data-copy-text") || "";
        if (copyText && navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(copyText).catch(function () {});
        }
        return;
      }
    }

    var toggleChatDrawerBtn = e.target.closest("[data-action='toggle-chat-drawer']");
    if (toggleChatDrawerBtn) {
      closeAllMenus(null);
      var chatDrawer = document.getElementById("ai-chat-drawer");
      if (chatDrawer) {
        var nextOpen = !chatDrawer.classList.contains("is-open");
        setChatDrawerOpen(nextOpen);
      }
      return;
    }

    var closeChatDrawerBtn = e.target.closest("[data-action='close-chat-drawer']");
    if (closeChatDrawerBtn) {
      closeAllMenus(null);
      setChatDrawerOpen(false);
      return;
    }

    var toggleAllBtn = e.target.closest("[data-action='toggle-all-accordions']");
    if (toggleAllBtn) {
      closeAllMenus(null);
      var panelId = toggleAllBtn.getAttribute("data-target-panel") || "panel-clinical";
      var panel = document.getElementById(panelId);
      if (panel) {
        var accordions = panel.querySelectorAll("details.ds-section, details.ds-opinion");
        var anyOpen = false;
        accordions.forEach(function (d) {
          if (d.open) anyOpen = true;
        });
        accordions.forEach(function (d) {
          d.open = !anyOpen;
        });
      }
      return;
    }

    var mobilePdfBtn = e.target.closest("[data-action='toggle-mobile-pdf']");
    if (mobilePdfBtn) {
      closeAllMenus(null);
      var pdfPane = mobilePdfBtn.closest("[data-pdf-pane]");
      if (pdfPane) {
        var isOpen = pdfPane.classList.toggle("is-mobile-pdf-open");
        mobilePdfBtn.setAttribute("aria-expanded", isOpen ? "true" : "false");
        var labelSpan = mobilePdfBtn.querySelector("[data-pdf-toggle-text]");
        if (labelSpan) {
          var nextLabel = isOpen
            ? mobilePdfBtn.getAttribute("data-label-hide")
            : mobilePdfBtn.getAttribute("data-label-show");
          if (nextLabel) labelSpan.textContent = nextLabel;
        }
        if (isOpen) {
          var viewerEl = pdfPane.querySelector("[data-pdf-canvas-viewer]");
          if (viewerEl && viewerEl.getAttribute("data-pdf-rendered") !== "true") {
            renderMobilePdfCanvas(viewerEl);
          }
        }
      }
      return;
    }

    var pdfExpandBtn = e.target.closest("[data-action='toggle-pdf-expand']");
    if (pdfExpandBtn) {
      closeAllMenus(null);
      if (window.matchMedia && window.matchMedia("(max-width: 75rem)").matches) {
        var mobileToggle = document.querySelector("[data-action='toggle-mobile-pdf']");
        if (mobileToggle) {
          mobileToggle.click();
          return;
        }
      }
      var splitView = document.getElementById("dossier-split-view");
      if (splitView) {
        var expanded = splitView.classList.toggle("ds-split--pdf-expanded");
        pdfExpandBtn.setAttribute("aria-pressed", String(expanded));
      }
      return;
    }

    var splitToggle = e.target.closest("[data-split-prompt-toggle]");
    if (splitToggle) {
      e.preventDefault();
      e.stopPropagation();
      var splitHost = splitToggle.closest(".ds-split-btn");
      if (splitHost) {
        var willOpen = !splitHost.classList.contains("is-open");
        closeAllMenus(splitHost);
        splitHost.classList.toggle("is-open", willOpen);
        splitToggle.setAttribute("aria-expanded", willOpen ? "true" : "false");
      }
      return;
    }

    var splitInsert = e.target.closest("[data-split-prompt-insert]");
    if (splitInsert) {
      e.preventDefault();
      var splitContainer = splitInsert.closest(".ds-split-btn");
      closeAllMenus(null);
      if (splitContainer) {
        var items = splitContainer.querySelectorAll("[data-quick-prompt]");
        if (items.length > 0) {
          var nextIdx =
            (Number(splitContainer.getAttribute("data-prompt-idx") || "0") || 0) % items.length;
          splitContainer.setAttribute("data-prompt-idx", String((nextIdx + 1) % items.length));
          var chosen = items[nextIdx];
          var text = chosen.getAttribute("data-quick-prompt") || "";
          var targetId =
            splitInsert.getAttribute("data-target-input") ||
            chosen.getAttribute("data-target-input") ||
            "chat-input";
          var fieldEl = document.getElementById(targetId);
          if (fieldEl) {
            fieldEl.value = text;
            autoResizeChatInput(fieldEl);
            fieldEl.focus();
          }
        }
      }
      return;
    }

    var promptChip = e.target.closest("[data-quick-prompt]");
    if (promptChip) {
      closeAllMenus(null);
      var chipPromptText = promptChip.getAttribute("data-quick-prompt") || "";
      var targetInputId = promptChip.getAttribute("data-target-input") || "chat-input";
      var inputEl = document.getElementById(targetInputId);
      if (inputEl) {
        inputEl.value = chipPromptText;
        autoResizeChatInput(inputEl);
        inputEl.focus();
      }
    }
  });

  // Auto-submit selects
  document.querySelectorAll("[data-autosubmit='true']").forEach(function (el) {
    el.addEventListener("change", function () {
      if (el.form) el.form.submit();
    });
  });

  // Dialog openers & closers
  document.addEventListener("click", function (e) {
    var openBtn = e.target.closest("[data-open]");
    if (openBtn) {
      closeAllMenus(null);
      var dlg = document.getElementById(openBtn.getAttribute("data-open"));
      if (dlg) {
        var patientName = openBtn.getAttribute("data-patient-name");
        if (patientName) {
          dlg.querySelectorAll("[data-del-patient-name]").forEach(function (el) {
            el.textContent = patientName;
          });
        }
        if (typeof dlg.showModal === "function") {
          dlg.showModal();
        } else {
          dlg.setAttribute("open", "");
        }
      }
    }
    var closeBtn = e.target.closest("[data-close]");
    if (closeBtn) {
      var cDlg = document.getElementById(closeBtn.getAttribute("data-close"));
      if (cDlg) {
        if (typeof cDlg.close === "function") {
          cDlg.close();
        } else {
          cDlg.removeAttribute("open");
        }
      }
    }
  });

  // Center horizontally scrollable RCP session timeline on the active session (mobile / narrow viewports)
  function centerActiveTimelineStep(scopeRoot) {
    var scope = scopeRoot || document;
    scope.querySelectorAll(".ds-timeline").forEach(function (timeline) {
      if (timeline.scrollWidth <= timeline.clientWidth) return;
      var activeLink = timeline.querySelector('.ds-timeline__link[aria-current="step"]');
      var activeItem = activeLink ? activeLink.closest(".ds-timeline__item") || activeLink : null;
      if (!activeItem) return;
      var targetLeft =
        activeItem.offsetLeft - Math.max(0, (timeline.clientWidth - activeItem.offsetWidth) / 2);
      timeline.scrollLeft = Math.max(0, targetLeft);
    });
  }
  centerActiveTimelineStep(document);
  window.addEventListener(
    "resize",
    function () {
      centerActiveTimelineStep(document);
    },
    { passive: true },
  );
  document.addEventListener(
    "toggle",
    function (ev) {
      if (
        ev.target &&
        ev.target.classList &&
        ev.target.classList.contains("ds-timeline-drawer") &&
        ev.target.open
      ) {
        centerActiveTimelineStep(ev.target);
      }
    },
    true,
  );

  // ARIA tabs navigation with dedicated M3 sliding bottom indicator (.ds-tabs__indicator — icons & labels stay fixed)
  function initM3Tabs(scopeRoot) {
    var scope = scopeRoot || document;
    scope.querySelectorAll(".ds-tabs[role='tablist']").forEach(function (tablist) {
      if (tablist.getAttribute("data-m3-tabs-bound") === "true") return;
      tablist.setAttribute("data-m3-tabs-bound", "true");
      var tabs = Array.prototype.slice.call(tablist.querySelectorAll("[role='tab']"));
      var indicator = tablist.querySelector(".ds-tabs__indicator");
      if (!indicator && tabs.length > 0) {
        indicator = document.createElement("span");
        indicator.className = "ds-tabs__indicator";
        indicator.setAttribute("aria-hidden", "true");
        tablist.appendChild(indicator);
      }

      function syncTabIndicator(activeTab) {
        if (!indicator || !activeTab) return;
        if (tablist.classList.contains("ds-tabs--patient-level")) {
          indicator.style.width = activeTab.offsetWidth + "px";
          indicator.style.transform = "translate3d(" + activeTab.offsetLeft + "px, 0, 0)";
          return;
        }
        var pad = 16; // matches --ds-space-4
        var w = Math.max(16, activeTab.offsetWidth - pad * 2);
        var x = activeTab.offsetLeft + pad;
        indicator.style.width = w + "px";
        indicator.style.transform = "translate3d(" + x + "px, 0, 0)";
      }

      function selectTab(idx, focus) {
        tabs.forEach(function (t, i) {
          var on = i === idx;
          t.setAttribute("aria-selected", String(on));
          t.tabIndex = on ? 0 : -1;
          var panelId = t.getAttribute("aria-controls");
          var panel = panelId ? document.getElementById(panelId) : null;
          if (panel) panel.hidden = !on;
        });
        var nextTab = tabs[idx];
        if (nextTab) {
          if (nextTab.id === "tab-patient-dashboard" || nextTab.id === "tab-patient-rcp") {
            var synopticCard = document.querySelector("[data-testid='synoptic-card']");
            if (synopticCard) {
              synopticCard.setAttribute(
                "data-patient-view",
                nextTab.id === "tab-patient-dashboard" ? "dashboard" : "rcp",
              );
            }
            if (nextTab.id === "tab-patient-rcp") {
              centerActiveTimelineStep(document);
            }
            window.dispatchEvent(new Event("resize"));
          }
          syncTabIndicator(nextTab);
          if (focus) nextTab.focus();
        }
      }

      var initialActive =
        tablist.querySelector("[role='tab'][aria-selected='true']") || tabs[0] || null;
      if (initialActive) syncTabIndicator(initialActive);

      try {
        var params = new URLSearchParams(window.location.search);
        var requestedView = params.get("view");
        var requestedTab =
          params.get("tab") ||
          (requestedView === "dashboard" || requestedView === "patient-dashboard"
            ? "patient-dashboard"
            : null);
        if (requestedTab === "dashboard") requestedTab = "patient-dashboard";
        if (requestedTab) {
          tabs.forEach(function (t, i) {
            if (t.id === "tab-" + requestedTab) selectTab(i, false);
          });
        }
      } catch (_e) {}

      if (typeof window.requestAnimationFrame === "function") {
        window.requestAnimationFrame(function () {
          tablist.classList.add("is-ready");
        });
      } else {
        tablist.classList.add("is-ready");
      }

      window.addEventListener(
        "resize",
        function () {
          var cur = tablist.querySelector("[role='tab'][aria-selected='true']");
          if (cur) syncTabIndicator(cur);
        },
        { passive: true },
      );

      tabs.forEach(function (tab, i) {
        tab.addEventListener("click", function () {
          selectTab(i, false);
        });
        tab.addEventListener("keydown", function (ev) {
          if (ev.key === "ArrowRight") {
            ev.preventDefault();
            selectTab((i + 1) % tabs.length, true);
          } else if (ev.key === "ArrowLeft") {
            ev.preventDefault();
            selectTab((i - 1 + tabs.length) % tabs.length, true);
          }
        });
      });
    });
  }
  initM3Tabs(document);

  // M3 Segmented Button background pill slider (.ds-segmented__pill — only the colored background moves)
  function syncAllSegmentedPills() {
    document.querySelectorAll(".ds-segmented").forEach(function (seg) {
      var pill = seg.querySelector(".ds-segmented__pill");
      var checkedLabel = seg.querySelector("input:checked + label");
      if (!checkedLabel || !pill || checkedLabel.offsetWidth === 0) return;
      pill.style.width = checkedLabel.offsetWidth + "px";
      pill.style.transform = "translate3d(" + checkedLabel.offsetLeft + "px, 0, 0)";
    });
  }

  document.querySelectorAll(".ds-segmented").forEach(function (seg) {
    var pill = seg.querySelector(".ds-segmented__pill");
    if (!pill) {
      pill = document.createElement("span");
      pill.className = "ds-segmented__pill";
      pill.setAttribute("aria-hidden", "true");
      seg.insertBefore(pill, seg.firstChild);
    }
    var checkedLabel = seg.querySelector("input:checked + label");
    if (checkedLabel && checkedLabel.offsetWidth > 0) {
      pill.style.width = checkedLabel.offsetWidth + "px";
      pill.style.transform = "translate3d(" + checkedLabel.offsetLeft + "px, 0, 0)";
    }
    if (typeof window.requestAnimationFrame === "function") {
      window.requestAnimationFrame(function () {
        seg.classList.add("is-ready");
      });
    } else {
      seg.classList.add("is-ready");
    }
    seg.addEventListener("change", syncAllSegmentedPills);
  });
  window.addEventListener("resize", syncAllSegmentedPills, { passive: true });

  // M3 Sliding Colored Background Pill across navigation buttons (.ds-nav__bg & .ds-bottom-nav__bg)
  // Icons & labels stay 100% static; only the colored pill background slides from the previous button to the new button.
  var NAV_BG_STORAGE_KEY = "ds_m3_nav_bg";

  (function playPendingNavBackgroundSlide() {
    try {
      if (!window.sessionStorage) return;
      var raw = window.sessionStorage.getItem(NAV_BG_STORAGE_KEY);
      if (!raw) return;
      window.sessionStorage.removeItem(NAV_BG_STORAGE_KEY);
      if (
        window.matchMedia &&
        window.matchMedia("(prefers-reduced-motion: reduce)").matches
      ) {
        return;
      }
      var prev = JSON.parse(raw);
      if (!prev || !prev.group || Date.now() - Number(prev.ts || 0) > 2000) return;

      if (prev.group === "bottom-nav") {
        var bottomNav = document.querySelector(".ds-bottom-nav");
        var targetBg = bottomNav
          ? bottomNav.querySelector(".ds-bottom-nav__item[aria-current='page'] .ds-bottom-nav__bg")
          : null;
        if (!bottomNav || !targetBg || typeof targetBg.animate !== "function") return;

        var curRect = targetBg.getBoundingClientRect();
        if (curRect.width === 0 && curRect.height === 0) return;

        var bottomItems = Array.prototype.slice.call(
          bottomNav.querySelectorAll(".ds-bottom-nav__item"),
        );
        var prevItem =
          typeof prev.index === "number" && bottomItems[prev.index]
            ? bottomItems[prev.index]
            : null;
        var prevPill = prevItem ? prevItem.querySelector(".ds-bottom-nav__pill") : null;
        var prevLeft = prevPill ? prevPill.getBoundingClientRect().left : Number(prev.left);
        var dx = prevLeft - curRect.left;
        if (Math.abs(dx) < 1) return;

        // Strictly horizontal movement (dy = 0) from the previous mobile button to the new one
        targetBg.animate(
          [
            { transform: "translate3d(" + dx + "px, 0, 0)" },
            { transform: "translate3d(0, 0, 0)" },
          ],
          {
            duration: 250,
            easing: "cubic-bezier(0.2, 0, 0, 1)",
          },
        );
        return;
      }

      if (prev.group === "side-nav") {
        var sideTargetBg = document.querySelector(
          ".ds-nav__link[aria-current='page'] > .ds-nav__bg",
        );
        if (!sideTargetBg || typeof sideTargetBg.animate !== "function") return;

        var sideCurRect = sideTargetBg.getBoundingClientRect();
        if (sideCurRect.width === 0 && sideCurRect.height === 0) return;

        var navLinks = Array.prototype.slice.call(document.querySelectorAll(".ds-nav__link"));
        var prevNavLink =
          typeof prev.index === "number" && navLinks[prev.index] ? navLinks[prev.index] : null;
        var prevNavBg = prevNavLink ? prevNavLink.querySelector(".ds-nav__bg") : null;
        var prevTop = prevNavBg ? prevNavBg.getBoundingClientRect().top : Number(prev.top);
        var dy = prevTop - sideCurRect.top;
        if (Math.abs(dy) < 1) return;

        // Strictly vertical movement (dx = 0) from the previous sidebar button to the new one
        sideTargetBg.animate(
          [
            { transform: "translate3d(0, " + dy + "px, 0)" },
            { transform: "translate3d(0, 0, 0)" },
          ],
          {
            duration: 250,
            easing: "cubic-bezier(0.2, 0, 0, 1)",
          },
        );
      }
    } catch (_err) {}
  })();

  document.addEventListener("click", function (e) {
    if (e.defaultPrevented || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    var bottomLink = e.target.closest(".ds-bottom-nav__item");
    if (bottomLink) {
      var bottomNav = bottomLink.closest(".ds-bottom-nav");
      var bottomItems = bottomNav
        ? Array.prototype.slice.call(bottomNav.querySelectorAll(".ds-bottom-nav__item"))
        : [];
      var curBottom = document.querySelector(".ds-bottom-nav__item[aria-current='page']");
      var curBottomBg = curBottom ? curBottom.querySelector(".ds-bottom-nav__bg") : null;
      if (curBottom && curBottom !== bottomLink && curBottomBg && window.sessionStorage) {
        var bRect = curBottomBg.getBoundingClientRect();
        if (bRect.width > 0) {
          try {
            window.sessionStorage.setItem(
              NAV_BG_STORAGE_KEY,
              JSON.stringify({
                group: "bottom-nav",
                index: bottomItems.indexOf(curBottom),
                left: bRect.left,
                top: bRect.top,
                width: bRect.width,
                height: bRect.height,
                ts: Date.now(),
              }),
            );
          } catch (_err) {}
        }
      }
      return;
    }

    var navLink = e.target.closest(".ds-nav__link");
    if (navLink) {
      var navLinks = Array.prototype.slice.call(document.querySelectorAll(".ds-nav__link"));
      var curNav = document.querySelector(".ds-nav__link[aria-current='page']");
      var curNavBg = curNav ? curNav.querySelector(".ds-nav__bg") : null;
      if (curNav && curNav !== navLink && curNavBg && window.sessionStorage) {
        var nRect = curNavBg.getBoundingClientRect();
        if (nRect.width > 0) {
          try {
            window.sessionStorage.setItem(
              NAV_BG_STORAGE_KEY,
              JSON.stringify({
                group: "side-nav",
                index: navLinks.indexOf(curNav),
                left: nRect.left,
                top: nRect.top,
                width: nRect.width,
                height: nRect.height,
                ts: Date.now(),
              }),
            );
          } catch (_err) {}
        }
      }
    }
  });

  // Inline section edit link (progressive enhancement)
  document.addEventListener("click", function (e) {
    var addExamBtn = e.target.closest("[data-add-exam-row]");
    if (addExamBtn) {
      e.preventDefault();
      var secName = addExamBtn.getAttribute("data-add-exam-row") || "RadiologicExams";
      var container = addExamBtn.closest("[data-exams-list-container]");
      var rowsHost = container ? container.querySelector("[data-exams-rows]") : null;
      if (rowsHost) {
        var idx = rowsHost.querySelectorAll("[data-exam-row]").length;
        var inputId = "inp-" + secName + "-exams_list";
        var rowEl = document.createElement("div");
        rowEl.className = "ds-subcard";
        rowEl.setAttribute("data-exam-row", String(idx));
        rowEl.style.marginBottom = "var(--ds-space-2)";
        rowEl.innerHTML =
          '<div class="ds-kv-grid">' +
          '<div class="ds-field">' +
          '<label class="ds-label" for="' + inputId + "-name-" + idx + '">Nom de l\'examen #' + (idx + 1) + "</label>" +
          '<input class="ds-input" type="text" id="' + inputId + "-name-" + idx + '" name="exam_name_' + idx + '" value="" data-field-type="text" placeholder="Ex : Scanner TAP injecté">' +
          "</div>" +
          '<div class="ds-field">' +
          '<label class="ds-label" for="' + inputId + "-type-" + idx + '">Modalité (Type)</label>' +
          '<select class="ds-select" id="' + inputId + "-type-" + idx + '" name="exam_type_' + idx + '" data-field-type="select">' +
          '<option value="CT" selected>CT — Scanner (TDM)</option>' +
          '<option value="MRI">MRI — IRM</option>' +
          '<option value="PET">PET — TEP-TDM</option>' +
          '<option value="EUS">EUS — Écho-endoscopie</option>' +
          "</select>" +
          "</div>" +
          '<div class="ds-field">' +
          '<label class="ds-label" for="' + inputId + "-date-" + idx + '">Date de l\'examen</label>' +
          '<input class="ds-input" type="date" id="' + inputId + "-date-" + idx + '" name="exam_date_' + idx + '" value="" data-field-type="date">' +
          "</div>" +
          "</div>" +
          '<div class="ds-field" style="margin-top:var(--ds-space-2)">' +
          '<label class="ds-label" for="' + inputId + "-res-" + idx + '">Conclusion / Résultat</label>' +
          '<textarea class="ds-textarea" rows="2" id="' + inputId + "-res-" + idx + '" name="exam_result_' + idx + '" data-field-type="textarea" placeholder="Résumé des conclusions radiologiques"></textarea>' +
          "</div>";
        rowsHost.appendChild(rowEl);
        initM3TextFields(rowEl);
        initM3Selects(rowEl);
      }
      return;
    }

    var addChemoBtn = e.target.closest("[data-add-chemo-row]");
    if (addChemoBtn) {
      e.preventDefault();
      var chemoSec = addChemoBtn.getAttribute("data-add-chemo-row") || "ChemotherapyTreament";
      var chemoContainer = addChemoBtn.closest("[data-chemo-list-container]");
      var chemoRowsHost = chemoContainer ? chemoContainer.querySelector("[data-chemo-rows]") : null;
      if (chemoRowsHost) {
        var cIdx = chemoRowsHost.querySelectorAll("[data-chemo-row]").length;
        var cInputId = "inp-" + chemoSec + "-chemotherapy_list";
        var cRowEl = document.createElement("div");
        cRowEl.className = "ds-subcard";
        cRowEl.setAttribute("data-chemo-row", String(cIdx));
        cRowEl.style.marginBottom = "var(--ds-space-2)";
        cRowEl.innerHTML =
          '<div class="ds-kv-grid">' +
          '<div class="ds-field">' +
          '<label class="ds-label" for="' + cInputId + "-name-" + cIdx + '">Protocole / Molécule #' + (cIdx + 1) + "</label>" +
          '<input class="ds-input" type="text" id="' + cInputId + "-name-" + cIdx + '" name="chemotherapy_name_' + cIdx + '" value="" data-field-type="text" placeholder="Ex : FOLFIRINOX">' +
          "</div>" +
          '<div class="ds-field">' +
          '<label class="ds-label" for="' + cInputId + "-tol-" + cIdx + '">Tolérance</label>' +
          '<select class="ds-select" id="' + cInputId + "-tol-" + cIdx + '" name="chemotherapy_tolerance_' + cIdx + '" data-field-type="select">' +
          '<option value="Good" selected>Bonne (Good)</option>' +
          '<option value="Medium">Moyenne / Modérée (Medium)</option>' +
          '<option value="Poor">Mauvaise / Toxicité (Poor)</option>' +
          "</select>" +
          "</div>" +
          '<div class="ds-field">' +
          '<label class="ds-label" for="' + cInputId + "-start-" + cIdx + '">Date de début</label>' +
          '<input class="ds-input" type="date" id="' + cInputId + "-start-" + cIdx + '" name="chemotherapy_start_date_' + cIdx + '" value="" data-field-type="date">' +
          "</div>" +
          '<div class="ds-field">' +
          '<label class="ds-label" for="' + cInputId + "-end-" + cIdx + '">Date de fin</label>' +
          '<input class="ds-input" type="date" id="' + cInputId + "-end-" + cIdx + '" name="chemotherapy_end_date_' + cIdx + '" value="" data-field-type="date">' +
          "</div>" +
          "</div>";
        chemoRowsHost.appendChild(cRowEl);
        initM3TextFields(cRowEl);
        initM3Selects(cRowEl);
      }
      return;
    }

    var editLink = e.target.closest("[data-edit-section]");
    if (!editLink) return;
    var targetId = editLink.getAttribute("data-edit-section");
    var href = editLink.getAttribute("href");
    if (!targetId || !href) return;
    e.preventDefault();
    fetch(href, { headers: { "HX-Request": "true" } })
      .then(function (r) {
        if (!r.ok) return null;
        return r.text();
      })
      .then(function (html) {
        if (!html) return;
        var host = document.getElementById(targetId);
        if (host) {
          host.outerHTML = html;
          initM3TextFields(document);
          initM3Selects(document);
        }
      })
      .catch(function () {});
  });

  // Auto-grow AI Chat textarea on newline / multi-line input
  function autoResizeChatInput(el) {
    if (!(el instanceof HTMLTextAreaElement)) return;
    el.style.height = "auto";
    var maxH = 136; // ~8.5rem
    var nextH = Math.min(Math.max(el.scrollHeight, 32), maxH);
    el.style.height = nextH + "px";
    el.style.overflowY = el.scrollHeight > maxH ? "auto" : "hidden";
  }

  document.addEventListener("input", function (e) {
    var target = e.target;
    if (!(target instanceof HTMLTextAreaElement)) return;
    if (
      target.getAttribute("data-chat-enter-submit") === "true" ||
      target.classList.contains("ds-chat__input") ||
      target.closest("[data-ajax-chat]")
    ) {
      autoResizeChatInput(target);
    }
  });

  // Enter to send, Shift+Enter for newline inside AI Chat textareas
  document.addEventListener("keydown", function (e) {
    var target = e.target;
    if (!(target instanceof HTMLTextAreaElement)) return;
    if (
      target.getAttribute("data-chat-enter-submit") !== "true" &&
      !target.closest("[data-ajax-chat]")
    ) {
      return;
    }
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      var form = target.form;
      if (!form || form.getAttribute("data-chat-busy") === "true") return;
      if (!target.value.trim()) return;
      if (typeof form.requestSubmit === "function") {
        form.requestSubmit();
      } else {
        form.dispatchEvent(new Event("submit", { cancelable: true, bubbles: true }));
      }
    }
  });

  // Inline section save & inline chat (progressive enhancement + M3 AI Reflection Module)
  document.addEventListener("submit", function (e) {
    var form = e.target;
    if (!(form instanceof HTMLFormElement)) return;

    var secId = form.getAttribute("data-ajax-section");
    if (secId) {
      e.preventDefault();
      var body = new URLSearchParams(new FormData(form)).toString();
      fetch(form.action, {
        method: "POST",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded",
          "HX-Request": "true",
        },
        body: body,
      })
        .then(function (r) {
          if (!r.ok) return null;
          return r.text();
        })
        .then(function (html) {
          if (!html) return;
          var host = document.getElementById(secId);
          if (host) {
            host.outerHTML = html;
            initM3TextFields(document);
            initM3Selects(document);
          }
        })
        .catch(function () {});
      return;
    }

    var chatLogId = form.getAttribute("data-ajax-chat");
    if (chatLogId) {
      e.preventDefault();
      if (form.getAttribute("data-chat-busy") === "true") return;

      var formData = new FormData(form);
      var questionText = String(formData.get("question") || "").trim();
      if (!questionText) return;
      var chatBody = new URLSearchParams(formData).toString();

      var textarea = form.querySelector("textarea");
      var submitBtn = form.querySelector("[data-chat-submit-btn], button[type='submit']");
      var log = document.getElementById(chatLogId);

      // Determine selected clinical specialty label for the M3 Reflection Module
      var selectAgent = form.querySelector("select[name='agentName']");
      var checkedAgent = form.querySelector("input[name='agentName']:checked");
      var agentLabel = "Assistant clinique";
      if (selectAgent && selectAgent.options && selectAgent.selectedIndex >= 0) {
        var selOpt = selectAgent.options[selectAgent.selectedIndex];
        agentLabel =
          (selOpt && (selOpt.getAttribute("data-agent-label") || selOpt.textContent)) ||
          "Assistant clinique";
      } else if (checkedAgent) {
        agentLabel = checkedAgent.getAttribute("data-agent-label") || checkedAgent.value;
      }

      form.setAttribute("data-chat-busy", "true");
      if (textarea) {
        textarea.value = "";
        autoResizeChatInput(textarea);
      }
      if (submitBtn) submitBtn.setAttribute("disabled", "disabled");

      var timerInterval = null;
      if (log) {
        // 1. Immediately append optimistic user message bubble
        var userLi = document.createElement("li");
        userLi.className = "ds-chat__msg ds-chat__msg--user";
        userLi.setAttribute("data-chat-temp", "true");
        var userAuthor = document.createElement("span");
        userAuthor.className = "ds-chat__author";
        userAuthor.textContent = "Vous";
        var userBubble = document.createElement("div");
        userBubble.className = "ds-chat__bubble";
        userBubble.textContent = questionText;
        userLi.appendChild(userAuthor);
        userLi.appendChild(userBubble);
        log.appendChild(userLi);

        // 2. Append the M3 AI Thinking / Reflection Module
        var tpl = form.querySelector("template[data-chat-thinking-template]");
        if (tpl && tpl.content) {
          var clone = tpl.content.cloneNode(true);
          var agentEl = clone.querySelector("[data-thinking-agent]");
          if (agentEl && agentLabel) {
            agentEl.textContent = agentLabel;
          }
          log.appendChild(clone);
        }

        log.scrollTop = log.scrollHeight;

        // 3. Live elapsed timer (minutes & seconds) & step progression while waiting for LLM / RAG
        var startedAt = Date.now();
        timerInterval = window.setInterval(function () {
          var elapsedSec = (Date.now() - startedAt) / 1000;
          var timerEl = log.querySelector("[data-thinking-timer]");
          if (timerEl) {
            var totalSec = Math.max(0, Math.floor(elapsedSec));
            var mins = Math.floor(totalSec / 60);
            var secs = totalSec % 60;
            timerEl.textContent = mins + " min " + (secs < 10 ? "0" + secs : secs) + " s";
          }
          var stepIdx = elapsedSec < 1.8 ? 0 : elapsedSec < 4.0 ? 1 : 2;
          var steps = log.querySelectorAll("[data-thinking-step]");
          steps.forEach(function (st, idx) {
            st.classList.toggle("is-active", idx === stepIdx);
            st.classList.toggle("is-done", idx < stepIdx);
          });
        }, 100);
      }

      fetch(form.action, {
        method: "POST",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded",
          "HX-Request": "true",
        },
        body: chatBody,
      })
        .then(function (r) {
          if (!r.ok) {
            var err = new Error("HTTP " + r.status);
            err.status = r.status;
            throw err;
          }
          return r.text();
        })
        .then(function (html) {
          if (timerInterval) window.clearInterval(timerInterval);
          if (log) {
            log.querySelectorAll("[data-chat-temp='true']").forEach(function (el) {
              el.remove();
            });
            log.insertAdjacentHTML("beforeend", html);
            log.scrollTop = log.scrollHeight;
          }
        })
        .catch(function (err) {
          if (timerInterval) window.clearInterval(timerInterval);
          if (log) {
            log.querySelectorAll("[data-chat-temp='true']").forEach(function (el) {
              el.remove();
            });
            var errUserLi = document.createElement("li");
            errUserLi.className = "ds-chat__msg ds-chat__msg--user";
            var errUserAuthor = document.createElement("span");
            errUserAuthor.className = "ds-chat__author";
            errUserAuthor.textContent = "Vous";
            var errUserBubble = document.createElement("div");
            errUserBubble.className = "ds-chat__bubble";
            errUserBubble.textContent = questionText;
            errUserLi.appendChild(errUserAuthor);
            errUserLi.appendChild(errUserBubble);
            log.appendChild(errUserLi);

            var errLi = document.createElement("li");
            errLi.className = "ds-chat__msg ds-chat__msg--assistant";
            errLi.setAttribute("data-testid", "chat-assistant-error");
            var errAuthor = document.createElement("span");
            errAuthor.className = "ds-chat__author";
            errAuthor.textContent = agentLabel || "Assistant clinique";
            var errBubble = document.createElement("div");
            errBubble.className = "ds-chat__bubble";
            var statusLabel = err && err.status ? " (erreur " + err.status + ")" : "";
            errBubble.textContent =
              "L'assistant n'a pas pu répondre après 3 tentatives" +
              statusLabel +
              ". Veuillez reformuler votre question ou réessayer.";
            errLi.appendChild(errAuthor);
            errLi.appendChild(errBubble);
            log.appendChild(errLi);
            log.scrollTop = log.scrollHeight;
          }
        })
        .finally(function () {
          form.removeAttribute("data-chat-busy");
          if (submitBtn) submitBtn.removeAttribute("disabled");
          if (textarea) textarea.focus();
        });
    }
  });

  // Dropzone file preview
  var fileInput = document.getElementById("ingest-files");
  var previewList = document.getElementById("ingest-preview-list");
  if (fileInput && previewList) {
    fileInput.addEventListener("change", function () {
      previewList.innerHTML = "";
      var files = fileInput.files || [];
      for (var i = 0; i < files.length; i++) {
        var li = document.createElement("li");
        li.className = "ds-file-list__item";
        var nameSpan = document.createElement("span");
        nameSpan.className = "ds-file-list__name";
        nameSpan.textContent = files[i].name;
        var sizeSpan = document.createElement("span");
        sizeSpan.className = "ds-badge ds-badge--neutral ds-badge--sm";
        sizeSpan.textContent = Math.max(1, Math.round(files[i].size / 1024)) + " Ko";
        li.appendChild(nameSpan);
        li.appendChild(sizeSpan);
        previewList.appendChild(li);
      }
    });
  }

  // Smart hovercard & tooltip flip when close to the top or right edge of the viewport
  function adjustFloatingOverlay(el) {
    if (!el || typeof el.getBoundingClientRect !== "function") return;
    var rect = el.getBoundingClientRect();
    if (el.classList.contains("ds-hovercard")) {
      el.classList.toggle("ds-hovercard--flip", rect.top < 220);
      var alignRight =
        rect.left + 320 > window.innerWidth && rect.left > window.innerWidth * 0.4;
      el.classList.toggle("ds-hovercard--align-right", alignRight);
    }
    if (el.hasAttribute("data-tooltip")) {
      if (rect.top < 90) {
        el.setAttribute("data-tooltip-flip", "bottom");
      } else {
        el.removeAttribute("data-tooltip-flip");
      }
    }
  }
  document.addEventListener(
    "mouseover",
    function (e) {
      var hc = e.target.closest(".ds-hovercard");
      if (hc && (!e.relatedTarget || !hc.contains(e.relatedTarget))) {
        adjustFloatingOverlay(hc);
      }
      var tt = e.target.closest("[data-tooltip]");
      if (tt && (!e.relatedTarget || !tt.contains(e.relatedTarget))) {
        adjustFloatingOverlay(tt);
      }
    },
    { passive: true },
  );
  document.addEventListener("focusin", function (e) {
    var hc = e.target.closest(".ds-hovercard");
    if (hc) adjustFloatingOverlay(hc);
    var tt = e.target.closest("[data-tooltip]");
    if (tt) adjustFloatingOverlay(tt);
  });

  // Client-side worklist column sorting on <table id="worklist">
  document.addEventListener("click", function (e) {
    var sortTrigger = e.target.closest("[data-sort-trigger]");
    if (!sortTrigger) return;
    var th = sortTrigger.closest("th");
    var table = sortTrigger.closest("table");
    var tbody = table ? table.querySelector("tbody") : null;
    if (!th || !table || !tbody) return;

    e.preventDefault();
    var colIdx = Number(sortTrigger.getAttribute("data-sort-trigger") || "0");
    var currentSort = th.getAttribute("aria-sort");
    var nextDir = currentSort === "ascending" ? "descending" : "ascending";

    table.querySelectorAll("thead th").forEach(function (headerEl) {
      headerEl.setAttribute("aria-sort", "none");
      var link = headerEl.querySelector(".ds-sort");
      var icon = headerEl.querySelector(".ds-sort__icon");
      if (link) link.classList.remove("is-sorted");
      if (icon) icon.textContent = "↕";
    });

    th.setAttribute("aria-sort", nextDir);
    sortTrigger.classList.add("is-sorted");
    var activeIcon = sortTrigger.querySelector(".ds-sort__icon");
    if (activeIcon) activeIcon.textContent = nextDir === "ascending" ? "↑" : "↓";

    var rows = Array.prototype.slice.call(tbody.querySelectorAll("tr"));
    rows.sort(function (rowA, rowB) {
      var cellA = rowA.children[colIdx];
      var cellB = rowB.children[colIdx];
      var valA = (cellA && (cellA.getAttribute("data-sort-value") || cellA.textContent)) || "";
      var valB = (cellB && (cellB.getAttribute("data-sort-value") || cellB.textContent)) || "";
      var numA = Number(valA);
      var numB = Number(valB);
      var cmp = 0;
      if (!Number.isNaN(numA) && !Number.isNaN(numB) && valA !== "" && valB !== "") {
        cmp = numA - numB;
      } else {
        cmp = String(valA).localeCompare(String(valB), "fr", { sensitivity: "base" });
      }
      return nextDir === "ascending" ? cmp : -cmp;
    });

    rows.forEach(function (r) {
      tbody.appendChild(r);
    });
  });

  // Live client-side filter for the Guidelines left document menu
  document.addEventListener("input", function (e) {
    var searchInput = e.target.closest("[data-guideline-search]");
    if (!searchInput) return;
    var query = String(searchInput.value || "").trim().toLowerCase();
    document.querySelectorAll("[data-guideline-item]").forEach(function (item) {
      var name = (item.getAttribute("data-guideline-item") || "").toLowerCase();
      item.style.display = !query || name.indexOf(query) !== -1 ? "" : "none";
    });
  });

  // Live Specialty Focus Highlighting on the RCP Agenda (/agenda) via selector or card badge
  function applyAgendaSpecialtyFocus(nextExpert) {
    var agendaList = document.querySelector("[data-testid='agenda-items-list']");
    if (!agendaList) return;

    var selectEl = document.querySelector("[data-agenda-focus-select]");
    if (selectEl && selectEl.value !== nextExpert) {
      selectEl.value = nextExpert;
      selectEl.dispatchEvent(new Event("change", { bubbles: false }));
    }

    document.querySelectorAll("[data-focus-expert]").forEach(function (el) {
      var exp = (el.getAttribute("data-focus-expert") || "").trim();
      var isActive = nextExpert === "" ? exp === "" : exp === nextExpert;
      el.setAttribute("aria-pressed", isActive ? "true" : "false");
      if (el.classList.contains("ds-agenda-item__exp-badge")) {
        el.classList.toggle("ds-badge--focused-specialty", nextExpert !== "" && exp === nextExpert);
      }
    });

    agendaList.querySelectorAll(".ds-agenda-item[data-required-experts]").forEach(function (row) {
      var raw = row.getAttribute("data-required-experts") || "";
      var requiredList = raw ? raw.split("|") : [];
      if (!nextExpert) {
        row.classList.remove("ds-agenda-item--focused", "ds-agenda-item--dimmed");
      } else {
        var matches = requiredList.indexOf(nextExpert) !== -1;
        row.classList.toggle("ds-agenda-item--focused", matches);
        row.classList.toggle("ds-agenda-item--dimmed", !matches);
      }
    });

    try {
      var nextUrl = new URL(window.location.href);
      if (nextExpert) {
        nextUrl.searchParams.set("focusExpert", nextExpert);
      } else {
        nextUrl.searchParams.delete("focusExpert");
      }
      window.history.replaceState({}, "", nextUrl.toString());
    } catch (_err) {}
  }

  document.addEventListener("change", function (e) {
    var focusSelect = e.target.closest("[data-agenda-focus-select]");
    if (!focusSelect) return;
    applyAgendaSpecialtyFocus((focusSelect.value || "").trim());
  });

  document.addEventListener("click", function (e) {
    var focusTrigger = e.target.closest("[data-focus-expert]");
    if (!focusTrigger) return;
    e.preventDefault();
    var clickedExpert = (focusTrigger.getAttribute("data-focus-expert") || "").trim();
    var currentlyPressed = focusTrigger.getAttribute("aria-pressed") === "true";
    var nextExpert = !clickedExpert || currentlyPressed ? "" : clickedExpert;
    applyAgendaSpecialtyFocus(nextExpert);
  });

  // Desktop Drag-and-Drop reordering on the RCP Agenda passage rank badge (.ds-agenda-item__rank)
  // Holding the mouse button on the rank number lifts the card directly under the cursor so it follows the mouse 1:1.
  var agendaDragState = null;

  function getAgendaRows(list) {
    return list ? Array.prototype.slice.call(list.querySelectorAll(".ds-agenda-item")) : [];
  }

  function renumberAgendaItems(list, activeState) {
    if (!list) return;
    if (activeState && activeState.placeholder && activeState.row) {
      var slots = Array.prototype.slice
        .call(list.children)
        .filter(function (el) {
          return (
            el !== activeState.row &&
            (el.classList.contains("ds-agenda-item") || el === activeState.placeholder)
          );
        });
      slots.forEach(function (slot, idx) {
        var row = slot === activeState.placeholder ? activeState.row : slot;
        var pos = idx + 1;
        row.setAttribute("data-position", String(pos));
        var posEl = row.querySelector(".ds-agenda-item__pos");
        if (posEl) posEl.textContent = "#" + pos;
        var rankEl = row.querySelector(".ds-agenda-item__rank");
        if (rankEl) rankEl.setAttribute("aria-label", "Rang de passage " + pos);
      });
      return;
    }

    getAgendaRows(list).forEach(function (row, idx) {
      var pos = idx + 1;
      row.setAttribute("data-position", String(pos));
      var posEl = row.querySelector(".ds-agenda-item__pos");
      if (posEl) posEl.textContent = "#" + pos;
      var rankEl = row.querySelector(".ds-agenda-item__rank");
      if (rankEl) rankEl.setAttribute("aria-label", "Rang de passage " + pos);
    });
  }

  function persistAgendaMove(list, patientId, targetPosition) {
    if (!list || !patientId || !targetPosition) return;
    var domain = list.getAttribute("data-domain");
    var form = document.createElement("form");
    form.method = "post";
    form.action =
      "/agenda/patients/" +
      encodeURIComponent(patientId) +
      "/move" +
      (domain ? "?domain=" + encodeURIComponent(domain) : "");
    form.style.display = "none";

    var posInput = document.createElement("input");
    posInput.type = "hidden";
    posInput.name = "targetPosition";
    posInput.value = String(targetPosition);
    form.appendChild(posInput);

    var pinInput = document.createElement("input");
    pinInput.type = "hidden";
    pinInput.name = "pinned";
    pinInput.value = "true";
    form.appendChild(pinInput);

    document.body.appendChild(form);
    form.submit();
  }

  function cleanupFloatingAgendaRow(row) {
    if (!row) return;
    row.classList.remove("is-dragging");
    row.style.position = "";
    row.style.left = "";
    row.style.top = "";
    row.style.width = "";
    row.style.height = "";
    row.style.margin = "";
    row.style.zIndex = "";
    row.style.pointerEvents = "";
    row.style.transform = "";
    row.style.transition = "";
  }

  function finalizeAgendaDrag(state, cancelled) {
    if (!state || state.finalized) return;
    state.finalized = true;
    agendaDragState = null;

    if (state.placeholder && state.placeholder.parentNode) {
      if (cancelled) {
        var currentRows = getAgendaRows(state.list).filter(function (r) {
          return r !== state.row;
        });
        var refRow = currentRows[state.initialIndex] || null;
        state.placeholder.remove();
        if (refRow) {
          refRow.before(state.row);
        } else {
          state.list.appendChild(state.row);
        }
      } else {
        state.placeholder.replaceWith(state.row);
      }
    }

    cleanupFloatingAgendaRow(state.row);
    renumberAgendaItems(state.list, null);

    if (cancelled) return;
    var rows = getAgendaRows(state.list);
    var finalIndex = rows.indexOf(state.row);
    if (finalIndex !== -1 && finalIndex !== state.initialIndex && state.patientId) {
      persistAgendaMove(state.list, state.patientId, finalIndex + 1);
    }
  }

  function startAgendaDrag(e) {
    if (typeof e.button === "number" && e.button !== 0) return;
    var handle = e.target && e.target.closest ? e.target.closest("[data-agenda-drag-handle]") : null;
    if (!handle || agendaDragState) return;
    if (window.matchMedia && !window.matchMedia("(min-width: 48rem)").matches) {
      return;
    }
    var row = handle.closest(".ds-agenda-item");
    var list = row ? row.closest("[data-testid='agenda-items-list']") : null;
    if (!row || !list) return;

    e.preventDefault();
    var rows = getAgendaRows(list);
    var initialIndex = rows.indexOf(row);
    var patientId = row.getAttribute("data-patient-id") || "";
    var rect = row.getBoundingClientRect();

    var placeholder = document.createElement("li");
    placeholder.className = "ds-agenda-item-placeholder";
    placeholder.setAttribute("aria-hidden", "true");
    placeholder.style.height = rect.height + "px";
    row.before(placeholder);

    row.classList.add("is-dragging");
    row.style.position = "fixed";
    row.style.left = rect.left + "px";
    row.style.top = rect.top + "px";
    row.style.width = rect.width + "px";
    row.style.height = rect.height + "px";
    row.style.margin = "0";
    row.style.zIndex = "1000";
    row.style.pointerEvents = "none";
    row.style.transform = "translate3d(0, 0, 0)";
    row.style.transition = "box-shadow 150ms cubic-bezier(0.2, 0, 0, 1)";

    agendaDragState = {
      row: row,
      list: list,
      placeholder: placeholder,
      patientId: patientId,
      initialIndex: initialIndex,
      startX: e.clientX,
      startY: e.clientY,
      finalized: false,
    };
  }

  function moveAgendaDrag(e) {
    if (!agendaDragState) return;
    var dx = e.clientX - agendaDragState.startX;
    var dy = e.clientY - agendaDragState.startY;
    agendaDragState.row.style.transform = "translate3d(" + dx + "px, " + dy + "px, 0)";

    // Auto-scroll viewport when dragging near top or bottom edges
    var edgeZone = 72;
    if (e.clientY < edgeZone) {
      window.scrollBy(0, -12);
    } else if (e.clientY > window.innerHeight - edgeZone) {
      window.scrollBy(0, 12);
    }

    var elUnder = document.elementFromPoint(e.clientX, e.clientY);
    var overRow = elUnder && elUnder.closest ? elUnder.closest(".ds-agenda-item") : null;
    if (
      !overRow ||
      overRow === agendaDragState.row ||
      overRow.closest("[data-testid='agenda-items-list']") !== agendaDragState.list
    ) {
      return;
    }

    var overRect = overRow.getBoundingClientRect();
    var midpoint = overRect.top + overRect.height / 2;
    if (e.clientY < midpoint) {
      if (agendaDragState.placeholder.nextElementSibling !== overRow) {
        overRow.before(agendaDragState.placeholder);
        renumberAgendaItems(agendaDragState.list, agendaDragState);
      }
    } else {
      if (agendaDragState.placeholder.previousElementSibling !== overRow) {
        overRow.after(agendaDragState.placeholder);
        renumberAgendaItems(agendaDragState.list, agendaDragState);
      }
    }
  }

  function endAgendaDrag() {
    if (!agendaDragState) return;
    finalizeAgendaDrag(agendaDragState, false);
  }

  document.addEventListener("pointerdown", startAgendaDrag);
  document.addEventListener("mousedown", startAgendaDrag);
  window.addEventListener("pointermove", moveAgendaDrag, { passive: true });
  window.addEventListener("mousemove", moveAgendaDrag, { passive: true });
  window.addEventListener("pointerup", endAgendaDrag);
  window.addEventListener("mouseup", endAgendaDrag);

  window.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && agendaDragState) {
      finalizeAgendaDrag(agendaDragState, true);
    }
  });

  // =========================================================================
  // 20. Mobile PDF Canvas Renderer (self-hosted PDF.js for mobile viewports)
  // =========================================================================
  var pdfJsPromise = null;
  function loadLocalPdfJs() {
    if (!pdfJsPromise) {
      pdfJsPromise = import("/public/vendor/pdfjs/pdf.mjs").then(function (mod) {
        if (mod && mod.GlobalWorkerOptions) {
          mod.GlobalWorkerOptions.workerSrc = new URL(
            "/public/vendor/pdfjs/pdf.worker.mjs",
            window.location.origin,
          ).href;
        }
        return mod;
      });
    }
    return pdfJsPromise;
  }

  function renderMobilePdfCanvas(viewerEl) {
    var pdfUrl = viewerEl.getAttribute("data-pdf-url");
    var filename = viewerEl.getAttribute("data-pdf-filename") || "document.pdf";
    if (!pdfUrl || viewerEl.getAttribute("data-pdf-rendered") === "loading") return;
    viewerEl.setAttribute("data-pdf-rendered", "loading");
    viewerEl.textContent = "";

    var barEl = document.createElement("div");
    barEl.className = "ds-pdf-canvas-viewer__bar";

    var statusEl = document.createElement("span");
    statusEl.setAttribute("data-pdf-status", "");
    statusEl.textContent = "Chargement du fichier source…";
    barEl.appendChild(statusEl);

    var actionsEl = document.createElement("div");
    actionsEl.className = "ds-cluster";
    actionsEl.style.gap = "var(--ds-space-2)";

    var openLink = document.createElement("a");
    openLink.className = "ds-btn ds-btn--ghost ds-btn--sm";
    openLink.href = pdfUrl;
    openLink.target = "_blank";
    openLink.rel = "noopener";
    openLink.textContent = "Ouvrir";
    actionsEl.appendChild(openLink);

    var dlLink = document.createElement("a");
    dlLink.className = "ds-btn ds-btn--secondary ds-btn--sm";
    dlLink.href = pdfUrl;
    dlLink.setAttribute("download", filename);
    dlLink.textContent = "Télécharger";
    actionsEl.appendChild(dlLink);

    barEl.appendChild(actionsEl);
    viewerEl.appendChild(barEl);

    var pagesEl = document.createElement("div");
    pagesEl.className = "ds-pdf-canvas-viewer__pages";
    pagesEl.setAttribute("data-pdf-pages", "");
    viewerEl.appendChild(pagesEl);

    Promise.all([
      loadLocalPdfJs(),
      fetch(pdfUrl, { credentials: "same-origin" }).then(function (res) {
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.arrayBuffer();
      }),
    ])
      .then(function (results) {
        var pdfjs = results[0];
        var buffer = results[1];
        return pdfjs.getDocument({
          data: new Uint8Array(buffer),
          useSystemFonts: true,
        }).promise;
      })
      .then(function (pdfDoc) {
        var total = pdfDoc.numPages || 1;
        statusEl.textContent = total + (total > 1 ? " pages" : " page");
        var dpr = Math.min(window.devicePixelRatio || 1, 2);
        var containerWidth = Math.max(260, pagesEl.clientWidth || viewerEl.clientWidth || 340);

        var chain = Promise.resolve();
        var _loop = function (pageNum) {
          chain = chain.then(function () {
            return pdfDoc.getPage(pageNum).then(function (page) {
              var unscaled = page.getViewport({ scale: 1 });
              var cssScale = containerWidth / Math.max(1, unscaled.width);
              var viewport = page.getViewport({ scale: cssScale * dpr });
              var canvas = document.createElement("canvas");
              canvas.className = "ds-pdf-canvas-viewer__canvas";
              canvas.width = Math.floor(viewport.width);
              canvas.height = Math.floor(viewport.height);
              pagesEl.appendChild(canvas);
              var ctx = canvas.getContext("2d");
              if (!ctx) return;
              return page.render({ canvasContext: ctx, viewport: viewport }).promise;
            });
          });
        };
        for (var p = 1; p <= total; p++) {
          _loop(p);
        }
        return chain.then(function () {
          viewerEl.setAttribute("data-pdf-rendered", "true");
        });
      })
      .catch(function (err) {
        pdfJsPromise = null;
        viewerEl.setAttribute("data-pdf-rendered", "error");
        statusEl.textContent =
          "Aperçu indisponible (" +
          (err && err.message ? err.message : "erreur") +
          ") — utilisez « Ouvrir » ou « Télécharger ».";
      });
  }

  // =========================================================================
  // 21. Live SSE Queue Banner & In-Progress Fiche Auto-Refresh Controller
  // =========================================================================
  var isAutoRefreshing = false;
  var lastRefreshAt = 0;

  function canSafelyAutoRefresh() {
    if (isAutoRefreshing) return false;
    if (document.hidden) return false;
    if (document.querySelector("dialog[open]")) return false;
    if (document.querySelector(".ds-section.is-editing, [data-chat-busy='true']")) return false;
    var active = document.activeElement;
    if (
      active &&
      (active.tagName === "INPUT" ||
        active.tagName === "TEXTAREA" ||
        active.tagName === "SELECT" ||
        active.isContentEditable)
    ) {
      return false;
    }
    return true;
  }

  function snapshotOpenDetails(scopeEl) {
    var openKeys = {};
    (scopeEl || document).querySelectorAll("details[open]").forEach(function (d) {
      var key = d.id || d.getAttribute("data-testid");
      if (key) openKeys[key] = true;
    });
    return openKeys;
  }

  function restoreOpenDetails(scopeEl, openKeys) {
    (scopeEl || document).querySelectorAll("details").forEach(function (d) {
      var key = d.id || d.getAttribute("data-testid");
      if (key && Object.prototype.hasOwnProperty.call(openKeys, key)) {
        d.open = Boolean(openKeys[key]);
      }
    });
  }

  function softRefreshCurrentPage() {
    if (!canSafelyAutoRefresh()) return;
    var now = Date.now();
    if (now - lastRefreshAt < 1800) return;
    isAutoRefreshing = true;
    lastRefreshAt = now;

    fetch(window.location.href, {
      method: "GET",
      credentials: "same-origin",
      cache: "no-store",
      headers: { "X-Requested-With": "AutoRefresh" },
    })
      .then(function (res) {
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.text();
      })
      .then(function (htmlText) {
        if (!canSafelyAutoRefresh()) return;
        var parser = new DOMParser();
        var nextDoc = parser.parseFromString(htmlText, "text/html");

        var nextBanner = nextDoc.getElementById("queue-banner");
        var curBanner = document.getElementById("queue-banner");
        if (nextBanner && curBanner) {
          curBanner.outerHTML = nextBanner.outerHTML;
        }

        var nextDrawerBody = nextDoc.getElementById("queue-drawer-body");
        var curDrawerBody = document.getElementById("queue-drawer-body");
        if (nextDrawerBody && curDrawerBody) {
          curDrawerBody.innerHTML = nextDrawerBody.innerHTML;
        }

        var curMain = document.getElementById("main");
        var nextMain = nextDoc.getElementById("main");
        if (!curMain || !nextMain) return;

        var openDetailsMap = snapshotOpenDetails(curMain);

        // On Dossier view, update synoptic & clinical panels in-place so the PDF iframe never reloads
        var curSplit = document.getElementById("dossier-split-view");
        var nextSplit = nextDoc.getElementById("dossier-split-view");
        if (curSplit && nextSplit) {
          var curSynoptic = curMain.querySelector(".ds-synoptic");
          var nextSynoptic = nextMain.querySelector(".ds-synoptic");
          if (curSynoptic && nextSynoptic) {
            curSynoptic.outerHTML = nextSynoptic.outerHTML;
          }
          ["panel-clinical", "panel-opinions", "panel-expert"].forEach(function (panelId) {
            var curPanel = document.getElementById(panelId);
            var nextPanel = nextDoc.getElementById(panelId);
            if (curPanel && nextPanel) {
              curPanel.innerHTML = nextPanel.innerHTML;
            }
          });
          ["tab-clinical", "tab-opinions", "tab-expert"].forEach(function (tabId) {
            var curTab = document.getElementById(tabId);
            var nextTab = nextDoc.getElementById(tabId);
            if (curTab && nextTab) {
              curTab.innerHTML = nextTab.innerHTML;
            }
          });
          restoreOpenDetails(curMain, openDetailsMap);
          initM3Tabs(curMain);
          initM3Selects(curMain);
          initM3TextFields(curMain);
          centerActiveTimelineStep(curMain);
        } else {
          curMain.innerHTML = nextMain.innerHTML;
          syncMobileCollapsibleDrawers();
          syncMobileWorklistDefaultDisplay();
          restoreOpenDetails(curMain, openDetailsMap);
          initM3Tabs(curMain);
          initM3Selects(curMain);
          initM3TextFields(curMain);
          centerActiveTimelineStep(curMain);
        }
      })
      .catch(function () {})
      .finally(function () {
        isAutoRefreshing = false;
      });
  }

  // Poll auto-refresh every 4s while any fiche on the current page is marked as processing
  window.setInterval(function () {
    if (document.querySelector('[data-processing-active="true"]')) {
      softRefreshCurrentPage();
    }
  }, 4000);

  if (typeof window.EventSource === "function" && document.getElementById("queue-banner")) {
    try {
      var es = new EventSource("/events/queue");
      es.addEventListener("banner", function (ev) {
        var current = document.getElementById("queue-banner");
        if (!current || !ev.data) return;
        var prevActive = current.getAttribute("data-queue-active");
        var prevCompleted = current.getAttribute("data-queue-completed");
        var prevActiveFile = current.getAttribute("data-active-file");

        current.outerHTML = ev.data;

        var updated = document.getElementById("queue-banner");
        if (!updated) return;
        var nextActive = updated.getAttribute("data-queue-active");
        var nextCompleted = updated.getAttribute("data-queue-completed");
        var nextActiveFile = updated.getAttribute("data-active-file");

        var hasPageProcessing = Boolean(document.querySelector('[data-processing-active="true"]'));
        var queueStateChanged =
          prevActive !== nextActive ||
          prevCompleted !== nextCompleted ||
          prevActiveFile !== nextActiveFile;

        if (hasPageProcessing && (queueStateChanged || nextActive === "true")) {
          softRefreshCurrentPage();
        }
      });
    } catch (_err) {}
  }
})();
