/**
 * Dashboard Chart.js Integration for AcxiomCRM (Phase 9).
 *
 * Consumes server-authorized, pre-aggregated JSON data safely embedded in the page.
 * Strictly READ-ONLY: Never initiates state-mutating requests or unauthorized raw queries.
 */

document.addEventListener("DOMContentLoaded", function () {
    // 1. Safely extract embedded JSON payload
    var dataElement = document.getElementById("dashboard-chart-data");
    if (!dataElement) {
        return;
    }

    var chartData = {};
    try {
        chartData = JSON.parse(dataElement.textContent || "{}");
    } catch (e) {
        console.error("Failed to parse dashboard chart data JSON:", e);
        return;
    }

    // Verify Chart.js availability
    if (typeof Chart === "undefined") {
        console.warn("Chart.js library is not available. Charts will not render.");
        return;
    }

    // Modern professional color palette
    var statusColors = {
        "New": "#3b82f6",         // Blue
        "Contacted": "#06b6d4",   // Cyan
        "Qualified": "#f59e0b",   // Amber
        "Converted": "#10b981",   // Emerald
        "Lost": "#ef4444"         // Red
    };

    var stageColors = {
        "Qualification": "#6366f1", // Indigo
        "Proposal": "#8b5cf6",      // Purple
        "Negotiation": "#ec4899",   // Pink
        "Won": "#10b981",           // Emerald
        "Lost": "#ef4444"           // Red
    };

    // -------------------------------------------------------------------------
    // 2. Chart 1: Lead Status Chart (Doughnut)
    // -------------------------------------------------------------------------
    var leadCanvas = document.getElementById("leadStatusChart");
    var leadEmptyMsg = document.getElementById("leadStatusEmptyMsg");

    if (leadCanvas && chartData.lead_status) {
        if (chartData.lead_status.has_data) {
            var leadLabels = chartData.lead_status.labels || [];
            var leadValues = chartData.lead_status.values || [];
            var bgColors = leadLabels.map(function (lbl) {
                return statusColors[lbl] || "#94a3b8";
            });

            new Chart(leadCanvas, {
                type: "doughnut",
                data: {
                    labels: leadLabels,
                    datasets: [{
                        data: leadValues,
                        backgroundColor: bgColors,
                        borderWidth: 2,
                        borderColor: "#ffffff"
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            position: "bottom",
                            labels: {
                                boxWidth: 14,
                                padding: 12
                            }
                        },
                        tooltip: {
                            callbacks: {
                                label: function (context) {
                                    var val = context.parsed || 0;
                                    var total = chartData.lead_status.total || 1;
                                    var pct = Math.round((val / total) * 100);
                                    return " " + context.label + ": " + val + " (" + pct + "%)";
                                }
                            }
                        }
                    }
                }
            });
        } else {
            if (leadEmptyMsg) {
                leadEmptyMsg.classList.remove("d-none");
            }
            if (leadCanvas.parentElement) {
                leadCanvas.parentElement.classList.add("d-none");
            }
        }
    }

    // -------------------------------------------------------------------------
    // 3. Chart 2: Opportunity Pipeline by Stage (Bar)
    // -------------------------------------------------------------------------
    var oppCanvas = document.getElementById("opportunityPipelineChart");
    var oppEmptyMsg = document.getElementById("oppPipelineEmptyMsg");

    if (oppCanvas && chartData.opportunity_pipeline) {
        if (chartData.opportunity_pipeline.has_data) {
            var oppLabels = chartData.opportunity_pipeline.labels || [];
            var oppValues = chartData.opportunity_pipeline.values || [];
            var oppBgColors = oppLabels.map(function (lbl) {
                return stageColors[lbl] || "#64748b";
            });

            new Chart(oppCanvas, {
                type: "bar",
                data: {
                    labels: oppLabels,
                    datasets: [{
                        label: "Number of Deals",
                        data: oppValues,
                        backgroundColor: oppBgColors,
                        borderRadius: 6
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            display: false
                        },
                        tooltip: {
                            callbacks: {
                                label: function (context) {
                                    return " Deals: " + context.parsed.y;
                                }
                            }
                        }
                    },
                    scales: {
                        y: {
                            beginAtZero: true,
                            ticks: {
                                precision: 0,
                                stepSize: 1
                            },
                            grid: {
                                color: "#f1f5f9"
                            }
                        },
                        x: {
                            grid: {
                                display: false
                            }
                        }
                    }
                }
            });
        } else {
            if (oppEmptyMsg) {
                oppEmptyMsg.classList.remove("d-none");
            }
            if (oppCanvas.parentElement) {
                oppCanvas.parentElement.classList.add("d-none");
            }
        }
    }

    // -------------------------------------------------------------------------
    // 4. Chart 3: Monthly Sales (12-Month Trend Line/Bar)
    // -------------------------------------------------------------------------
    var salesCanvas = document.getElementById("monthlySalesChart");
    var salesEmptyMsg = document.getElementById("monthlySalesEmptyMsg");

    if (salesCanvas && chartData.monthly_sales) {
        if (chartData.monthly_sales.has_data) {
            var salesLabels = chartData.monthly_sales.labels || [];
            var salesValues = chartData.monthly_sales.values || [];

            new Chart(salesCanvas, {
                type: "bar",
                data: {
                    labels: salesLabels,
                    datasets: [{
                        label: "Won Sales (INR)",
                        data: salesValues,
                        backgroundColor: "rgba(37, 99, 235, 0.75)",
                        hoverBackgroundColor: "rgba(29, 78, 216, 0.9)",
                        borderColor: "#2563eb",
                        borderWidth: 1,
                        borderRadius: 6
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            display: false
                        },
                        tooltip: {
                            callbacks: {
                                label: function (context) {
                                    var val = context.parsed.y || 0;
                                    return " Sales: \u20B9" + val.toLocaleString("en-IN", {
                                        minimumFractionDigits: 2,
                                        maximumFractionDigits: 2
                                    });
                                }
                            }
                        }
                    },
                    scales: {
                        y: {
                            beginAtZero: true,
                            ticks: {
                                callback: function (value) {
                                    if (value >= 100000) {
                                        return "\u20B9" + (value / 100000).toFixed(1) + "L";
                                    }
                                    return "\u20B9" + value.toLocaleString("en-IN");
                                }
                            },
                            grid: {
                                color: "#f1f5f9"
                            }
                        },
                        x: {
                            grid: {
                                display: false
                            }
                        }
                    }
                }
            });
        } else {
            if (salesEmptyMsg) {
                salesEmptyMsg.classList.remove("d-none");
            }
            if (salesCanvas.parentElement) {
                salesCanvas.parentElement.classList.add("d-none");
            }
        }
    }

    // -------------------------------------------------------------------------
    // 5. Client-Side Date Range Validation
    // -------------------------------------------------------------------------
    var customForm = document.querySelector("form[action*='/dashboard']");
    if (customForm) {
        customForm.addEventListener("submit", function (e) {
            var startInput = document.getElementById("filter-start-date");
            var endInput = document.getElementById("filter-end-date");
            if (startInput && endInput && startInput.value && endInput.value) {
                if (startInput.value > endInput.value) {
                    e.preventDefault();
                    alert("Start date cannot be after end date.");
                }
            }
        });
    }
});
