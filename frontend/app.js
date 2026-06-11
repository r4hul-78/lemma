/**
 * Lemma Frontend Engine (Vanilla JS)
 */

document.addEventListener("DOMContentLoaded", () => {
    // API URL configuration
    const API_BASE_URL = "http://localhost:8000";
    const API_UPLOAD_URL = `${API_BASE_URL}/api/v1/documents/upload`;
    const API_HEALTH_URL = `${API_BASE_URL}/api/v1/health`;

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

    // App State
    let activeFile = null;
    let uploadResponseData = null;

    // Initialize Page
    checkServerHealth();
    setInterval(checkServerHealth, 10000); // Check health every 10 seconds

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
     * Document Upload Service Call
     * ------------------------------------------------------------- */
    async function uploadDocument(file) {
        // Update Metadata sidebar indicators
        metaFilename.textContent = file.name;
        metaStatus.innerHTML = '<span class="badge badge-dim">Uploading...</span>';
        
        // Show loading progress
        showToast(`Uploading and parsing ${file.name}...`, "info");
        
        const formData = new FormData();
        formData.append("file", file);

        try {
            const response = await fetch(API_UPLOAD_URL, {
                method: "POST",
                body: formData
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.detail || "Failed to parse document");
            }

            uploadResponseData = data;
            showToast("Document segmented successfully!", "success");
            
            // Render Document Viewer
            renderDocument(data);
            
            // Enable analysis button trigger (Phase 2)
            btnRunAnalysis.disabled = false;
        } catch (error) {
            console.error("Upload Error:", error);
            showToast(error.message, "error");
            
            // Reset metadata card on failure
            metaFilename.textContent = "No file uploaded";
            metaStatus.innerHTML = '<span class="badge badge-dim">Idle</span>';
        }
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
            } else {
                matchTypeBadge.className = "badge badge-purple";
                matchTypeBadge.textContent = "Semantic Match";
            }
            
            // Set Match Score
            const pct = Math.round(matchData.score * 100);
            matchScoreBadge.textContent = `${pct}% Similarity`;
            matchScoreBadge.className = "badge " + (matchData.match_type === "lexical" ? "badge-red" : "badge-purple");
            
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
                span.classList.add(match.match_type === "lexical" ? "match-lexical" : "match-semantic");
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
                        const markClass = match.match_type === "lexical" ? "mark-lexical" : "mark-semantic";
                        htmlContent += `<mark class="${markClass}">${escapeHtml(text.substring(hl.start, hl.end))}</mark>`;
                        lastIdx = hl.end;
                    });

                    if (lastIdx < text.length) {
                        htmlContent += escapeHtml(text.substring(lastIdx));
                    }

                    span.innerHTML = htmlContent;
                } else {
                    const markClass = match.match_type === "lexical" ? "mark-lexical" : "mark-semantic";
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
        document.getElementById("legend-val-semantic").textContent = "0%";
        document.getElementById("legend-val-original").textContent = "100%";

        activeFile = null;
        uploadResponseData = null;
        btnRunAnalysis.disabled = true;
    });

    // Trigger analysis toast (Phase 2 Integration)
    btnRunAnalysis.addEventListener("click", () => {
        if (!uploadResponseData || !uploadResponseData.analysis) {
            showToast("No analysis report found for this document.", "error");
            return;
        }

        const analysis = uploadResponseData.analysis;
        showToast("Phase 2 Matcher Engine running (Lexical & Semantic)...", "info");
        
        const lexicalChk = document.getElementById("chk-lexical");
        const semanticChk = document.getElementById("chk-semantic");
        const progressScore = document.getElementById("plagiarism-score-text");
        const progressCircle = document.querySelector(".circular-progress");

        lexicalChk.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Checking Lexical Database...';
        lexicalChk.className = "checklist-item done";

        setTimeout(() => {
            lexicalChk.innerHTML = '<i class="fa-regular fa-circle-check"></i> Lexical Match Complete';
            semanticChk.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Indexing Semantic Vectors...';
            semanticChk.className = "checklist-item done";
            
            // Calculate real percentages
            const total = analysis.total_sentences;
            const lexicalCount = analysis.lexical_matches_count;
            const semanticCount = analysis.semantic_matches_count;

            const pctL = total > 0 ? Math.round((lexicalCount / total) * 100) : 0;
            const pctS = total > 0 ? Math.round((semanticCount / total) * 100) : 0;
            const pctO = Math.max(0, 100 - pctL - pctS);

            setTimeout(() => {
                semanticChk.innerHTML = '<i class="fa-regular fa-circle-check"></i> Semantic Matching Complete';
                
                // Set circular progress middle text (overall plagiarism score)
                const realPlagScore = pctL + pctS;
                progressScore.textContent = `${realPlagScore}%`;
                
                // Calculate conic gradient slices:
                // Red (Lexical): 0 to pctL%
                // Purple (Semantic): pctL% to (pctL + pctS)%
                // Green (Original): (pctL + pctS)% to 100%
                const degL = pctL * 3.6;
                const degS = pctS * 3.6;
                
                progressCircle.style.background = `conic-gradient(#ef4444 0deg ${degL}deg, #8b5cf6 ${degL}deg ${degL + degS}deg, #10b981 ${degL + degS}deg 360deg)`;
                
                // Update Legend Values
                document.getElementById("legend-val-lexical").textContent = `${pctL}%`;
                document.getElementById("legend-val-semantic").textContent = `${pctS}%`;
                document.getElementById("legend-val-original").textContent = `${pctO}%`;

                // Apply visual highlights to document sentences
                applyPlagiarismHighlights(analysis);
                
                // Final success toast
                if (realPlagScore > 0) {
                    showToast(`Analysis complete. Found ${realPlagScore}% plagiarism match profile.`, "success");
                } else {
                    showToast("Analysis complete. Document is 100% original and clean!", "success");
                }
            }, 1200);
        }, 1200);
    });

    // Paraphrase button triggers UI alert
    btnQuickParaphrase.addEventListener("click", () => {
        const sentenceText = inspectText.textContent.replace(/"/g, "");
        showToast(`Sending segment to local Ollama rewriter: "${sentenceText.substring(0, 30)}..."`, "info");
    });

    /* -------------------------------------------------------------
     * Sidebar Nav Navigation & Theme Styling Mock
     * ------------------------------------------------------------- */
    const navItems = document.querySelectorAll(".nav-item");
    navItems.forEach(item => {
        item.addEventListener("click", (e) => {
            e.preventDefault();
            navItems.forEach(n => n.classList.remove("active"));
            item.classList.add("active");
            
            const tabId = item.id;
            if (tabId === "nav-dashboard" || tabId === "nav-plagiarism") {
                // Keep showing dashboard
            } else {
                showToast(`${item.textContent.trim()} workspace module is coming in Phase 3/4.`, "info");
            }
        });
    });
});

