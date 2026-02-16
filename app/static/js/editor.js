document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("editor-form");
    const hiddenInput = document.getElementById("edited-segments-input");

    // Collect all segments and serialize to JSON before submit
    form.addEventListener("submit", (e) => {
        const segments = [];
        document.querySelectorAll(".segment-row").forEach((row) => {
            const textarea = row.querySelector(".segment-text");
            segments.push({
                speaker: textarea.dataset.speaker,
                start_time: parseFloat(textarea.dataset.start) || 0,
                end_time: parseFloat(textarea.dataset.end) || 0,
                translated_text: textarea.value,
            });
        });
        hiddenInput.value = JSON.stringify(segments);
    });

    // Tag insertion buttons
    document.querySelectorAll(".tag-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
            const row = btn.closest(".segment-row");
            const textarea = row.querySelector(".segment-text");

            const tags = ["[Thoughtful]", "[Laughing]", "[Excited]", "[Serious]", "[Pause]"];
            const tag = prompt("Select emotion tag:\n" + tags.map((t, i) => `${i + 1}. ${t}`).join("\n") + "\n\nOr type your own [Tag]:");

            if (tag) {
                let insertTag = tag;
                const num = parseInt(tag);
                if (num >= 1 && num <= tags.length) {
                    insertTag = tags[num - 1];
                } else if (!tag.startsWith("[")) {
                    insertTag = `[${tag}]`;
                }

                const pos = textarea.selectionStart;
                const before = textarea.value.substring(0, pos);
                const after = textarea.value.substring(pos);
                textarea.value = before + " " + insertTag + " " + after;
                textarea.focus();
            }
        });
    });

    // Sync audio playback with segments on click
    const audioPlayer = document.getElementById("audio-player");
    if (audioPlayer) {
        document.querySelectorAll(".segment-row").forEach((row) => {
            row.addEventListener("click", (e) => {
                if (e.target.tagName === "TEXTAREA") return;
                const textarea = row.querySelector(".segment-text");
                const startTime = parseFloat(textarea.dataset.start) || 0;
                audioPlayer.currentTime = startTime;
                audioPlayer.play();
            });
        });
    }
});
