(() => {
  // ../frappe_ticktix/frappe_ticktix/public/js/help_menu.bundle.js
  document.addEventListener(
    "click",
    (e) => {
      const a = e.target.closest && e.target.closest("#toolbar-help a.dropdown-item[href]");
      if (!a || e.defaultPrevented || e.button !== 0)
        return;
      let url;
      try {
        url = new URL(a.href, window.location.href);
      } catch (err) {
        return;
      }
      if (url.origin === window.location.origin)
        return;
      e.preventDefault();
      e.stopPropagation();
      window.open(url.href, "_blank", "noopener");
    },
    true
  );
})();
//# sourceMappingURL=help_menu.bundle.C6PUBA4K.js.map
