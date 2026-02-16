document.addEventListener("DOMContentLoaded", () => {
    const dropZone = document.getElementById("drop-zone");
    const fileInput = document.getElementById("file-input");
    const dropText = document.getElementById("drop-text");
    const fileInfo = document.getElementById("file-info");
    const fileName = document.getElementById("file-name");
    const fileSize = document.getElementById("file-size");
    const submitBtn = document.getElementById("submit-btn");
    const targetLang = document.getElementById("target_language");

    function formatSize(bytes) {
        if (bytes < 1024) return bytes + " B";
        if (bytes < 1048576) return (bytes / 1024).toFixed(1) + " KB";
        return (bytes / 1048576).toFixed(1) + " MB";
    }

    function checkReady() {
        const hasFile = fileInput.files && fileInput.files.length > 0;
        const hasTarget = targetLang.value !== "";
        submitBtn.disabled = !(hasFile && hasTarget);
    }

    function handleFile(file) {
        if (!file.name.toLowerCase().endsWith(".mp3")) {
            alert("Please select an MP3 file.");
            return;
        }
        const dt = new DataTransfer();
        dt.items.add(file);
        fileInput.files = dt.files;

        fileName.textContent = file.name;
        fileSize.textContent = formatSize(file.size);
        dropText.classList.add("hidden");
        fileInfo.classList.remove("hidden");
        checkReady();
    }

    // Click to browse — stop propagation from input to avoid loop
    dropZone.addEventListener("click", (e) => {
        if (e.target !== fileInput) {
            fileInput.click();
        }
    });

    fileInput.addEventListener("click", (e) => e.stopPropagation());

    fileInput.addEventListener("change", () => {
        if (fileInput.files.length > 0) {
            handleFile(fileInput.files[0]);
        }
    });

    // Drag and drop
    dropZone.addEventListener("dragover", (e) => {
        e.preventDefault();
        dropZone.classList.add("drop-active");
    });

    dropZone.addEventListener("dragleave", () => {
        dropZone.classList.remove("drop-active");
    });

    dropZone.addEventListener("drop", (e) => {
        e.preventDefault();
        dropZone.classList.remove("drop-active");
        if (e.dataTransfer.files.length > 0) {
            handleFile(e.dataTransfer.files[0]);
        }
    });

    // Language selection
    targetLang.addEventListener("change", checkReady);
});
