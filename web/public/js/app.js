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
      });
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
        '<svg class="ds-icon ds-icon--xs" aria-hidden="true" viewBox="0 0 24 24"><path d="m6 9.5 6 6 6-6"/></svg>';

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
          if (ev.key === "Enter" || ev.key === " ") {
            chooseOption(ev);
          }
        });
        panel.appendChild(li);
      });

      syncFromSelect();
      select.addEventListener("change", syncFromSelect);

      trigger.addEventListener("click", function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        var willOpen = !wrapper.classList.contains("is-open");
        closeAllMenus(wrapper);
        wrapper.classList.toggle("is-open", willOpen);
        trigger.setAttribute("aria-expanded", willOpen ? "true" : "false");
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
    if (drawer) {
      drawer.classList.toggle("is-keyboard-open", keyboardLikelyOpen);
      if (drawer.classList.contains("is-open") && keyboardLikelyOpen) {
        var log = drawer.querySelector(".ds-chat__log");
        if (log) {
          log.scrollTop = log.scrollHeight;
        }
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
        "a, button, summary, details, input, select, textarea, dialog, form, label, .ds-m3-select, .ds-hovercard, .ds-field__clear",
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

    var pdfExpandBtn = e.target.closest("[data-action='toggle-pdf-expand']");
    if (pdfExpandBtn) {
      closeAllMenus(null);
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
      var promptText = promptChip.getAttribute("data-quick-prompt") || "";
      var targetInputId = promptChip.getAttribute("data-target-input") || "chat-input";
      var inputEl = document.getElementById(targetInputId);
      if (inputEl) {
        inputEl.value = promptText;
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
      var dlg = document.getElementById(openBtn.getAttribute("data-open"));
      if (dlg && typeof dlg.showModal === "function") {
        dlg.showModal();
      }
    }
    var closeBtn = e.target.closest("[data-close]");
    if (closeBtn) {
      var cDlg = document.getElementById(closeBtn.getAttribute("data-close"));
      if (cDlg && typeof cDlg.close === "function") {
        cDlg.close();
      }
    }
  });

  // ARIA tabs navigation with M3 GPU FLIP sliding indicator (zero stutter)
  var prefersReducedMotion =
    window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function animateFlipElement(targetEl, fromRect, opts) {
    if (
      prefersReducedMotion ||
      !targetEl ||
      !fromRect ||
      typeof targetEl.animate !== "function"
    ) {
      return;
    }
    var toRect = targetEl.getBoundingClientRect();
    if (!toRect.width || !toRect.height) return;
    var dx = fromRect.left + fromRect.width / 2 - (toRect.left + toRect.width / 2);
    var dy = fromRect.top + fromRect.height / 2 - (toRect.top + toRect.height / 2);
    var sx = Math.max(0.25, Math.min(3.5, fromRect.width / toRect.width));
    var sy = opts && opts.lockY ? 1 : Math.max(0.5, Math.min(2.5, fromRect.height / toRect.height));
    if (Math.abs(dx) < 1 && Math.abs(dy) < 1 && Math.abs(sx - 1) < 0.02) return;
    try {
      targetEl.animate(
        [
          {
            transform:
              "translate3d(" +
              dx.toFixed(1) +
              "px, " +
              (opts && opts.lockY ? "0px" : dy.toFixed(1) + "px") +
              ", 0) scale(" +
              sx.toFixed(3) +
              ", " +
              sy.toFixed(3) +
              ")",
          },
          { transform: "translate3d(0, 0, 0) scale(1, 1)" },
        ],
        {
          duration: (opts && opts.duration) || 220,
          easing: "cubic-bezier(0.2, 0, 0, 1)",
          pseudoElement: (opts && opts.pseudoElement) || undefined,
        },
      );
    } catch (_err) {}
  }

  document.querySelectorAll(".ds-tabs[role='tablist']").forEach(function (tablist) {
    var tabs = Array.prototype.slice.call(tablist.querySelectorAll("[role='tab']"));
    function selectTab(idx, focus) {
      var prevTab = tablist.querySelector("[role='tab'][aria-selected='true']");
      var prevRect = prevTab ? prevTab.getBoundingClientRect() : null;
      tabs.forEach(function (t, i) {
        var on = i === idx;
        t.setAttribute("aria-selected", String(on));
        t.tabIndex = on ? 0 : -1;
        var panelId = t.getAttribute("aria-controls");
        var panel = panelId ? document.getElementById(panelId) : null;
        if (panel) panel.hidden = !on;
      });
      var nextTab = tabs[idx];
      if (nextTab && prevTab && nextTab !== prevTab && prevRect) {
        animateFlipElement(nextTab, prevRect, {
          lockY: true,
          duration: 220,
          pseudoElement: "::after",
        });
      }
      if (focus && nextTab) nextTab.focus();
    }
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

    try {
      var params = new URLSearchParams(window.location.search);
      var requestedTab = params.get("tab");
      if (requestedTab) {
        tabs.forEach(function (t, i) {
          if (t.id === "tab-" + requestedTab) selectTab(i, false);
        });
      }
    } catch (_e) {}
  });

  // Smooth M3 FLIP button-to-button transition for Segmented Controls, Chips, Nav Rail & Bottom Nav
  document.querySelectorAll(".ds-segmented").forEach(function (seg) {
    var lastCheckedLabel = seg.querySelector("input:checked + label");
    seg.addEventListener("change", function () {
      var nextCheckedLabel = seg.querySelector("input:checked + label");
      if (lastCheckedLabel && nextCheckedLabel && lastCheckedLabel !== nextCheckedLabel) {
        animateFlipElement(nextCheckedLabel, lastCheckedLabel.getBoundingClientRect(), {
          lockY: true,
          duration: 200,
        });
      }
      lastCheckedLabel = nextCheckedLabel;
    });
  });

  // Cross-page & instant M3 Navigation Pill FLIP (Left Rail & Mobile Bottom Nav)
  function captureNavFlip(groupKey, fromEl, toEl, pillSelector) {
    if (!fromEl || !toEl || fromEl === toEl) return;
    var fromPill = pillSelector ? fromEl.querySelector(pillSelector) || fromEl : fromEl;
    var toPill = pillSelector ? toEl.querySelector(pillSelector) || toEl : toEl;
    var rect = fromPill.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    try {
      sessionStorage.setItem(
        "ds_flip_" + groupKey,
        JSON.stringify({
          left: rect.left,
          top: rect.top,
          width: rect.width,
          height: rect.height,
          ts: Date.now(),
        }),
      );
    } catch (_err) {}
    fromEl.removeAttribute("aria-current");
    toEl.setAttribute("aria-current", "page");
    animateFlipElement(toPill, rect, { duration: 220 });
  }

  document.addEventListener("click", function (e) {
    if (e.defaultPrevented || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    var navLink = e.target.closest(".ds-nav__link");
    if (navLink) {
      var prevNav = document.querySelector(".ds-nav__link[aria-current='page']");
      captureNavFlip("rail", prevNav, navLink, ".ds-nav__indicator");
      return;
    }
    var bottomLink = e.target.closest(".ds-bottom-nav__item");
    if (bottomLink) {
      var prevBottom = document.querySelector(".ds-bottom-nav__item[aria-current='page']");
      captureNavFlip("bottom", prevBottom, bottomLink, ".ds-bottom-nav__pill");
    }
  });

  ["rail", "bottom"].forEach(function (groupKey) {
    try {
      var raw = sessionStorage.getItem("ds_flip_" + groupKey);
      if (!raw) return;
      sessionStorage.removeItem("ds_flip_" + groupKey);
      var saved = JSON.parse(raw);
      if (!saved || Date.now() - (saved.ts || 0) > 2500) return;
      var activePill =
        groupKey === "rail"
          ? document.querySelector(".ds-nav__link[aria-current='page'] .ds-nav__indicator")
          : document.querySelector(".ds-bottom-nav__item[aria-current='page'] .ds-bottom-nav__pill");
      if (activePill) {
        animateFlipElement(activePill, saved, { duration: 220 });
      }
    } catch (_err) {}
  });

  // Inline section edit link (progressive enhancement)
  document.addEventListener("click", function (e) {
    var editLink = e.target.closest("[data-edit-section]");
    if (!editLink) return;
    var targetId = editLink.getAttribute("data-edit-section");
    var href = editLink.getAttribute("href");
    if (!targetId || !href) return;
    e.preventDefault();
    fetch(href, { headers: { "HX-Request": "true" } })
      .then(function (r) {
        return r.text();
      })
      .then(function (html) {
        var host = document.getElementById(targetId);
        if (host) {
          host.outerHTML = html;
          initM3TextFields(document);
        }
      });
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
          return r.text();
        })
        .then(function (html) {
          var host = document.getElementById(secId);
          if (host) host.outerHTML = html;
        });
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
        .catch(function () {
          if (timerInterval) window.clearInterval(timerInterval);
          if (log) {
            log.querySelectorAll("[data-chat-temp='true']").forEach(function (el) {
              el.remove();
            });
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

  // Live SSE Queue Banner stream
  if (typeof window.EventSource === "function" && document.getElementById("queue-banner")) {
    try {
      var es = new EventSource("/events/queue");
      es.addEventListener("banner", function (ev) {
        var current = document.getElementById("queue-banner");
        if (current && ev.data) {
          current.outerHTML = ev.data;
        }
      });
    } catch (_err) {}
  }
})();
