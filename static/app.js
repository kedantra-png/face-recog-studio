/**
 * Silent-Face-Anti-Spoofing Web Client Application
 */

document.addEventListener("DOMContentLoaded", () => {
    // UI Elements
    const tabBtns = document.querySelectorAll(".tab-btn");
    const tabContents = document.querySelectorAll(".tab-content");

    const dropZone = document.getElementById("drop-zone");
    const fileInput = document.getElementById("file-input");

    const videoElem = document.getElementById("webcam-video");
    const canvasElem = document.getElementById("webcam-canvas");
    const btnToggleWebcam = document.getElementById("btn-toggle-webcam");
    const btnSnapWebcam = document.getElementById("btn-snap-webcam");
    const chkAutoScan = document.getElementById("chk-auto-scan");
    const webcamOverlay = document.getElementById("webcam-overlay");

    const samplesGrid = document.getElementById("samples-grid");

    const mainPreviewImg = document.getElementById("main-preview-img");
    const loadingSpinner = document.getElementById("loading-spinner");
    const imgNameTag = document.getElementById("img-name-tag");

    // Verdict & Metrics Elements
    const verdictBanner = document.getElementById("verdict-banner");
    const verdictIcon = document.getElementById("verdict-icon");
    const verdictTitle = document.getElementById("verdict-title");
    const verdictSub = document.getElementById("verdict-sub");
    const verdictScore = document.getElementById("verdict-score");

    const realPercentage = document.getElementById("real-percentage");
    const realBar = document.getElementById("real-bar");
    const fakePercentage = document.getElementById("fake-percentage");
    const fakeBar = document.getElementById("fake-bar");

    const modelsGrid = document.getElementById("models-grid");
    const patchScale27 = document.getElementById("patch-scale-27");
    const patchScale40 = document.getElementById("patch-scale-40");

    const valLatency = document.getElementById("val-latency");
    const valBbox = document.getElementById("val-bbox");

    // State Variables
    let webcamStream = null;
    let autoScanTimer = null;
    let isProcessing = false;

    // --- Tab Switching Logic ---
    tabBtns.forEach(btn => {
        btn.addEventListener("click", () => {
            tabBtns.forEach(b => b.classList.remove("active"));
            tabContents.forEach(c => c.classList.remove("active"));

            btn.classList.add("active");
            const targetTab = btn.getAttribute("data-tab");
            document.getElementById(targetTab).classList.add("active");

            // Pause webcam scan if switching away from webcam tab
            if (targetTab !== "webcam-tab" && autoScanTimer) {
                stopAutoScan();
            }
        });
    });

    // --- File Upload Logic ---
    dropZone.addEventListener("click", () => fileInput.click());

    dropZone.addEventListener("dragover", (e) => {
        e.preventDefault();
        dropZone.classList.add("dragover");
    });

    dropZone.addEventListener("dragleave", () => {
        dropZone.classList.remove("dragover");
    });

    dropZone.addEventListener("drop", (e) => {
        e.preventDefault();
        dropZone.classList.remove("dragover");
        if (e.dataTransfer.files && e.dataTransfer.files[0]) {
            handleFileUpload(e.dataTransfer.files[0]);
        }
    });

    fileInput.addEventListener("change", (e) => {
        if (e.target.files && e.target.files[0]) {
            handleFileUpload(e.target.files[0]);
        }
    });

    function handleFileUpload(file) {
        if (!file.type.startsWith("image/")) {
            alert("Please upload a valid image file.");
            return;
        }

        const formData = new FormData();
        formData.append("file", file);
        imgNameTag.textContent = file.name;

        // Preview local file before response
        const reader = new FileReader();
        reader.onload = (e) => {
            mainPreviewImg.src = e.target.result;
        };
        reader.readAsDataURL(file);

        sendPredictionRequest("/api/predict", formData);
    }

    // --- Webcam Stream Logic ---
    btnToggleWebcam.addEventListener("click", toggleWebcam);
    btnSnapWebcam.addEventListener("click", captureWebcamFrame);

    chkAutoScan.addEventListener("change", () => {
        if (chkAutoScan.checked) {
            startAutoScan();
        } else {
            stopAutoScan();
        }
    });

    async function toggleWebcam() {
        if (webcamStream) {
            stopWebcam();
        } else {
            try {
                webcamStream = await navigator.mediaDevices.getUserMedia({
                    video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: "user" },
                    audio: false
                });
                videoElem.srcObject = webcamStream;
                btnToggleWebcam.innerHTML = "<span>🛑</span> Stop Camera";
                btnSnapWebcam.disabled = false;
                webcamOverlay.style.display = "flex";

                if (chkAutoScan.checked) {
                    startAutoScan();
                }
            } catch (err) {
                alert("Could not access webcam: " + err.message);
            }
        }
    }

    function stopWebcam() {
        if (webcamStream) {
            webcamStream.getTracks().forEach(track => track.stop());
            webcamStream = null;
        }
        videoElem.srcObject = null;
        btnToggleWebcam.innerHTML = "<span>🎥</span> Start Camera";
        btnSnapWebcam.disabled = true;
        webcamOverlay.style.display = "none";
        stopAutoScan();
    }

    function startAutoScan() {
        if (!webcamStream) return;
        if (autoScanTimer) clearInterval(autoScanTimer);
        autoScanTimer = setInterval(() => {
            if (!isProcessing) {
                captureWebcamFrame();
            }
        }, 1200);
    }

    function stopAutoScan() {
        if (autoScanTimer) {
            clearInterval(autoScanTimer);
            autoScanTimer = null;
        }
        chkAutoScan.checked = false;
    }

    function captureWebcamFrame() {
        if (!webcamStream || !videoElem.videoWidth) return;

        canvasElem.width = videoElem.videoWidth;
        canvasElem.height = videoElem.videoHeight;
        const ctx = canvasElem.getContext("2d");
        ctx.drawImage(videoElem, 0, 0, canvasElem.width, canvasElem.height);

        const b64Image = canvasElem.toDataURL("image/jpeg", 0.9);
        imgNameTag.textContent = `webcam_${Date.now()}.jpg`;

        sendPredictionRequest("/api/predict", JSON.stringify({ image_b64: b64Image }), "json");
    }

    // --- Sample Gallery Logic ---
    async function loadSamples() {
        try {
            const res = await fetch("/api/samples");
            const data = await res.json();
            if (data.success && data.samples.length > 0) {
                samplesGrid.innerHTML = "";
                data.samples.forEach(sample => {
                    const card = document.createElement("div");
                    card.className = "sample-card";
                    card.innerHTML = `
                        <img src="${sample.url}" alt="${sample.filename}">
                        <div class="sample-info">
                            <span>${sample.filename}</span>
                            <span class="badge-hint ${sample.hint}">${sample.hint}</span>
                        </div>
                    `;
                    card.addEventListener("click", () => {
                        mainPreviewImg.src = sample.url;
                        imgNameTag.textContent = sample.filename;
                        fetchSamplePrediction(sample.url, sample.filename);
                    });
                    samplesGrid.appendChild(card);
                });
            } else {
                samplesGrid.innerHTML = "<div class='sample-skeleton'>No sample images available</div>";
            }
        } catch (err) {
            samplesGrid.innerHTML = "<div class='sample-skeleton'>Error loading samples</div>";
        }
    }

    async function fetchSamplePrediction(url, filename) {
        try {
            showLoading(true);
            const response = await fetch(url);
            const blob = await response.blob();
            const formData = new FormData();
            formData.append("file", blob, filename);
            sendPredictionRequest("/api/predict", formData);
        } catch (err) {
            showLoading(false);
            alert("Error analyzing sample: " + err.message);
        }
    }

    // --- API Request & Result Rendering ---
    async function sendPredictionRequest(endpoint, body, type = "formData") {
        if (isProcessing) return;
        isProcessing = true;
        showLoading(true);

        try {
            const options = {
                method: "POST",
                body: body
            };
            if (type === "json") {
                options.headers = { "Content-Type": "application/json" };
            }

            const response = await fetch(endpoint, options);
            const data = await response.json();

            showLoading(false);
            isProcessing = false;

            if (data.success) {
                renderResults(data);
            } else {
                renderError(data.error);
            }
        } catch (err) {
            showLoading(false);
            isProcessing = false;
            renderError("Network error: " + err.message);
        }
    }

    function renderResults(res) {
        // Main Preview Annotated Image
        if (res.annotated_image_b64) {
            mainPreviewImg.src = res.annotated_image_b64;
        }

        // Verdict Banner
        verdictBanner.className = "verdict-banner " + (res.is_real ? "status-real" : "status-fake");
        verdictIcon.textContent = res.is_real ? "✅" : "⚠️";
        verdictTitle.textContent = res.label_str;
        verdictSub.textContent = res.is_real ? "Authentic Live Human Face Verified" : "Presentation Attack / Photo / Screen Detected";
        verdictScore.textContent = res.score.toFixed(1) + "%";

        // Probability Bars
        realPercentage.textContent = res.real_probability.toFixed(1) + "%";
        realBar.style.width = res.real_probability + "%";

        fakePercentage.textContent = res.fake_probability.toFixed(1) + "%";
        fakeBar.style.width = res.fake_probability + "%";

        // Model Breakdown Grid
        if (res.per_model_scores) {
            modelsGrid.innerHTML = "";
            for (const [mName, mData] of Object.entries(res.per_model_scores)) {
                const item = document.createElement("div");
                item.className = "model-item";
                const isModelReal = mData.real_score > 50.0;
                item.innerHTML = `
                    <span class="model-name">${mData.model_type} (Scale ${mData.scale || 'Full'})</span>
                    <span class="model-score" style="color: ${isModelReal ? 'var(--accent-real)' : 'var(--accent-fake)'}">
                        ${isModelReal ? 'REAL' : 'SPOOF'} (${mData.real_score.toFixed(1)}%)
                    </span>
                `;
                modelsGrid.appendChild(item);
            }
        }

        // Cropped Face Patches
        if (res.cropped_patches) {
            if (res.cropped_patches["scale_2.7"]) {
                patchScale27.src = res.cropped_patches["scale_2.7"];
                patchScale27.style.display = "block";
                patchScale27.nextElementSibling.style.display = "none";
            }
            if (res.cropped_patches["scale_4.0"]) {
                patchScale40.src = res.cropped_patches["scale_4.0"];
                patchScale40.style.display = "block";
                patchScale40.nextElementSibling.style.display = "none";
            }
        }

        // Telemetry
        valLatency.textContent = res.total_latency_ms + " ms";
        if (res.bbox) {
            valBbox.textContent = `${res.bbox.width}x${res.bbox.height} px`;
        }
    }

    function renderError(errMsg) {
        verdictBanner.className = "verdict-banner status-neutral";
        verdictIcon.textContent = "❌";
        verdictTitle.textContent = "Detection Warning";
        verdictSub.textContent = errMsg || "Unknown error";
        verdictScore.textContent = "--%";
    }

    function showLoading(show) {
        loadingSpinner.style.display = show ? "flex" : "none";
    }

    // Initialize Preset Samples on load
    loadSamples();
});
