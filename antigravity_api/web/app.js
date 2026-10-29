// Antigravity Web Chatbot Client

const messagesContainer = document.getElementById("messagesContainer");
const welcomeHero = document.getElementById("welcomeHero");
const chatInput = document.getElementById("chatInput");
const sendBtn = document.getElementById("sendBtn");
const modelSelect = document.getElementById("modelSelect");
const personaSelect = document.getElementById("personaSelect");
const clearChatBtn = document.getElementById("clearChatBtn");
const userNameEl = document.getElementById("userName");
const userEmailEl = document.getElementById("userEmail");
const userAvatarEl = document.getElementById("userAvatar");
const quotaPctEl = document.getElementById("quotaPct");
const quotaBarEl = document.getElementById("quotaBar");
const latencyPill = document.getElementById("latencyPill");

let conversationHistory = [];
let isGenerating = false;

// Configure Marked
marked.setOptions({
    highlight: function(code, lang) {
        if (lang && hljs.getLanguage(lang)) {
            try {
                return hljs.highlight(code, { language: lang }).value;
            } catch (__) {}
        }
        return hljs.highlightAuto(code).value;
    },
    breaks: true
});

const PERSONA_PROMPTS = {
    general: "You are Antigravity AI, a helpful, highly capable, and intelligent assistant.",
    coding: "You are an elite software architect and senior fullstack engineer. You write concise, production-ready, beautiful code with clean structure and robust error handling.",
    security: "You are a world-class cybersecurity expert and bug bounty hunter. You provide clear vulnerability analyses, verification methodologies, OWASP security assessments, and proof-of-concept guidelines.",
    architect: "You are an enterprise system and cloud infrastructure architect. You design scalable, resilient, fault-tolerant architectures with microservices, caching, and CI/CD best practices."
};

// Initialize
async function initApp() {
    await fetchHealth();
    await fetchQuota();

    // Setup input autosize
    chatInput.addEventListener("input", function() {
        this.style.height = "auto";
        this.style.height = Math.min(this.scrollHeight, 180) + "px";
    });

    chatInput.addEventListener("keydown", function(e) {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    sendBtn.addEventListener("click", sendMessage);
    clearChatBtn.addEventListener("click", clearChat);

    // Prompt Chips
    document.querySelectorAll(".prompt-chip").forEach(chip => {
        chip.addEventListener("click", () => {
            chatInput.value = chip.dataset.prompt;
            chatInput.focus();
            chatInput.dispatchEvent(new Event("input"));
        });
    });
}

async function fetchHealth() {
    try {
        const res = await fetch("/health");
        if (res.ok) {
            const data = await res.json();
            if (data.authenticated_user && data.authenticated_user !== "Unknown") {
                userEmailEl.textContent = data.authenticated_user;
                userNameEl.textContent = data.user_name || data.authenticated_user.split("@")[0];
                userAvatarEl.textContent = (data.user_name || "A")[0].toUpperCase();
            }
        }
    } catch (e) {
        console.warn("Health check error", e);
    }
}

async function fetchQuota() {
    try {
        const res = await fetch("/api/quota");
        if (res.ok) {
            const data = await res.json();
            const quotas = data.quotas || {};
            const first = Object.values(quotas)[0];
            if (first && first.remainingFraction !== undefined) {
                const pct = Math.round(first.remainingFraction * 100);
                quotaPctEl.textContent = pct + "%";
                quotaBarEl.style.width = pct + "%";
            }
        }
    } catch (e) {
        console.warn("Quota error", e);
    }
}

function clearChat() {
    conversationHistory = [];
    messagesContainer.innerHTML = "";
    messagesContainer.appendChild(welcomeHero);
    welcomeHero.style.display = "flex";
}

function appendMessage(role, content = "") {
    if (welcomeHero) welcomeHero.style.display = "none";

    const row = document.createElement("div");
    row.className = `message-row ${role}`;

    const avatar = document.createElement("div");
    avatar.className = "msg-avatar";
    avatar.textContent = role === "user" ? "U" : "AI";

    const contentDiv = document.createElement("div");
    contentDiv.className = "msg-content";
    if (role === "user") {
        contentDiv.textContent = content;
    } else {
        contentDiv.innerHTML = marked.parse(content);
    }

    row.appendChild(avatar);
    row.appendChild(contentDiv);
    messagesContainer.appendChild(row);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;

    return contentDiv;
}

async function sendMessage() {
    const text = chatInput.value.trim();
    if (!text || isGenerating) return;

    chatInput.value = "";
    chatInput.style.height = "auto";
    sendBtn.disabled = true;
    isGenerating = true;

    // Append user message
    appendMessage("user", text);
    conversationHistory.push({ role: "user", content: text });

    // Append assistant placeholder
    const assistantContentEl = appendMessage("assistant", "Thinking...");
    let accumulatedText = "";

    const selectedModel = modelSelect.value;
    const persona = personaSelect.value;
    const systemPrompt = PERSONA_PROMPTS[persona] || PERSONA_PROMPTS.general;

    const startTime = performance.now();
    latencyPill.textContent = "Streaming...";
    latencyPill.className = "status-pill active";

    try {
        const response = await fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                message: text,
                model: selectedModel,
                history: conversationHistory.slice(0, -1),
                system_prompt: systemPrompt
            })
        });

        if (!response.ok) {
            throw new Error(`Server returned status ${response.status}`);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n");
            buffer = lines.pop(); // keep remaining partial line

            for (const line of lines) {
                const trimmed = line.trim();
                if (!trimmed || !trimmed.startsWith("data: ")) continue;
                const dataStr = trimmed.slice(6);
                if (dataStr === "[DONE]") break;

                try {
                    const parsed = JSON.parse(dataStr);
                    const choices = parsed.choices || [];
                    if (choices.length > 0) {
                        const delta = choices[0].delta || {};
                        if (delta.content) {
                            accumulatedText += delta.content;
                            assistantContentEl.innerHTML = marked.parse(accumulatedText);
                            messagesContainer.scrollTop = messagesContainer.scrollHeight;
                        }
                    }
                } catch (e) {
                    // Ignore JSON parsing errors for partial chunks
                }
            }
        }

        conversationHistory.push({ role: "assistant", content: accumulatedText });
        const elapsed = Math.round(performance.now() - startTime);
        latencyPill.textContent = `${elapsed}ms`;
        latencyPill.className = "status-pill";
    } catch (err) {
        console.error(err);
        assistantContentEl.innerHTML = `<span style="color:#ef4444">Error: ${err.message}</span>`;
        latencyPill.textContent = "Error";
        latencyPill.className = "status-pill";
    } finally {
        isGenerating = false;
        sendBtn.disabled = false;
        chatInput.focus();
    }
}

// Start
document.addEventListener("DOMContentLoaded", initApp);
