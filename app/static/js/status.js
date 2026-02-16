document.addEventListener("DOMContentLoaded", () => {
    if (CURRENT_STATUS === "completed" || CURRENT_STATUS === "failed") {
        return; // No need to poll
    }

    const statusBadge = document.getElementById("status-badge");
    const stageLabel = document.getElementById("stage-label");
    const stageCounter = document.getElementById("stage-counter");
    const progressBar = document.getElementById("progress-bar");
    const errorBox = document.getElementById("error-box");
    const errorText = document.getElementById("error-text");
    const actionButtons = document.getElementById("action-buttons");

    const evtSource = new EventSource(`/jobs/${JOB_ID}/events`);

    evtSource.addEventListener("status", (event) => {
        const data = JSON.parse(event.data);

        // Update stage info
        stageLabel.textContent = data.stage_name || "Processing...";
        stageCounter.textContent = `${data.current_stage}/6`;

        // Update progress bar
        const pct = Math.round((data.current_stage / 6) * 100);
        progressBar.style.width = pct + "%";

        // Update stage items
        document.querySelectorAll(".stage-item").forEach((item) => {
            const stage = parseInt(item.dataset.stage);
            const dot = item.querySelector("div");
            const label = item.querySelector("span");

            if (data.current_stage > stage) {
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
        } else if (data.status === "failed") {
            badgeClass += "bg-red-900 text-red-300";
            progressBar.className = progressBar.className.replace(/bg-\w+-500/, "bg-red-500");
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
