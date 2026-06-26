/**
 * Lemma Frontend Engine (Vanilla JS)
 */

document.addEventListener("DOMContentLoaded", () => {
    // API URL configuration
    let API_BASE_URL = 'https://r4hul-78-lemma-backend.hf.space'; // 'http://localhost:8000'; 
    let API_UPLOAD_URL = `${API_BASE_URL}/api/v1/documents/upload`;
    let API_ANALYZE_URL = `${API_BASE_URL}/api/v1/analyze`;
    let API_STATUS_URL = `${API_BASE_URL}/api/v1/status`;
    let API_REWRITE_URL = `${API_BASE_URL}/api/v1/rewrite`;
    let API_HEALTH_URL = `${API_BASE_URL}/api/v1/health`;

    function updateApiUrls(base) {
        API_BASE_URL = base;
        API_UPLOAD_URL = `${API_BASE_URL}/api/v1/documents/upload`;
        API_ANALYZE_URL = `${API_BASE_URL}/api/v1/analyze`;
        API_STATUS_URL = `${API_BASE_URL}/api/v1/status`;
        API_REWRITE_URL = `${API_BASE_URL}/api/v1/rewrite`;
        API_HEALTH_URL = `${API_BASE_URL}/api/v1/health`;
    }

    // DOM Elements
    const serverStatusDot = document.getElementById("server-status-dot");
    const serverStatusText = document.getElementById("server-status-text");
    const dropZone = document.getElementById("drop-zone");
    const fileInput = document.getElementById("file-input");
    const documentViewer = document.getElementById("document-viewer");
    const documentRender = document.getElementById("document-content-render");
    const viewerFilename = document.getElementById("viewer-filename");
    const viewerDocType = document.getElementById("viewer-doc-type");
    const btnReupload = document.getElementById("btn-reupload");
    const btnRunAnalysis = document.getElementById("btn-run-analysis");
    const btnDownloadPdf = document.getElementById("btn-download-pdf");
    const toastContainer = document.getElementById("toast-container");

    // Metadata Elements
    const metaChars = document.getElementById("meta-chars");
    const metaSentences = document.getElementById("meta-sentences");
    const metaFilename = document.getElementById("meta-filename");
    const metaStatus = document.getElementById("meta-status");

    // Inspector Elements
    const inspectorPlaceholder = document.getElementById("inspector-placeholder");
    const inspectorData = document.getElementById("inspector-data");
    const inspectStart = document.getElementById("inspect-start");
    const inspectEnd = document.getElementById("inspect-end");
    const inspectText = document.getElementById("inspect-text");
    const btnQuickParaphrase = document.getElementById("btn-quick-paraphrase");

    // Reports Workspace Elements
    const reportsWorkspace = document.getElementById("reports-workspace");
    const reportsTable = document.getElementById("reports-table");
    const reportsTableBody = document.getElementById("reports-table-body");
    const reportsEmptyState = document.getElementById("reports-empty-state");
    const btnClearHistory = document.getElementById("btn-clear-history");

    // App State
    let activeFile = null;
    let uploadResponseData = null;
    let currentJobId = null;

    // Initialize Page
    async function initApiConfig() {
        try {
            const resolvedUrl = await APIConfigManager.getApiBaseUrl();
            updateApiUrls(resolvedUrl);
            console.log("Resolved API URL:", resolvedUrl);
        } catch (err) {
            console.warn("Failed resolving API from config manager, fallback to default URL:", err);
        } finally {
            checkServerHealth();
            setInterval(checkServerHealth, 10000); // Check health every 10 seconds
        }
    }
    
    initApiConfig();

    /* -------------------------------------------------------------
     * Server Health Checking
     * ------------------------------------------------------------- */
    async function checkServerHealth() {
        try {
            const response = await fetch(API_HEALTH_URL, { signal: AbortSignal.timeout(3000) });
            if (response.ok) {
                serverStatusDot.className = "status-indicator online";
                serverStatusText.textContent = "Server: Online";
            } else {
                throw new Error("Server status abnormal");
            }
        } catch (error) {
            serverStatusDot.className = "status-indicator offline";
            serverStatusText.textContent = "Server: Offline";
        }
    }

    /* -------------------------------------------------------------
     * Toast Notifications Helper
     * ------------------------------------------------------------- */
    function showToast(message, type = "info") {
        const toast = document.createElement("div");
        toast.className = `toast toast-${type}`;
        
        let icon = '<i class="fa-solid fa-circle-info"></i>';
        if (type === "error") icon = '<i class="fa-solid fa-circle-exclamation"></i>';
        if (type === "success") icon = '<i class="fa-solid fa-circle-check"></i>';

        toast.innerHTML = `
            ${icon}
            <div class="toast-message">${message}</div>
        `;
        
        toastContainer.appendChild(toast);

        // Slide out and remove
        setTimeout(() => {
            toast.style.animation = "slide-in 0.3s reverse forwards";
            setTimeout(() => toast.remove(), 300);
        }, 4000);
    }

    /* -------------------------------------------------------------
     * Ingestion / Drag-and-Drop Handlers
     * ------------------------------------------------------------- */
    // Open file dialog on click
    dropZone.addEventListener("click", () => fileInput.click());

    fileInput.addEventListener("change", (e) => {
        if (e.target.files.length > 0) {
            handleFileSelection(e.target.files[0]);
        }
    });

    // Drag over styling
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
        if (e.dataTransfer.files.length > 0) {
            handleFileSelection(e.dataTransfer.files[0]);
        }
    });

    function handleFileSelection(file) {
        const allowedExtensions = ["txt", "docx", "pdf"];
        const fileExt = file.name.split(".").pop().toLowerCase();

        if (!allowedExtensions.includes(fileExt)) {
            showToast(`Unsupported file type: .${fileExt}. Please upload PDF, DOCX, or TXT.`, "error");
            return;
        }

        if (file.size > 100 * 1024 * 1024) {
            showToast("File size exceeds 100MB limit.", "error");
            return;
        }

        activeFile = file;
        uploadDocument(file);
    }

    /* -------------------------------------------------------------
     * Document Upload Service Call (Async Queue Flow)
     * ------------------------------------------------------------- */
    function resetMetricsUI() {
        const lexicalChk = document.getElementById("chk-lexical");
        const semanticChk = document.getElementById("chk-semantic");
        const progressScore = document.getElementById("plagiarism-score-text");
        const progressCircle = document.querySelector(".circular-progress");

        if (progressScore) progressScore.textContent = "0%";
        if (progressCircle) {
            progressCircle.style.background = `conic-gradient(var(--border-color) 360deg, transparent 0deg)`;
        }
        
        document.getElementById("legend-val-lexical").textContent = "0%";
        document.getElementById("legend-val-hybrid").textContent = "0%";
        document.getElementById("legend-val-semantic").textContent = "0%";
        document.getElementById("legend-val-original").textContent = "100%";

        lexicalChk.innerHTML = '<i class="fa-regular fa-circle"></i> Lexical Matching (TF-IDF)';
        lexicalChk.className = "checklist-item";
        semanticChk.innerHTML = '<i class="fa-regular fa-circle"></i> Semantic Indexing (Embeddings)';
        semanticChk.className = "checklist-item";
    }

    async function uploadDocument(file) {
        // Update Metadata sidebar indicators
        metaFilename.textContent = file.name;
        metaStatus.innerHTML = '<span class="badge badge-dim">Uploading...</span>';
        
        // Show loading progress
        showToast(`Uploading ${file.name}...`, "info");
        
        const formData = new FormData();
        formData.append("file", file);

        try {
            const response = await fetch(API_UPLOAD_URL, {
                method: "POST",
                body: formData
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.detail || "Failed to upload document");
            }

            uploadResponseData = data;
            showToast("Document uploaded and segmented successfully.", "success");
            
            // Render Document Viewer (plain text)
            renderDocument(uploadResponseData);
            
            // Reset metrics cards in UI
            resetMetricsUI();

            // Enable Run Analysis button
            btnRunAnalysis.disabled = false;
            btnDownloadPdf.classList.add("hidden");
            metaStatus.innerHTML = '<span class="badge badge-dim">Uploaded</span>';
            
        } catch (error) {
            console.error("Upload Error:", error);
            showToast(error.message, "error");
            
            // Reset metadata card on failure
            metaFilename.textContent = "No file uploaded";
            metaStatus.innerHTML = '<span class="badge badge-dim">Idle</span>';
            btnRunAnalysis.disabled = true;
        }
    }

    async function triggerPlagiarismAnalysis(file) {
        if (!file) {
            showToast("No active file to analyze.", "error");
            return;
        }

        const lexicalChk = document.getElementById("chk-lexical");
        const semanticChk = document.getElementById("chk-semantic");

        btnRunAnalysis.disabled = true;
        showToast("Submitting document to plagiarism checker...", "info");

        // Set visual loading indicators
        metaStatus.innerHTML = '<span class="badge badge-dim">Queued...</span>';
        lexicalChk.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Checking Lexical Database...';
        lexicalChk.className = "checklist-item done";
        
        const formData = new FormData();
        formData.append("file", file);

        try {
            const response = await fetch(API_ANALYZE_URL, {
                method: "POST",
                body: formData
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.detail || "Failed to submit analysis job");
            }

            const jobId = data.job_id;
            currentJobId = jobId;
            
            // Start polling the job status
            pollAnalysisStatus(jobId, file.name);

        } catch (error) {
            console.error("Analysis Submission Error:", error);
            showToast(error.message, "error");
            metaStatus.innerHTML = '<span class="badge badge-dim">Failed</span>';
            btnRunAnalysis.disabled = false;
            resetMetricsUI();
        }
    }

    async function pollAnalysisStatus(jobId, filename) {
        const lexicalChk = document.getElementById("chk-lexical");
        const semanticChk = document.getElementById("chk-semantic");
        const progressScore = document.getElementById("plagiarism-score-text");
        const progressCircle = document.querySelector(".circular-progress");

        const interval = setInterval(async () => {
            try {
                const response = await fetch(`${API_STATUS_URL}/${jobId}`);
                const data = await response.json();
                
                if (!response.ok) {
                    throw new Error(data.detail || "Status check failed");
                }
                
                if (data.status === "completed") {
                    clearInterval(interval);
                    uploadResponseData = data.result;
                    
                    showToast("Document analysis complete!", "success");
                    metaStatus.innerHTML = '<span class="badge badge-dim">Analyzed</span>';

                    // Update checklist
                    lexicalChk.innerHTML = '<i class="fa-regular fa-circle-check"></i> Lexical Match Complete';
                    semanticChk.innerHTML = '<i class="fa-regular fa-circle-check"></i> Semantic Matching Complete';
                    semanticChk.className = "checklist-item done";

                    // Calculate real percentages
                    const analysis = uploadResponseData.analysis;
                    const total = analysis.total_sentences;
                    const lexicalCount = analysis.lexical_matches_count;
                    const hybridCount = analysis.hybrid_matches_count || 0;
                    const semanticCount = analysis.semantic_matches_count;

                    const pctL = total > 0 ? Math.round((lexicalCount / total) * 100) : 0;
                    const pctH = total > 0 ? Math.round((hybridCount / total) * 100) : 0;
                    const pctS = total > 0 ? Math.round((semanticCount / total) * 100) : 0;
                    const pctO = Math.max(0, 100 - pctL - pctH - pctS);

                    // Set circular progress middle text
                    const realPlagScore = pctL + pctH + pctS;
                    progressScore.textContent = `${realPlagScore}%`;
                    
                    // Set conic gradient
                    const degL = pctL * 3.6;
                    const degH = pctH * 3.6;
                    const degS = pctS * 3.6;
                    progressCircle.style.background = `conic-gradient(#ef4444 0deg ${degL}deg, #f59e0b ${degL}deg ${degL + degH}deg, #8b5cf6 ${degL + degH}deg ${degL + degH + degS}deg, #10b981 ${degL + degH + degS}deg 360deg)`;
                    
                    // Update Legend Values
                    document.getElementById("legend-val-lexical").textContent = `${pctL}%`;
                    document.getElementById("legend-val-hybrid").textContent = `${pctH}%`;
                    document.getElementById("legend-val-semantic").textContent = `${pctS}%`;
                    document.getElementById("legend-val-original").textContent = `${pctO}%`;

                    // Apply visual highlights to document sentences
                    applyPlagiarismHighlights(analysis);
                    
                    // Show Download PDF button
                    btnDownloadPdf.classList.remove("hidden");

                    // Save report to history
                    saveReportToHistory(uploadResponseData.filename, jobId, realPlagScore, uploadResponseData);

                    // Enable button
                    btnRunAnalysis.disabled = false;

                    // Final success toast
                    if (realPlagScore > 0) {
                        showToast(`Analysis complete. Found ${realPlagScore}% plagiarism match profile.`, "success");
                    } else {
                        showToast("Analysis complete. Document is 100% original and clean!", "success");
                    }

                } else if (data.status === "failed") {
                    clearInterval(interval);
                    throw new Error(data.error || "Analysis task failed");
                } else if (data.status === "processing") {
                    metaStatus.innerHTML = '<span class="badge badge-dim">Analyzing...</span>';
                    lexicalChk.innerHTML = '<i class="fa-regular fa-circle-check"></i> Lexical Match Complete';
                    semanticChk.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Indexing Semantic Vectors...';
                    semanticChk.className = "checklist-item done";
                } else {
                    metaStatus.innerHTML = '<span class="badge badge-dim">Queued...</span>';
                }
            } catch (error) {
                clearInterval(interval);
                console.error("Polling Error:", error);
                showToast(error.message, "error");
                
                metaStatus.innerHTML = '<span class="badge badge-dim">Failed</span>';
                btnRunAnalysis.disabled = false;
                resetMetricsUI();
            }
        }, 1000);
    }

    /* -------------------------------------------------------------
     * Document Rendering & Highlight Setup
     * ------------------------------------------------------------- */
    function renderDocument(data) {
        // Update details card
        viewerFilename.textContent = data.filename;
        const fileExt = data.filename.split(".").pop().toUpperCase();
        viewerDocType.textContent = fileExt;
        
        metaChars.textContent = data.char_count.toLocaleString();
        metaSentences.textContent = data.sentence_count.toLocaleString();
        metaStatus.innerHTML = '<span class="badge badge-dim">Segmented</span>';

        // Clear contents
        documentRender.innerHTML = "";

        // If no sentences were parsed
        if (!data.sentences || data.sentences.length === 0) {
            documentRender.textContent = data.text || "Empty document.";
            return;
        }

        // We construct the HTML dynamically using segments and coordinate index spans
        // Let's rebuild the text using sentence bounds to ensure coordinates align exactly
        let fullText = data.text;
        let lastOffset = 0;

        data.sentences.forEach((sentence, index) => {
            const start = sentence.start_char;
            const end = sentence.end_char;

            // Append any raw text between sentences (like original spaces or newlines)
            if (start > lastOffset) {
                const intermediateText = fullText.substring(lastOffset, start);
                const textSpan = document.createTextNode(intermediateText);
                documentRender.appendChild(textSpan);
            }

            // Create sentence highlights
            const sentSpan = document.createElement("span");
            sentSpan.className = "doc-sentence";
            sentSpan.textContent = sentence.text;
            sentSpan.dataset.index = index;
            sentSpan.dataset.start = start;
            sentSpan.dataset.end = end;

            // Hover interactions
            sentSpan.addEventListener("mouseenter", () => {
                highlightSentence(sentSpan, sentence);
            });

            // Click interactions (persists coordinates details in inspector)
            sentSpan.addEventListener("click", (e) => {
                e.stopPropagation();
                // Toggle active selection state
                document.querySelectorAll(".doc-sentence").forEach(s => s.classList.remove("active"));
                sentSpan.classList.add("active");
                const matchData = sentSpan.dataset.match ? JSON.parse(sentSpan.dataset.match) : null;
                inspectSentence(sentence, matchData, true);
            });

            documentRender.appendChild(sentSpan);
            lastOffset = end;
        });

        // Append remaining tail text
        if (lastOffset < fullText.length) {
            const tailText = fullText.substring(lastOffset);
            const textSpan = document.createTextNode(tailText);
            documentRender.appendChild(textSpan);
        }

        // Show viewer, hide upload panel
        dropZone.classList.add("hidden");
        documentViewer.classList.remove("hidden");
    }

    /* -------------------------------------------------------------
     * Coordinate Inspection Handlers
     * ------------------------------------------------------------- */
    function highlightSentence(element, sentence) {
        // If there's no clicked sentence active, update on hover
        const hasActiveClick = document.querySelector(".doc-sentence.active") !== null;
        if (!hasActiveClick) {
            const matchData = element.dataset.match ? JSON.parse(element.dataset.match) : null;
            inspectSentence(sentence, matchData, false);
        }
    }

    function inspectSentence(sentence, matchData, isClicked) {
        inspectorPlaceholder.classList.add("hidden");
        inspectorData.classList.remove("hidden");

        inspectStart.textContent = sentence.start_char;
        inspectEnd.textContent = sentence.end_char;
        inspectText.textContent = `"${sentence.text}"`;

        // Hide paraphrase result block from previous inspect runs
        const paraphraseBlock = document.getElementById("paraphrase-result-block");
        if (paraphraseBlock) {
            paraphraseBlock.classList.add("hidden");
        }

        const matchDetailsDiv = document.getElementById("plagiarism-match-details");
        const inspectMatchRefText = document.getElementById("inspect-match-ref-text");
        const matchSourceBlock = inspectMatchRefText ? inspectMatchRefText.closest(".inspector-text-block") : null;

        if (matchData) {
            matchDetailsDiv.classList.remove("hidden");
            if (matchSourceBlock) {
                matchSourceBlock.classList.remove("hidden");
            }
            
            const matchTypeBadge = document.getElementById("inspect-match-type");
            const matchScoreBadge = document.getElementById("inspect-match-score");
            const matchTitle = document.getElementById("inspect-match-title");
            const matchCitation = document.getElementById("inspect-match-citation");
            
            // Set Match Type Badge
            if (matchData.match_type === "lexical") {
                matchTypeBadge.className = "badge badge-red";
                matchTypeBadge.textContent = "Lexical Match";
            } else if (matchData.match_type === "hybrid") {
                matchTypeBadge.className = "badge badge-orange";
                matchTypeBadge.textContent = "Hybrid Match";
            } else {
                matchTypeBadge.className = "badge badge-purple";
                matchTypeBadge.textContent = "Semantic Match";
            }
            
            // Set Match Score
            const pct = Math.round(matchData.score * 100);
            matchScoreBadge.textContent = `${pct}% Similarity`;
            matchScoreBadge.className = "badge " + (
                matchData.match_type === "lexical" ? "badge-red" : 
                (matchData.match_type === "hybrid" ? "badge-orange" : "badge-purple")
            );
            
            // Set reference sentence and doc info
            inspectMatchRefText.textContent = `"${matchData.matched_sentence.text}"`;
            matchTitle.textContent = matchData.matched_sentence.doc_title;
            matchCitation.textContent = `${matchData.matched_sentence.doc_author} — ${matchData.matched_sentence.doc_source}`;
        } else {
            // Check if this sentence was marked as original
            const sentenceSpans = document.querySelectorAll(".doc-sentence");
            let isOriginal = false;
            sentenceSpans.forEach(span => {
                if (parseInt(span.dataset.start) === sentence.start_char && span.classList.contains("original")) {
                    isOriginal = true;
                }
            });

            if (isOriginal) {
                matchDetailsDiv.classList.remove("hidden");
                
                const matchTypeBadge = document.getElementById("inspect-match-type");
                const matchScoreBadge = document.getElementById("inspect-match-score");
                
                matchTypeBadge.className = "badge badge-green";
                matchTypeBadge.textContent = "Original Segment";
                
                matchScoreBadge.className = "badge badge-green";
                matchScoreBadge.textContent = "0% Similarity";
                
                if (matchSourceBlock) {
                    matchSourceBlock.classList.add("hidden");
                }
            } else {
                matchDetailsDiv.classList.add("hidden");
            }
        }
    }

    function applyPlagiarismHighlights(analysis) {
        if (!analysis || !analysis.matches) return;

        // Map query sentence start_char to its match object for quick lookup
        const matchesMap = {};
        analysis.matches.forEach(m => {
            matchesMap[m.query_sentence.start_char] = m;
        });

        // Select all sentence spans in the viewer
        const sentenceSpans = document.querySelectorAll(".doc-sentence");
        sentenceSpans.forEach(span => {
            const start = parseInt(span.dataset.start);
            const match = matchesMap[start];

            // Reset any old analysis classes first
            span.className = "doc-sentence";

            if (match) {
                const text = span.textContent;
                
                span.classList.add("plagiarized");
                if (match.match_type === "lexical") {
                    span.classList.add("match-lexical");
                } else if (match.match_type === "hybrid") {
                    span.classList.add("match-hybrid");
                } else {
                    span.classList.add("match-semantic");
                }
                span.dataset.match = JSON.stringify(match);

                // Re-render sentence text with word-level mark tags
                const highlights = match.highlights;
                if (highlights && highlights.length > 0) {
                    const sortedHls = highlights.map(hl => ({
                        start: hl.start_char - start,
                        end: hl.end_char - start,
                        text: hl.text
                    })).sort((a, b) => a.start - b.start);

                    let htmlContent = "";
                    let lastIdx = 0;

                    sortedHls.forEach(hl => {
                        if (hl.start > lastIdx) {
                            htmlContent += escapeHtml(text.substring(lastIdx, hl.start));
                        }
                        const markClass = match.match_type === "lexical" ? "mark-lexical" : 
                                          (match.match_type === "hybrid" ? "mark-hybrid" : "mark-semantic");
                        htmlContent += `<mark class="${markClass}">${escapeHtml(text.substring(hl.start, hl.end))}</mark>`;
                        lastIdx = hl.end;
                    });

                    if (lastIdx < text.length) {
                        htmlContent += escapeHtml(text.substring(lastIdx));
                    }

                    span.innerHTML = htmlContent;
                } else {
                    const markClass = match.match_type === "lexical" ? "mark-lexical" : 
                                      (match.match_type === "hybrid" ? "mark-hybrid" : "mark-semantic");
                    span.innerHTML = `<mark class="${markClass}">${escapeHtml(text)}</mark>`;
                }
            } else {
                // If it is not a match, it is clean/original! Apply original styles
                span.classList.add("original");
                span.removeAttribute("data-match");
            }
        });
    }

    function escapeHtml(str) {
        return str
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    // Reset Viewer/Upload Ingestion state
    btnReupload.addEventListener("click", () => {
        documentViewer.classList.add("hidden");
        dropZone.classList.remove("hidden");
        fileInput.value = ""; // clear input stream
        
        // Reset Metadata stats
        metaChars.textContent = "-";
        metaSentences.textContent = "-";
        metaFilename.textContent = "No file uploaded";
        metaStatus.innerHTML = '<span class="badge badge-dim">Idle</span>';
        
        // Reset Inspector state
        inspectorPlaceholder.classList.remove("hidden");
        inspectorData.classList.add("hidden");
        const paraphraseBlock = document.getElementById("paraphrase-result-block");
        if (paraphraseBlock) {
            paraphraseBlock.classList.add("hidden");
        }
        document.querySelectorAll(".doc-sentence").forEach(s => {
            s.className = "doc-sentence";
            s.removeAttribute("data-match");
            s.innerHTML = escapeHtml(s.textContent);
        });

        // Reset Plagiarism progress metrics & legend values
        const progressScore = document.getElementById("plagiarism-score-text");
        const progressCircle = document.querySelector(".circular-progress");
        const lexicalChk = document.getElementById("chk-lexical");
        const semanticChk = document.getElementById("chk-semantic");

        progressScore.textContent = "0%";
        progressCircle.style.background = "conic-gradient(var(--border-color) 360deg, transparent 0deg)";
        
        lexicalChk.innerHTML = '<i class="fa-regular fa-circle"></i> Lexical Matching (TF-IDF)';
        lexicalChk.className = "checklist-item";
        semanticChk.innerHTML = '<i class="fa-regular fa-circle"></i> Semantic Indexing (Embeddings)';
        semanticChk.className = "checklist-item";

        document.getElementById("legend-val-lexical").textContent = "0%";
        document.getElementById("legend-val-hybrid").textContent = "0%";
        document.getElementById("legend-val-semantic").textContent = "0%";
        document.getElementById("legend-val-original").textContent = "100%";

        activeFile = null;
        uploadResponseData = null;
        currentJobId = null;
        btnDownloadPdf.classList.add("hidden");
        btnRunAnalysis.disabled = true;
    });

    // Trigger analysis toast (Phase 2 Integration)
    // Trigger analysis (Phase 2 Integration)
    btnRunAnalysis.addEventListener("click", () => {
        if (!activeFile) {
            showToast("Please upload a file first.", "error");
            return;
        }
        triggerPlagiarismAnalysis(activeFile);
    });

    // Download PDF Report
    btnDownloadPdf.addEventListener("click", () => {
        if (!currentJobId) {
            showToast("No active report job ID found.", "error");
            return;
        }
        showToast("Downloading PDF report...", "info");
        window.open(`${API_BASE_URL}/api/v1/documents/report/${currentJobId}`, "_blank");
    });

    // Paraphrase button triggers Ollama API call
    btnQuickParaphrase.addEventListener("click", async () => {
        const sentenceText = inspectText.textContent.replace(/^"|"$/g, "").trim();
        if (!sentenceText) return;

        const paraphraseBlock = document.getElementById("paraphrase-result-block");
        const paraphraseText = document.getElementById("inspect-paraphrase-text");
        
        // Disable button and show spinner
        btnQuickParaphrase.disabled = true;
        btnQuickParaphrase.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Paraphrasing...';
        showToast("Paraphrasing segment with local Ollama...", "info");

        try {
            const response = await fetch(API_REWRITE_URL, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({ text: sentenceText })
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.detail || "Paraphrasing failed");
            }

            // Show result
            paraphraseText.textContent = `"${data.rewritten_text}"`;
            paraphraseBlock.classList.remove("hidden");
            showToast("Sentence paraphrased successfully!", "success");
        } catch (error) {
            console.error("Paraphrase Error:", error);
            showToast(error.message, "error");
        } finally {
            // Restore button
            btnQuickParaphrase.disabled = false;
            btnQuickParaphrase.innerHTML = '<i class="fa-solid fa-pen-nib"></i> Paraphrase Segment';
        }
    });

    /* -------------------------------------------------------------
     * Sidebar Nav Navigation & Workspace Switching
     * ------------------------------------------------------------- */
    const navItems = document.querySelectorAll(".nav-item");
    const dashboardWorkspace = document.getElementById("dashboard-workspace");
    const paraphraserWorkspace = document.getElementById("paraphraser-workspace");

    navItems.forEach(item => {
        item.addEventListener("click", (e) => {
            e.preventDefault();
            
            const tabId = item.id;
            if (tabId === "nav-dashboard" || tabId === "nav-plagiarism") {
                // Activate both dashboard & plagiarism links in sidebar to keep them synced
                navItems.forEach(n => n.classList.remove("active"));
                document.getElementById("nav-dashboard").classList.add("active");
                document.getElementById("nav-plagiarism").classList.add("active");
                
                dashboardWorkspace.classList.remove("hidden");
                paraphraserWorkspace.classList.add("hidden");
                reportsWorkspace.classList.add("hidden");
            } else if (tabId === "nav-paraphraser") {
                navItems.forEach(n => n.classList.remove("active"));
                item.classList.add("active");
                
                dashboardWorkspace.classList.add("hidden");
                paraphraserWorkspace.classList.remove("hidden");
                reportsWorkspace.classList.add("hidden");
            } else if (tabId === "nav-reports") {
                navItems.forEach(n => n.classList.remove("active"));
                item.classList.add("active");
                
                dashboardWorkspace.classList.add("hidden");
                paraphraserWorkspace.classList.add("hidden");
                reportsWorkspace.classList.remove("hidden");
                renderReportsHistory();
            } else {
                showToast(`${item.textContent.trim()} workspace module is coming in Phase 4/5.`, "info");
            }
        });
    });

    /* -------------------------------------------------------------
     * Plagiarism-Free Generator Workspace Logic [NEW]
     * ------------------------------------------------------------- */
    const paraInputText = document.getElementById("para-input-text");
    const paraOutputRender = document.getElementById("para-output-render");
    const btnRunParaphrase = document.getElementById("btn-run-paraphrase");
    const btnCopyParaphrase = document.getElementById("btn-copy-paraphrase");
    const paraTone = document.getElementById("para-tone");
    const paraOrigWords = document.getElementById("para-orig-words");
    const paraNewWords = document.getElementById("para-new-words");

    // Track word counts on input change
    paraInputText.addEventListener("input", () => {
        const text = paraInputText.value.trim();
        const wordCount = text ? text.split(/\s+/).length : 0;
        paraOrigWords.textContent = wordCount;
    });

    // Run Paraphrase Action
    btnRunParaphrase.addEventListener("click", async () => {
        const textToParaphrase = paraInputText.value.trim();
        if (!textToParaphrase) {
            showToast("Please enter some text to paraphrase.", "error");
            return;
        }

        // Disable button, show loading spinner
        btnRunParaphrase.disabled = true;
        btnRunParaphrase.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Paraphrasing...';
        paraOutputRender.innerHTML = '<span class="placeholder-text"><i class="fa-solid fa-spinner fa-spin"></i> Generating plagiarism-free text...</span>';
        btnCopyParaphrase.disabled = true;
        paraNewWords.textContent = "0";

        showToast("Paraphrasing text with local Llama3...", "info");

        try {
            const response = await fetch(API_REWRITE_URL, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({ 
                    text: textToParaphrase,
                    tone: paraTone.value
                })
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.detail || "Paraphrasing failed");
            }

            // Render result
            paraOutputRender.innerHTML = escapeHtml(data.rewritten_text);
            
            // Calculate new word count
            const wordsNew = data.rewritten_text.trim().split(/\s+/).length;
            paraNewWords.textContent = wordsNew;

            // Enable copy button
            btnCopyParaphrase.disabled = false;
            
            showToast("Text paraphrased successfully!", "success");
        } catch (error) {
            console.error("Paraphrase Workspace Error:", error);
            paraOutputRender.innerHTML = `<span class="placeholder-text" style="color: #ef4444; font-style: normal;"><i class="fa-solid fa-circle-exclamation"></i> Error: ${escapeHtml(error.message)}</span>`;
            showToast(error.message, "error");
        } finally {
            // Restore button
            btnRunParaphrase.disabled = false;
            btnRunParaphrase.innerHTML = '<i class="fa-solid fa-wand-magic-sparkles"></i> Paraphrase Text';
        }
    });

    // Copy to Clipboard Action
    btnCopyParaphrase.addEventListener("click", () => {
        const textToCopy = paraOutputRender.textContent;
        if (!textToCopy) return;

        navigator.clipboard.writeText(textToCopy).then(() => {
            showToast("Copied paraphrased text to clipboard!", "success");
        }).catch(err => {
            console.error("Clipboard Error:", err);
            showToast("Failed to copy text.", "error");
        });
    });

    /* -------------------------------------------------------------
     * Reports History & LocalStorage Persistence [NEW]
     * ------------------------------------------------------------- */
    function saveReportToHistory(filename, jobId, scorePct, resultData) {
        try {
            let history = localStorage.getItem("lemma_reports_history");
            history = history ? JSON.parse(history) : [];
            
            // Check if this jobId already exists in history to prevent duplicates
            const exists = history.some(item => item.jobId === jobId);
            if (exists) return;
            
            const newReport = {
                filename: filename,
                jobId: jobId,
                date: new Date().toLocaleString(),
                score: scorePct,
                result: resultData
            };
            
            history.unshift(newReport); // Add to the beginning
            
            // Limit history to 20 entries
            if (history.length > 20) {
                history.pop();
            }
            
            localStorage.setItem("lemma_reports_history", JSON.stringify(history));
        } catch (e) {
            console.error("Error saving report to history:", e);
        }
    }

    function renderReportsHistory() {
        try {
            let history = localStorage.getItem("lemma_reports_history");
            history = history ? JSON.parse(history) : [];
            
            reportsTableBody.innerHTML = "";
            
            if (history.length === 0) {
                reportsTable.classList.add("hidden");
                reportsEmptyState.classList.remove("hidden");
                btnClearHistory.disabled = true;
                return;
            }
            
            reportsTable.classList.remove("hidden");
            reportsEmptyState.classList.add("hidden");
            btnClearHistory.disabled = false;
            
            history.forEach((item, index) => {
                const tr = document.createElement("tr");
                
                // Get similarity badge class
                let scoreBadgeClass = "badge-green";
                if (item.score > 50) {
                    scoreBadgeClass = "badge-red";
                } else if (item.score > 20) {
                    scoreBadgeClass = "badge-purple";
                }
                
                tr.innerHTML = `
                    <td>
                        <i class="fa-solid fa-file-invoice" style="margin-right: 8px; color: var(--text-muted);"></i>
                        <strong>${escapeHtml(item.filename)}</strong>
                    </td>
                    <td>${escapeHtml(item.date)}</td>
                    <td>
                        <span class="badge ${scoreBadgeClass}">
                            ${item.score}% Similarity
                        </span>
                    </td>
                    <td><span class="badge badge-dim">Completed</span></td>
                    <td style="text-align: right;">
                        <button class="btn btn-sm btn-outline btn-restore-report" data-index="${index}" style="padding: 0.35rem 0.75rem; font-size: 0.75rem; margin-right: 0.25rem;">
                            <i class="fa-solid fa-eye"></i> View
                        </button>
                        <button class="btn btn-sm btn-secondary btn-download-report-pdf" data-jobid="${item.jobId}" style="padding: 0.35rem 0.75rem; font-size: 0.75rem;">
                            <i class="fa-solid fa-file-pdf"></i> PDF
                        </button>
                    </td>
                `;
                reportsTableBody.appendChild(tr);
            });
            
            // Bind view/restore clicks
            document.querySelectorAll(".btn-restore-report").forEach(btn => {
                btn.addEventListener("click", () => {
                    const idx = parseInt(btn.dataset.index);
                    const item = history[idx];
                    if (item && item.result) {
                        restoreReportToViewer(item);
                    }
                });
            });
            
            // Bind download pdf clicks
            document.querySelectorAll(".btn-download-report-pdf").forEach(btn => {
                btn.addEventListener("click", () => {
                    const jobId = btn.dataset.jobid;
                    showToast("Downloading PDF report...", "info");
                    window.open(`${API_BASE_URL}/api/v1/documents/report/${jobId}`, "_blank");
                });
            });
        } catch (e) {
            console.error("Error rendering reports history:", e);
        }
    }

    function restoreReportToViewer(reportItem) {
        // Switch variables
        uploadResponseData = reportItem.result;
        currentJobId = reportItem.jobId;
        activeFile = { name: reportItem.filename }; // mock active file
        
        // Render document text structures
        renderDocument(uploadResponseData);
        
        // Enable PDF download button
        btnDownloadPdf.classList.remove("hidden");
        
        // Immediately run analysis rendering in UI (without delay since it's already computed)
        const analysis = uploadResponseData.analysis;
        const lexicalChk = document.getElementById("chk-lexical");
        const semanticChk = document.getElementById("chk-semantic");
        const progressScore = document.getElementById("plagiarism-score-text");
        const progressCircle = document.querySelector(".circular-progress");

        lexicalChk.innerHTML = '<i class="fa-regular fa-circle-check"></i> Lexical Match Complete';
        lexicalChk.className = "checklist-item done";
        semanticChk.innerHTML = '<i class="fa-regular fa-circle-check"></i> Semantic Matching Complete';
        semanticChk.className = "checklist-item done";
        
        const total = analysis.total_sentences;
        const lexicalCount = analysis.lexical_matches_count;
        const hybridCount = analysis.hybrid_matches_count || 0;
        const semanticCount = analysis.semantic_matches_count;

        const pctL = total > 0 ? Math.round((lexicalCount / total) * 100) : 0;
        const pctH = total > 0 ? Math.round((hybridCount / total) * 100) : 0;
        const pctS = total > 0 ? Math.round((semanticCount / total) * 100) : 0;
        const pctO = Math.max(0, 100 - pctL - pctH - pctS);
        
        const realPlagScore = pctL + pctH + pctS;
        progressScore.textContent = `${realPlagScore}%`;
        
        const degL = pctL * 3.6;
        const degH = pctH * 3.6;
        const degS = pctS * 3.6;
        progressCircle.style.background = `conic-gradient(#ef4444 0deg ${degL}deg, #f59e0b ${degL}deg ${degL + degH}deg, #8b5cf6 ${degL + degH}deg ${degL + degH + degS}deg, #10b981 ${degL + degH + degS}deg 360deg)`;
        
        document.getElementById("legend-val-lexical").textContent = `${pctL}%`;
        document.getElementById("legend-val-hybrid").textContent = `${pctH}%`;
        document.getElementById("legend-val-semantic").textContent = `${pctS}%`;
        document.getElementById("legend-val-original").textContent = `${pctO}%`;

        applyPlagiarismHighlights(analysis);
        btnRunAnalysis.disabled = false;
        
        // Switch view to dashboard
        navItems.forEach(n => n.classList.remove("active"));
        document.getElementById("nav-dashboard").classList.add("active");
        document.getElementById("nav-plagiarism").classList.add("active");
        
        dashboardWorkspace.classList.remove("hidden");
        paraphraserWorkspace.classList.add("hidden");
        reportsWorkspace.classList.add("hidden");
        
        showToast(`Loaded analysis report for ${reportItem.filename}`, "success");
    }

    // Clear History Action
    btnClearHistory.addEventListener("click", () => {
        if (confirm("Are you sure you want to clear your reports history? This cannot be undone.")) {
            localStorage.removeItem("lemma_reports_history");
            renderReportsHistory();
            showToast("Reports history cleared.", "info");
        }
    });
});

