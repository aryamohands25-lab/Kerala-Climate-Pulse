"use strict";

const API_BASE = "https://kerala-climate-pulse.onrender.com";

let districts = [];
let selectedDistrict = "Thiruvananthapuram";
let temperatureChart = null;
let rainfallChart = null;

const $ = (id) => document.getElementById(id);

function setText(id, value) {
    const element = $(id);
    if (element) element.textContent = value;
}

function formatNumber(value, digits = 1) {
    const number = Number(value);
    return Number.isFinite(number) ? number.toFixed(digits) : "—";
}

function formatDate(value) {
    if (!value) return "—";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleString("en-IN", {
        day: "2-digit",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit"
    });
}

async function api(path) {
    const response = await fetch(`${API_BASE}${path}`);

    if (!response.ok) {
        throw new Error(`API request failed (${response.status}): ${path}`);
    }

    return response.json();
}

function showError(id, message) {
    const element = $(id);
    if (element) {
        element.textContent = message;
        element.classList.add("error-message");
    }
}

function clearError(id) {
    const element = $(id);
    if (element) element.classList.remove("error-message");
}

function setApiStatus(online, message) {
    const element = $("api-status");
    if (!element) return;

    element.textContent = message;
    element.classList.toggle("online", online);
    element.classList.toggle("offline", !online);
}

async function loadDistricts() {
    const data = await api("/districts");

    // The actual API response is an array.
    districts = Array.isArray(data) ? data : data.value || [];

    const select = $("district-select");
    const list = $("district-list");

    if (!districts.length) {
        throw new Error("The districts endpoint returned no districts.");
    }

    if (select) {
        select.replaceChildren();

        districts.forEach((district) => {
            const option = document.createElement("option");
            option.value = district.district_name;
            option.textContent = district.district_name;
            select.appendChild(option);
        });

        select.value = districts.some(
            d => d.district_name === selectedDistrict
        ) ? selectedDistrict : districts[0].district_name;

        selectedDistrict = select.value;

        select.addEventListener("change", () => {
            selectedDistrict = select.value;
            loadSelectedDistrict();
        });
    }

    if (list) {
        list.replaceChildren();

        districts.forEach((district) => {
            const item = document.createElement("button");
            item.type = "button";
            item.className = "district-item";
            item.textContent = district.district_name;
            item.dataset.district = district.district_name;

            item.addEventListener("click", () => {
                selectedDistrict = district.district_name;
                if (select) select.value = selectedDistrict;
                loadSelectedDistrict();
            });

            list.appendChild(item);
        });
    }

    updateDistrictSelection();
}

function updateDistrictSelection() {
    document.querySelectorAll(".district-item").forEach((item) => {
        item.classList.toggle(
            "active",
            item.dataset.district === selectedDistrict
        );
    });
}

function updateReading(reading) {
    setText("selected-district", reading.district_name);
    setText("district-region", reading.region || "—");

    setText("district-temp", `${formatNumber(reading.temperature_c)} °C`);
    setText("district-humidity", `${formatNumber(reading.humidity_pct, 0)}%`);
    setText("district-rain", `${formatNumber(reading.rainfall_mm)} mm`);
    setText("district-aqi", formatNumber(reading.aqi, 0));
    setText("district-observed", `Observed: ${formatDate(reading.observed_at)}`);



    updateDistrictSelection();
}

async function loadStateOverview() {
    const results = await Promise.allSettled(
        districts.map(district =>
            api(`/district/${encodeURIComponent(district.district_name)}/latest`)
        )
    );

    const readings = results
        .filter(result => result.status === "fulfilled")
        .map(result => result.value);

    function average(field, digits = 1) {
        const values = readings
            .map(reading => Number(reading[field]))
            .filter(Number.isFinite);

        if (!values.length) return "—";

        const total = values.reduce((sum, value) => sum + value, 0);
        return (total / values.length).toFixed(digits);
    }

    setText("avg-temp", `${average("temperature_c")} °C`);
    setText("avg-humidity", `${average("humidity_pct", 0)}%`);
    setText("avg-rainfall", `${average("rainfall_mm")} mm`);
    setText("avg-aqi", average("aqi", 0));

    console.log(
        `State overview calculated using ${readings.length} of ${districts.length} districts.`
    );
}
async function loadSelectedDistrict() {
    clearError("selected-district");

    try {
        const encodedName = encodeURIComponent(selectedDistrict);
        const reading = await api(`/district/${encodedName}/latest`);

        updateReading(reading);
        await loadHistory();
    } catch (error) {
        console.error("District loading error:", error);
        showError("selected-district", "Unable to load district data.");
    }
}

function createChart(canvasId, oldChart, labels, values, label, color, unit) {
    const canvas = $(canvasId);

    if (!canvas || typeof Chart === "undefined") return oldChart;

    if (oldChart) oldChart.destroy();

    return new Chart(canvas, {
        type: "line",
        data: {
            labels,
            datasets: [{
                label,
                data: values,
                borderColor: color,
                backgroundColor: `${color}22`,
                borderWidth: 2,
                fill: true,
                tension: 0.35,
                pointRadius: 3,
                pointHoverRadius: 5
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                intersect: false,
                mode: "index"
            },
            plugins: {
                legend: {
                    display: true,
                    labels: {
                        color: "#cbd5e1"
                    }
                },
                tooltip: {
                    callbacks: {
                        label: (context) =>
                            `${context.dataset.label}: ${context.parsed.y} ${unit}`
                    }
                }
            },
            scales: {
                x: {
                    ticks: { color: "#94a3b8" },
                    grid: { color: "#ffffff10" }
                },
                y: {
                    beginAtZero: true,
                    ticks: { color: "#94a3b8" },
                    grid: { color: "#ffffff10" }
                }
            }
        }
    });
}

async function loadHistory() {
    const daysSelect = $("history-days");
    const days = daysSelect ? daysSelect.value : "7";

    try {
        const encodedName = encodeURIComponent(selectedDistrict);
        const history = await api(
            `/district/${encodedName}/history?days=${days}`
        );

        const records = Array.isArray(history.records)
            ? history.records
            : [];

        if (!records.length) {
            console.warn("No history records returned.");
            return;
        }

        const labels = records.map(record => record.full_date);

        temperatureChart = createChart(
            "temperature-chart",
            temperatureChart,
            labels,
            records.map(record => record.temp_avg_c),
            "Average temperature",
            "#38bdf8",
            "°C"
        );

        rainfallChart = createChart(
            "rainfall-chart",
            rainfallChart,
            labels,
            records.map(record => record.rain_mm_total),
            "Daily rainfall",
            "#2dd4bf",
            "mm"
        );

        const partialDay = records.find(
            record => Number(record.hours_observed) < 24
        );

        const note = $("history-note");
        if (note) {
            note.textContent = partialDay
                ? `Note: ${partialDay.full_date} is an incomplete day (${partialDay.hours_observed}/24 hours observed).`
                : "";
        }
    } catch (error) {
        console.error("History loading error:", error);
    }
}

function renderAlerts(containerId, data, type) {
    const container = $(containerId);
    if (!container) return;

    container.replaceChildren();

    const alerts = Array.isArray(data)
        ? data
        : Array.isArray(data?.alerts)
            ? data.alerts
            : [];

    if (!alerts.length) {
        const message = document.createElement("p");
        message.className = "muted";
        message.textContent = "No active alerts.";
        container.appendChild(message);
        return;
    }

    alerts.forEach((alert) => {
        const card = document.createElement("div");
        card.className = "alert-item";

        const heading = document.createElement("strong");
        heading.textContent =
            alert.district_name ||
            alert.title ||
            (type === "air" ? "Air quality alert" : "Rainfall alert");

        const description = document.createElement("p");
        description.textContent =
            alert.message ||
            alert.description ||
            alert.alert_message ||
            "An active alert has been reported.";

        card.append(heading, description);
        container.appendChild(card);
    });
}

async function loadAlerts() {
    const results = await Promise.allSettled([
        api("/alerts/air-quality"),
        api("/alerts/heavy-rain")
    ]);

    renderAlerts(
        "air-alerts",
        results[0].status === "fulfilled" ? results[0].value : [],
        "air"
    );

    renderAlerts(
        "rain-alerts",
        results[1].status === "fulfilled" ? results[1].value : [],
        "rain"
    );
}

function renderRankings(containerId, data, type) {
    const container = $(containerId);
    if (!container) return;

    container.replaceChildren();

    const rows = Array.isArray(data) ? data : [];

    if (!rows.length) {
        const message = document.createElement("p");
        message.className = "muted";
        message.textContent = "Ranking data is currently unavailable.";
        container.appendChild(message);
        return;
    }

    rows.forEach((district, index) => {
        const item = document.createElement("div");
        item.className = "ranking-item";

        const rank = document.createElement("span");
        rank.className = "ranking-position";
        rank.textContent = `#${index + 1}`;

        const name = document.createElement("span");
        name.className = "ranking-name";
        name.textContent = district.district_name;

        const value = document.createElement("strong");
        value.className = "ranking-value";

        if (type === "aqi") {
            value.textContent = `${formatNumber(district.aqi_avg, 0)} AQI`;
        } else {
            value.textContent = `${formatNumber(district.rain_mm_total)} mm`;
        }

        item.append(rank, name, value);
        container.appendChild(item);
    });
}

async function loadRankings() {
    const results = await Promise.allSettled([
        api("/rankings/aqi"),
        api("/rankings/rainfall")
    ]);

    renderRankings(
        "aqi-rankings",
        results[0].status === "fulfilled" ? results[0].value : [],
        "aqi"
    );

    renderRankings(
        "rain-rankings",
        results[1].status === "fulfilled" ? results[1].value : [],
        "rain"
    );
}

function updateLastUpdated() {
    setText(
        "last-updated",
        `Dashboard refreshed: ${new Date().toLocaleString("en-IN")}`
    );
}

async function initializeDashboard() {
    setApiStatus(false, "Connecting to API...");

    try {
        await loadDistricts();
        await Promise.all([
            loadStateOverview(),
            loadSelectedDistrict()
        ]);

        await Promise.all([
            loadAlerts(),
            loadRankings()
        ]);

        setApiStatus(true, "API connected");
        updateLastUpdated();
    } catch (error) {
        console.error("Dashboard initialization error:", error);
        setApiStatus(false, "API connection failed");

        const districtList = $("district-list");
        if (districtList) {
            districtList.textContent =
                "Unable to load district data. Please refresh the page.";
        }
    }
}

const historySelect = $("history-days");
if (historySelect) {
    historySelect.addEventListener("change", loadHistory);
}

initializeDashboard();


