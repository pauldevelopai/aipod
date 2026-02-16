document.addEventListener("DOMContentLoaded", () => {
    const statusBadge = document.getElementById("status-badge");
    const stageLabel = document.getElementById("stage-label");
    const stageCounter = document.getElementById("stage-counter");
    const progressBar = document.getElementById("progress-bar");
    const errorBox = document.getElementById("error-box");
    const errorText = document.getElementById("error-text");
    const actionButtons = document.getElementById("action-buttons");
    const logEntries = document.getElementById("log-entries");
    const logStatus = document.getElementById("log-status");
    const logPanel = document.getElementById("log-panel");

    let lastLogCount = 0;
    let lastUpdatedAt = null;
    let staleCheckCount = 0;
    const STALE_THRESHOLD = 450; // 450 polls * 2s = 15 min without update = stale

    function renderLogEntries(entries) {
        if (!entries || entries.length === 0) return;
        if (entries.length === lastLogCount) return; // No new entries

        logPanel.classList.remove("hidden");
        logEntries.innerHTML = entries.map((entry) => {
            let colorClass = "text-gray-400";
            if (entry.msg.includes("FAILED")) colorClass = "text-red-400";
            else if (entry.msg.includes("complete") || entry.msg.includes("skipped")) colorClass = "text-green-400";
            else if (entry.msg.includes("...")) colorClass = "text-blue-300";
            return `<div class="${colorClass}"><span class="text-gray-600">${entry.ts}</span> ${entry.msg}</div>`;
        }).join("");

        lastLogCount = entries.length;
        // Auto-scroll to bottom
        logEntries.scrollTop = logEntries.scrollHeight;
    }

    function markStale() {
        statusBadge.className = "px-3 py-1 rounded-full text-sm font-medium bg-orange-900 text-orange-300";
        statusBadge.textContent = "Stale (Worker Crashed?)";
        progressBar.className = progressBar.className.replace(/bg-\w+-500/, "bg-orange-500");
        logStatus.textContent = "No updates for 15 min — worker may have crashed";
        logStatus.className = "text-xs text-orange-400";
        // Show retry button
        actionButtons.innerHTML = `
            <form action="/jobs/${JOB_ID}/retry" method="post" class="inline">
                <button type="submit" class="bg-orange-600 hover:bg-orange-700 text-white font-medium py-2 px-6 rounded-lg transition-colors">
                    Retry Job
                </button>
            </form>
            <a href="/" class="bg-gray-700 hover:bg-gray-600 text-white font-medium py-2 px-6 rounded-lg transition-colors">
                New Job
            </a>`;
    }

    if (CURRENT_STATUS === "completed" || CURRENT_STATUS === "failed") {
        // Still fetch once to show logs for completed/failed jobs
        fetch(`/jobs/${JOB_ID}/events`)
            .then(() => {
                // Use a one-shot SSE to get the final state
                const oneShot = new EventSource(`/jobs/${JOB_ID}/events`);
                oneShot.addEventListener("status", (event) => {
                    const data = JSON.parse(event.data);
                    renderLogEntries(data.stage_log || []);
                    oneShot.close();
                });
                oneShot.addEventListener("error", () => oneShot.close());
            });
        return;
    }

    const evtSource = new EventSource(`/jobs/${JOB_ID}/events`);

    evtSource.addEventListener("status", (event) => {
        const data = JSON.parse(event.data);

        // Render log entries
        renderLogEntries(data.stage_log || []);

        // Detect stale job (processing but no DB update)
        if (data.status === "processing") {
            if (data.updated_at === lastUpdatedAt) {
                staleCheckCount++;
                if (staleCheckCount >= STALE_THRESHOLD) {
                    markStale();
                    evtSource.close();
                    return;
                }
            } else {
                staleCheckCount = 0;
                lastUpdatedAt = data.updated_at;
            }
            logStatus.textContent = `Listening for updates...`;
        }

        // Update stage info
        stageLabel.textContent = data.stage_name || "Processing...";
        stageCounter.textContent = data.status === "completed" ? "6/6" : `${data.current_stage}/6`;

        // Update progress bar
        const pct = data.status === "completed" ? 100 : Math.round((data.current_stage / 6) * 100);
        progressBar.style.width = pct + "%";

        // Update stage items
        document.querySelectorAll(".stage-item").forEach((item) => {
            const stage = parseInt(item.dataset.stage);
            const dot = item.querySelector("div");
            const label = item.querySelector("span");

            const isComplete = data.status === "completed";

            if (isComplete || data.current_stage > stage) {
                dot.className = "w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold bg-green-600 text-white";
                dot.innerHTML = "&#10003;";
                label.className = "text-sm text-gray-400";
            } else if (data.current_stage === stage) {
                if (data.status === "awaiting_review") {
                    dot.className = "w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold bg-yellow-600 text-white";
                } else {
                    dot.className = "w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold bg-blue-600 text-white animate-pulse";
                }
                dot.textContent = stage;
                label.className = "text-sm text-white font-medium";
            } else {
                dot.className = "w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold bg-gray-700 text-gray-500";
                dot.textContent = stage;
                label.className = "text-sm text-gray-600";
            }
        });

        // Update status badge
        let badgeClass = "px-3 py-1 rounded-full text-sm font-medium ";
        const statusText = data.status.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

        if (data.status === "completed") {
            badgeClass += "bg-green-900 text-green-300";
            progressBar.className = progressBar.className.replace(/bg-\w+-500/, "bg-green-500");
            logStatus.textContent = "Complete";
            logStatus.className = "text-xs text-green-500";
        } else if (data.status === "failed") {
            badgeClass += "bg-red-900 text-red-300";
            progressBar.className = progressBar.className.replace(/bg-\w+-500/, "bg-red-500");
            logStatus.textContent = "Failed";
            logStatus.className = "text-xs text-red-400";
        } else if (data.status === "awaiting_review") {
            badgeClass += "bg-yellow-900 text-yellow-300";
            progressBar.className = progressBar.className.replace(/bg-\w+-500/, "bg-yellow-500");
        } else {
            badgeClass += "bg-blue-900 text-blue-300";
        }

        statusBadge.className = badgeClass;
        statusBadge.textContent = statusText;

        // Show detected languages
        if (data.detected_languages && data.detected_languages.length > 0) {
            const container = document.getElementById("detected-langs");
            const badges = document.getElementById("lang-badges");
            container.classList.remove("hidden");
            badges.innerHTML = data.detected_languages.map((lang) =>
                `<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-indigo-900 text-indigo-300">
                    ${lang.name}
                    <span class="text-indigo-500">${lang.percentage}%</span>
                </span>`
            ).join("");
        }

        // Show error
        if (data.error_message) {
            errorBox.classList.remove("hidden");
            if (errorText) errorText.textContent = data.error_message;
        }

        // Update action buttons
        if (data.status === "awaiting_review") {
            actionButtons.innerHTML = `
                <a href="/jobs/${JOB_ID}/edit" class="bg-yellow-600 hover:bg-yellow-700 text-white font-medium py-2 px-6 rounded-lg transition-colors">
                    Review & Edit Translation
                </a>
                <a href="/" class="bg-gray-700 hover:bg-gray-600 text-white font-medium py-2 px-6 rounded-lg transition-colors">
                    New Job
                </a>`;
        } else if (data.status === "completed") {
            actionButtons.innerHTML = `
                <a href="/jobs/${JOB_ID}/download" class="bg-green-600 hover:bg-green-700 text-white font-medium py-2 px-6 rounded-lg transition-colors">
                    Download Result
                </a>
                <a href="/" class="bg-gray-700 hover:bg-gray-600 text-white font-medium py-2 px-6 rounded-lg transition-colors">
                    New Job
                </a>`;
        } else if (data.status === "failed") {
            actionButtons.innerHTML = `
                <form action="/jobs/${JOB_ID}/retry" method="post" class="inline">
                    <button type="submit" class="bg-blue-600 hover:bg-blue-700 text-white font-medium py-2 px-6 rounded-lg transition-colors">
                        Retry
                    </button>
                </form>
                <a href="/" class="bg-gray-700 hover:bg-gray-600 text-white font-medium py-2 px-6 rounded-lg transition-colors">
                    New Job
                </a>`;
        }

        // Close SSE if terminal state
        if (data.status === "completed" || data.status === "failed" || data.status === "awaiting_review") {
            evtSource.close();
        }
    });

    evtSource.addEventListener("error", () => {
        evtSource.close();
    });
});
