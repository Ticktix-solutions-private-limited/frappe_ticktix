// Help menu: external links (e.g. Documentation, About) open in a new tab.
// They stay real <a href> links, so the browser still shows the URL preview on hover.
document.addEventListener(
	"click",
	(e) => {
		const a = e.target.closest && e.target.closest("#toolbar-help a.dropdown-item[href]");
		if (!a || e.defaultPrevented || e.button !== 0) return;
		let url;
		try {
			url = new URL(a.href, window.location.href);
		} catch (err) {
			return;
		}
		if (url.origin === window.location.origin) return;
		e.preventDefault();
		e.stopPropagation();
		window.open(url.href, "_blank", "noopener");
	},
	true
);
