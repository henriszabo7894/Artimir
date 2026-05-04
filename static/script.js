document.addEventListener("DOMContentLoaded", function () {

    setInterval(() => {
        fetch("/api/heartbeat", { method: "POST" });
    }, 5000);

    function detectDevice() {
        const isMobile =
            /Android|iPhone|iPad|iPod|Opera Mini|IEMobile|WPDesktop/i.test(navigator.userAgent)
            || window.innerWidth <= 768;

        document.body.classList.add(isMobile ? "mobile-device" : "desktop-device");
    }

    detectDevice();

    const steps = document.querySelectorAll(".step");

    const typedText = document.getElementById("typedText");
    const cursor = document.getElementById("cursor");
    const nextBtn = document.getElementById("btnToHeight");
    const btnToNarration = document.getElementById("btnToNarration");

    const narrationYes = document.getElementById("narrationYes");
    const narrationNo = document.getElementById("narrationNo");
    const pauseBtn = document.getElementById("pauseNarration");
    const resumeBtn = document.getElementById("resumeNarration");

    const mailYes = document.getElementById("mailYes");
    const mailNo = document.getElementById("mailNo");

    const sendEmailBtn = document.getElementById("sendEmail");
    const emailInput = document.getElementById("emailInput");

    const timerElement = document.getElementById("sessionTimer");
    const endMessage = document.getElementById("sessionEndMessage");

    let narrationStarted = false;
    let narrationPaused = false;
    let narrationWatcher = null;

    async function sendMapping(command) {
        try {
            await fetch(`/api/mapping/${command}`, { method: "POST" });
        } catch (e) {
            console.error("Mapping error:", e);
        }
    }

    const freeze = () => sendMapping("freeze");
    const resume = () => sendMapping("resume");
    const narrationStartAPI = () => sendMapping("narration/start");
    const narrationPauseAPI = () => sendMapping("narration/pause");
    const narrationResumeAPI = () => sendMapping("narration/resume");
    const narrationStopAPI = () => sendMapping("narration/stop");

    function showStep(id) {
        steps.forEach(step => step.classList.remove("active"));
        document.getElementById(id)?.classList.add("active");
    }

    /* =========================
       TEXTE QUI S'ÉCRIT
    ========================= */

    if (typedText && typeof biographyText !== "undefined") {
        let i = 0;
        const speed = 25;

        typedText.innerHTML = "";

        function typeWriter() {
            if (i < biographyText.length) {
                typedText.innerHTML += biographyText.charAt(i);
                i++;
                setTimeout(typeWriter, speed);
            } else {
                if (cursor) cursor.style.display = "none";
                if (nextBtn) nextBtn.classList.remove("hidden");
            }
        }

        typeWriter();
    }

    /* =========================
       BOUTONS ÉTAPES
    ========================= */

    if (nextBtn) {
        nextBtn.onclick = () => showStep("step2");
    }

    if (btnToNarration) {
        btnToNarration.onclick = () => showStep("step3");
    }

    if (mailYes) {
        mailYes.onclick = () => {
            stopNarration();
            freeze();
            showStep("step5");
        };
    }

    if (mailNo) {
        mailNo.onclick = () => {
            stopNarration();
            freeze();
            showStep("step6");
        };
    }

    /* =========================
       NARRATION
    ========================= */

    function hideNarrationControls() {
        pauseBtn?.classList.add("hidden");
        resumeBtn?.classList.add("hidden");
    }

    async function checkNarrationStatus() {
        try {
            const res = await fetch("/api/mapping/status");
            const data = await res.json();

            if (data.status === "success") {
                const active = data.data.narration_active;

                if (!active && narrationStarted) {
                    narrationStarted = false;
                    narrationPaused = false;

                    if (narrationWatcher) {
                        clearInterval(narrationWatcher);
                        narrationWatcher = null;
                    }

                    resume();
                    hideNarrationControls();
                    showStep("step4");
                }
            }
        } catch (e) {
            console.error("Watcher error:", e);
        }
    }

    function startNarration() {
        narrationStarted = true;
        narrationPaused = false;

        narrationStartAPI();

        pauseBtn?.classList.remove("hidden");
        resumeBtn?.classList.add("hidden");

        if (narrationWatcher) clearInterval(narrationWatcher);
        narrationWatcher = setInterval(checkNarrationStatus, 1000);
    }

    function pauseNarration() {
        if (!narrationStarted || narrationPaused) return;

        narrationPauseAPI();
        narrationPaused = true;

        pauseBtn?.classList.add("hidden");
        resumeBtn?.classList.remove("hidden");
    }

    function resumeNarration() {
        if (!narrationStarted || !narrationPaused) return;

        narrationResumeAPI();
        narrationPaused = false;

        resumeBtn?.classList.add("hidden");
        pauseBtn?.classList.remove("hidden");
    }

    function stopNarration() {
        if (narrationStarted) {
            narrationStopAPI();
        }

        narrationStarted = false;
        narrationPaused = false;

        if (narrationWatcher) {
            clearInterval(narrationWatcher);
            narrationWatcher = null;
        }

        hideNarrationControls();
    }

    narrationYes?.addEventListener("click", startNarration);

    narrationNo?.addEventListener("click", () => {
        stopNarration();
        resume();
        showStep("step4");
    });

    pauseBtn?.addEventListener("click", pauseNarration);
    resumeBtn?.addEventListener("click", resumeNarration);

    /* =========================
       EMAIL
    ========================= */

    function isValidEmail(email) {
        return /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(email);
    }

    sendEmailBtn?.addEventListener("click", async () => {
        const email = emailInput.value.trim();

        if (!isValidEmail(email)) {
            alert("Email invalide");
            return;
        }

        stopNarration();
        freeze();

        sendEmailBtn.innerText = "Envoi...";
        sendEmailBtn.disabled = true;

        try {
            const res = await fetch("/api/send-email", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ email })
            });

            const data = await res.json();

            if (data.status === "success") {
                const step5 = document.getElementById("step5");

                if (step5) {
                    step5.innerHTML = `
                        <div class="polaroid-card">
                            <div class="polaroid-image"></div>
                            <div class="polaroid-text">
                                <h2>📨 Email envoyé !</h2>
                                <p>Votre portrait a été envoyé à :</p>
                                <strong>${email}</strong>
                            </div>
                        </div>
                        <br>
                        <a href="/reset" class="gold-btn">Terminer</a>
                    `;
                }
            } else {
                alert(data.message);
                sendEmailBtn.innerText = "Envoyer";
                sendEmailBtn.disabled = false;
            }

        } catch (e) {
            alert("Erreur serveur");
            sendEmailBtn.innerText = "Envoyer";
            sendEmailBtn.disabled = false;
        }
    });

    /* =========================
       TIMER SESSION
    ========================= */

    let remainingTime = 300;

    const sessionTimer = setInterval(() => {
        remainingTime--;

        let minutes = Math.floor(remainingTime / 60);
        let seconds = remainingTime % 60;

        let formatted =
            `${minutes.toString().padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`;

        if (timerElement) {
            timerElement.innerHTML = "⏳ Temps restant : " + formatted;
        }

        if (remainingTime <= 0) {
            clearInterval(sessionTimer);
            stopNarration();
            freeze();

            document.querySelectorAll("button").forEach(btn => {
                btn.disabled = true;
            });

            document.querySelectorAll(".step").forEach(el => {
                el.style.display = "none";
            });

            if (endMessage) {
                endMessage.classList.remove("hidden");
            }

            setTimeout(() => {
                window.location.href = "/reset";
            }, 5000);
        }
    }, 1000);

    /* =========================
       MODE DEV
    ========================= */

    window.adminAccess = function () {
        const code = prompt("Code développeur :");

        if (!code) return;

        fetch("/admin-login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ code })
        })
        .then(res => {
            if (res.ok) {
                alert("Mode dev activé 🚀");
                location.reload();
            } else {
                alert("Code incorrect");
            }
        })
        .catch(() => alert("Erreur serveur"));
    };

});