frappe.provide("frappe.ticktix");

frappe.pages["live-geo-tracking-map"].on_page_load = function (wrapper) {
	frappe.ticktix.live_geo_tracking_map = new frappe.ticktix.LiveGeoTrackingMap(wrapper);
};

frappe.ticktix.LiveGeoTrackingMap = class LiveGeoTrackingMap {
	constructor(wrapper) {
		this.wrapper = wrapper;
		this.page = frappe.ui.make_app_page({
			parent: wrapper,
			title: __("Live Geo Tracking Map"),
			single_column: true,
		});

		this.make_filters();
		this.make_map();
	}

	make_filters() {
		this.employee_field = this.page.add_field({
			label: __("Employee"),
			fieldname: "employee",
			fieldtype: "Link",
			options: "Employee",
			reqd: 1,
		});

		this.single_date_field = this.page.add_field({
			label: __("Single Date"),
			fieldname: "single_date",
			fieldtype: "Date",
			description: __("Shows the full day when set"),
			change: () => {
				if (this.single_date_field.get_value()) {
					this.from_field.set_value("");
					this.to_field.set_value("");
				}
			},
		});

		this.from_field = this.page.add_field({
			label: __("From"),
			fieldname: "from_datetime",
			fieldtype: "Datetime",
			change: () => {
				if (this.from_field.get_value()) this.single_date_field.set_value("");
			},
		});

		this.to_field = this.page.add_field({
			label: __("To"),
			fieldname: "to_datetime",
			fieldtype: "Datetime",
			change: () => {
				if (this.to_field.get_value()) this.single_date_field.set_value("");
			},
		});

		this.page.set_primary_action(__("Show on Map"), () => this.load_and_render(), "refresh");
	}

	make_map() {
		// The filter row (page-form) must render its Link-field suggestion
		// dropdown above the map. Leaflet's internal panes/controls use
		// z-index values up to 1000, which otherwise beat the dropdown's
		// z-index (4) since both are compared in the same stacking context.
		// Giving the filter row an explicit higher z-index, and wrapping the
		// map in its own stacking context (position + z-index), contains
		// Leaflet's internal stacking so it never climbs above the filters.
		this.page.page_form.css({ position: "relative", "z-index": 1000 });

		this.$map_area = $(
			`<div class="live-geo-tracking-map-area" style="margin-top: 15px; position: relative; z-index: 1;">
				<div class="live-geo-tracking-map-summary text-muted small" style="margin-bottom: 8px;"></div>
				<div class="live-geo-tracking-map-container" style="height: calc(100vh - 200px); width: 100%; border-radius: 4px; position: relative; z-index: 1;"></div>
			</div>`
		).appendTo(this.page.main);

		this.map_id = frappe.dom.get_unique_id();
		this.$map_area.find(".live-geo-tracking-map-container").attr("id", this.map_id);

		L.Icon.Default.imagePath = frappe.utils.map_defaults.image_path;
		this.map = L.map(this.map_id).setView(
			frappe.utils.map_defaults.center,
			frappe.utils.map_defaults.zoom
		);
		L.tileLayer(frappe.utils.map_defaults.tiles, frappe.utils.map_defaults.options).addTo(
			this.map
		);
		L.control.scale().addTo(this.map);

		// Leaflet computes the map size from its container at init time. If the
		// container was hidden/zero-sized during page transition (common for
		// Desk pages), the map renders tiny until we force a resize check once
		// the page is actually laid out and visible.
		this.fix_map_size();
		$(window).on(`resize.${this.map_id}`, () => this.fix_map_size());
		$(this.wrapper).on("show", () => this.fix_map_size());
	}

	fix_map_size() {
		if (!this.map) return;
		setTimeout(() => this.map && this.map.invalidateSize(), 200);
		setTimeout(() => this.map && this.map.invalidateSize(), 600);
	}

	get_time_range() {
		const single_date = this.single_date_field.get_value();
		if (single_date) {
			return {
				from_time: `${single_date} 00:00:00`,
				to_time: `${single_date} 23:59:59`,
			};
		}
		return {
			from_time: this.from_field.get_value() || null,
			to_time: this.to_field.get_value() || null,
		};
	}

	load_and_render() {
		const employee = this.employee_field.get_value();
		if (!employee) {
			frappe.msgprint(__("Please select an Employee"));
			return;
		}

		const { from_time, to_time } = this.get_time_range();

		frappe.dom.freeze(__("Loading tracking data..."));
		frappe
			.call({
				method: "frappe_ticktix.plugins.hr.geo_tracking.api.get_live_points",
				args: {
					employee,
					from_time,
					to_time,
					limit: 10000,
				},
			})
			.then((r) => {
				this.render_points(r.message || []);
			})
			.always(() => frappe.dom.unfreeze());
	}

	// Source (how the point was captured) gets its own marker color so the
	// trail visually distinguishes background pings, foreground pings and
	// punch-in/out events, in addition to the distinct start/end pins.
	get_source_color(source) {
		const colors = {
			background: "#3388ff",
			foreground: "#f39c12",
			punch: "#9b59b6",
		};
		return colors[source] || "#3388ff";
	}

	// Great-circle distance between two lat/lng points using the Haversine
	// formula, in kilometers.
	haversine_distance_km(lat1, lon1, lat2, lon2) {
		const to_rad = (deg) => (deg * Math.PI) / 180;
		const R = 6371; // Earth's mean radius in km
		const dLat = to_rad(lat2 - lat1);
		const dLon = to_rad(lon2 - lon1);
		const a =
			Math.sin(dLat / 2) ** 2 +
			Math.cos(to_rad(lat1)) * Math.cos(to_rad(lat2)) * Math.sin(dLon / 2) ** 2;
		const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
		return R * c;
	}

	// Sums the distance between every consecutive pair of points (in
	// chronological order) rather than just start-to-end, so an out-and-back
	// route (leave, travel far, return to the same spot) still reports the
	// full distance actually travelled instead of ~0.
	calculate_total_distance_km(points) {
		let total = 0;
		for (let i = 1; i < points.length; i++) {
			const prev = points[i - 1];
			const curr = points[i];
			total += this.haversine_distance_km(prev.lat, prev.long, curr.lat, curr.long);
		}
		return total;
	}

	// Small self-contained (no external icon assets) pin-style marker used
	// for the Start / End points so they stand out clearly from the plain
	// waypoint dots.
	make_pin_icon(color, label) {
		const size = 26;
		return L.divIcon({
			className: "live-geo-tracking-pin-icon",
			html: `<div style="
					width: ${size}px;
					height: ${size}px;
					background: ${color};
					border: 2px solid #fff;
					border-radius: 50% 50% 50% 0;
					transform: rotate(-45deg);
					box-shadow: 0 1px 4px rgba(0,0,0,0.5);
				">
					<span style="
						display: block;
						transform: rotate(45deg);
						text-align: center;
						line-height: ${size - 4}px;
						color: #fff;
						font-weight: bold;
						font-size: 11px;
					">${label}</span>
				</div>`,
			iconSize: [size, size],
			iconAnchor: [size / 2, size],
			popupAnchor: [0, -size],
		});
	}

	render_points(points) {
		if (this.marker_layer) {
			this.map.removeLayer(this.marker_layer);
			this.marker_layer = null;
		}
		if (this.polyline) {
			this.map.removeLayer(this.polyline);
			this.polyline = null;
		}
		if (this.polyline_outline) {
			this.map.removeLayer(this.polyline_outline);
			this.polyline_outline = null;
		}

		const $summary = this.$map_area.find(".live-geo-tracking-map-summary");

		if (!points.length) {
			$summary.text(__("No tracking data found for the selected filters."));
			return;
		}

		const latlngs = points.map((p) => [p.lat, p.long]);

		this.marker_layer = L.featureGroup();

		points.forEach((point, idx) => {
			const is_start = idx === 0;
			const is_end = idx === points.length - 1;

			const popup_lines = [
				`<b>${
					is_start ? __("Start") + " — " : is_end ? __("End") + " — " : ""
				}${frappe.datetime.str_to_user(point.device_date_time)}</b>`,
				`${__("Lat")}: ${point.lat}, ${__("Long")}: ${point.long}`,
			];
			if (point.speed != null) popup_lines.push(`${__("Speed")}: ${point.speed} m/s`);
			if (point.accuracy != null) popup_lines.push(`${__("Accuracy")}: ${point.accuracy} m`);
			if (point.source) popup_lines.push(`${__("Source")}: ${point.source}`);

			let marker;
			if (is_start) {
				marker = L.marker([point.lat, point.long], {
					icon: this.make_pin_icon("#2ecc71", "S"),
					zIndexOffset: 1000,
				});
			} else if (is_end) {
				marker = L.marker([point.lat, point.long], {
					icon: this.make_pin_icon("#e74c3c", "E"),
					zIndexOffset: 1000,
				});
			} else {
				const color = this.get_source_color(point.source);
				marker = L.circleMarker([point.lat, point.long], {
					radius: 5,
					color: "#fff",
					weight: 1.5,
					fillColor: color,
					fillOpacity: 1,
				});
			}

			marker.bindPopup(popup_lines.join("<br>"));
			// Show the info popup on hover instead of requiring a click.
			marker.on("mouseover", (e) => e.target.openPopup());
			marker.on("mouseout", (e) => e.target.closePopup());

			this.marker_layer.addLayer(marker);
		});

		// Draw the polyline first so it sits underneath, then add the marker
		// layer on top — otherwise the line paints over every intermediate
		// marker and only the Start/End pins remain visible.
		// Two-pass "casing" render (a wider dark outline underneath a
		// narrower bright line) keeps the route clearly visible over any
		// tile colors, unlike a single flat gray line.
		this.polyline_outline = L.polyline(latlngs, {
			color: "#0b3d91",
			weight: 7,
			opacity: 0.35,
			lineJoin: "round",
			lineCap: "round",
		}).addTo(this.map);
		this.polyline = L.polyline(latlngs, {
			color: "#1a73e8",
			weight: 4,
			opacity: 0.95,
			lineJoin: "round",
			lineCap: "round",
		}).addTo(this.map);
		this.marker_layer.addTo(this.map);

		this.map.invalidateSize();
		this.map.fitBounds(this.polyline.getBounds(), { padding: [30, 30] });

		const total_distance_km = this.calculate_total_distance_km(points);

		$summary.html(
			__("{0} points &nbsp;|&nbsp; {1} km travelled &nbsp;|&nbsp; {2} to {3}", [
				points.length,
				total_distance_km.toFixed(2),
				frappe.datetime.str_to_user(points[0].device_date_time),
				frappe.datetime.str_to_user(points[points.length - 1].device_date_time),
			])
		);
	}
};
