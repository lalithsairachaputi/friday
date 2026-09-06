document.addEventListener('DOMContentLoaded', () => {
    // Select the DOM container targets
    const splineScene = document.getElementById('nexbot-canvas');
    const hudStatus = document.getElementById('hud-loading-status');
    
    const scanBtn = document.getElementById('trigger-scan');
    const optimizeBtn = document.getElementById('trigger-optimize');
    const resetBtn = document.getElementById('trigger-reset');

    // 1. Wait for the Spline engine to fully parse the runtime file instance
    splineScene.addEventListener('load', (event) => {
        // This variable contains the main Spline application instance pipeline
        const splineApp = event.detail.app;
        hudStatus.innerText = "NEXBOT Core Online";
        hudStatus.style.color = "#4af6c3";

        // 2. Attach Interactive UI Action Click Listeners
        scanBtn.addEventListener('click', () => {
            setActiveButton(scanBtn);
            hudStatus.innerText = "Scanning framework loops...";
            
            /* 
             PRO TIP: If you configured object interactions inside your Spline panel,
             you can emit events directly by naming the trigger and the object ID:
             splineApp.emitEvent('mouseHover', 'Bot');
            */
        });

        optimizeBtn.addEventListener('click', () => {
            setActiveButton(optimizeBtn);
            hudStatus.innerText = "Optimizing data asset arrays...";
        });

        resetBtn.addEventListener('click', () => {
            setActiveButton(resetBtn);
            hudStatus.innerText = "Recalibrating camera tracking matrices...";
        });
    });

    // Helper function to switch visual emphasis states between sidebar buttons
    function setActiveButton(activeButton) {
        [scanBtn, optimizeBtn, resetBtn].forEach(btn => btn.classList.remove('active'));
        activeButton.classList.add('active');
    }
});