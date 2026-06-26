/**
 * Lemma Mobile UI & Tab Layout Engine
 */
document.addEventListener("DOMContentLoaded", () => {
    const isMobile = () => window.innerWidth < 768;

    // Check configuration and set up UI layout on load/resize
    function initMobileLayout() {
        if (!isMobile()) {
            removeMobileTabControls();
            return;
        }
        setupMobileTabControls();
    }

    window.addEventListener("resize", initMobileLayout);
    initMobileLayout();

    /* -------------------------------------------------------------
     * Dynamic Tab Injector
     * ------------------------------------------------------------- */
    function setupMobileTabControls() {
        // Prevent duplicate setups
        if (document.getElementById("mobile-workspace-tabs")) {
            // If already set up, make sure it is visible if dashboard is active
            const dashboardWorkspace = document.getElementById("dashboard-workspace");
            const tabHeader = document.getElementById("mobile-workspace-tabs");
            if (dashboardWorkspace && tabHeader) {
                const isDashboardHidden = dashboardWorkspace.classList.contains("hidden");
                tabHeader.style.display = isDashboardHidden ? "none" : "flex";
            }
            return;
        }

        // Find main dashboard workspace components
        const leftPanel = document.getElementById("dashboard-workspace")?.querySelector(".left-panel");
        const rightPanel = document.getElementById("dashboard-workspace")?.querySelector(".right-panel");

        if (!leftPanel || !rightPanel) return;

        // Group panels into tabs
        leftPanel.classList.add("mobile-tab-view", "active-tab");
        leftPanel.id = "tab-editor-panel";

        // Segment the progress card and inspector card within right-panel
        const progressCard = rightPanel.querySelector(".progress-card");
        const metadataCard = rightPanel.querySelector(".metadata-card");
        const inspectorCard = rightPanel.querySelector(".inspector-card");

        // Create virtual containers for responsive mobile views
        if (progressCard) {
            const metricsContainer = document.createElement("div");
            metricsContainer.id = "tab-metrics-panel";
            metricsContainer.className = "mobile-tab-view";
            // Reparent elements for mobile view organization
            progressCard.parentNode.insertBefore(metricsContainer, progressCard);
            metricsContainer.appendChild(metadataCard);
            metricsContainer.appendChild(progressCard);
        }

        if (inspectorCard) {
            const inspectContainer = document.createElement("div");
            inspectContainer.id = "tab-inspect-panel";
            inspectContainer.className = "mobile-tab-view";
            inspectorCard.parentNode.insertBefore(inspectContainer, inspectorCard);
            inspectContainer.appendChild(inspectorCard);
        }

        // Hide standard right-panel parent styles on mobile
        rightPanel.style.display = "contents";

        // Create Bottom Navigation Bar tabs for mobile mode
        const tabHeader = document.createElement("div");
        tabHeader.id = "mobile-workspace-tabs";
        tabHeader.className = "mobile-tab-bar";
        tabHeader.innerHTML = `
            <button class="mobile-tab-btn active" data-target="tab-editor-panel">
                <i class="fa-solid fa-file-lines"></i>
                <span>Document</span>
            </button>
            <button class="mobile-tab-btn" data-target="tab-metrics-panel">
                <i class="fa-solid fa-chart-simple"></i>
                <span>Metrics</span>
            </button>
            <button class="mobile-tab-btn" data-target="tab-inspect-panel">
                <i class="fa-solid fa-magnifying-glass"></i>
                <span>Inspector</span>
            </button>
        `;

        document.querySelector(".main-content").appendChild(tabHeader);

        // Bind clicks to the dynamically added tab buttons
        const buttons = tabHeader.querySelectorAll(".mobile-tab-btn");
        buttons.forEach(btn => {
            btn.addEventListener("click", () => {
                buttons.forEach(b => b.classList.remove("active"));
                btn.classList.add("active");

                document.querySelectorAll(".mobile-tab-view").forEach(view => {
                    view.classList.remove("active-tab");
                });

                const targetId = btn.dataset.target;
                document.getElementById(targetId).classList.add("active-tab");
            });
        });

        // Listen to sidebar/bottom-nav workspace changes to hide/show virtual workspace tabs
        const mainNavItems = document.querySelectorAll(".nav-item");
        mainNavItems.forEach(item => {
            item.addEventListener("click", () => {
                const isDashboardActive = (item.id === "nav-dashboard" || item.id === "nav-plagiarism");
                const currentTabHeader = document.getElementById("mobile-workspace-tabs");
                if (currentTabHeader) {
                    if (isDashboardActive && isMobile()) {
                        currentTabHeader.style.display = "flex";
                    } else {
                        currentTabHeader.style.display = "none";
                    }
                }
            });
        });

        // Intercept sentence clicks to swap to inspector tab automatically
        setupSentenceTapInterception();
    }

    function removeMobileTabControls() {
        const tabHeader = document.getElementById("mobile-workspace-tabs");
        if (tabHeader) tabHeader.remove();

        const rightPanel = document.getElementById("dashboard-workspace")?.querySelector(".right-panel");
        if (rightPanel) rightPanel.removeAttribute("style");

        document.querySelectorAll(".mobile-tab-view").forEach(view => {
            view.classList.remove("mobile-tab-view", "active-tab");
        });
    }

    /* -------------------------------------------------------------
     * Sentence Selection Intercept
     * ------------------------------------------------------------- */
    function setupSentenceTapInterception() {
        const renderContainer = document.getElementById("document-content-render");
        if (!renderContainer) return;

        // Use event delegation for sentence clicks
        renderContainer.addEventListener("click", (e) => {
            if (!isMobile()) return;
            
            const docSentence = e.target.closest(".doc-sentence");
            if (docSentence) {
                // Wait for document click handler to run, then switch tabs
                setTimeout(() => {
                    const inspectorTabBtn = document.querySelector('[data-target="tab-inspect-panel"]');
                    if (inspectorTabBtn) {
                        inspectorTabBtn.click(); // Programmatically shift view to Inspector card
                    }
                }, 120);
            }
        });
    }

    /* -------------------------------------------------------------
     * Developer URL Switcher Setup
     * ------------------------------------------------------------- */
    function setupDevApiSwitcher() {
        const serverStatus = document.querySelector(".server-status");
        if (!serverStatus) return;

        // Add visual double-click instruction tooltip for devs
        serverStatus.title = "Double-click to set custom Developer API Endpoint";
        
        serverStatus.addEventListener("dblclick", () => {
            const currentUrl = localStorage.getItem("lemma_override_api_url") || "None (Default)";
            const newUrl = prompt(`Enter custom Dev API Endpoint (Current: ${currentUrl}):`, "http://192.168.1.100:8000");
            
            if (newUrl !== null) {
                const trimmedUrl = newUrl.trim();
                if (trimmedUrl === "" || trimmedUrl.toLowerCase() === "default" || trimmedUrl.toLowerCase() === "none") {
                    localStorage.removeItem("lemma_override_api_url");
                    alert("Developer override removed. Reverting to default configuration. Reloading page...");
                } else {
                    localStorage.setItem("lemma_override_api_url", trimmedUrl);
                    alert(`Developer endpoint saved: ${trimmedUrl}. Reloading page...`);
                }
                window.location.reload();
            }
        });
    }

    // Initialize switcher
    setupDevApiSwitcher();
});
