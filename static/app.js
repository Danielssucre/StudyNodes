
const API_URL = '/api';

// State
let currentCard = null;

// DOM Elements
const dom = {
    title: document.getElementById('topic-title'),
    statGen: document.getElementById('stat-gen'),
    statDue: document.getElementById('stat-due'),
    statDays: document.getElementById('stat-days')
};

// Init
document.addEventListener('DOMContentLoaded', () => {
    loadCard();
    updateStats();
    setupRoadmapToggle();
});

function setupRoadmapToggle() {
    const btn = document.getElementById('btn-toggle-roadmap');
    const side = document.getElementById('roadmap-side');
    if (btn && side) {
        btn.onclick = () => {
            side.classList.toggle('collapsed');
        };
    }
}

async function updateStats() {
    try {
        const res = await fetch(`${API_URL}/stats`);
        const stats = await res.json();
        dom.statGen.innerText = `${stats.generated}/${stats.total}`;
        dom.statDue.innerText = stats.due_reviews;
        dom.statDays.innerText = stats.days_left;

        // Also update the roadmap layout
        updateRoadmap();
    } catch (e) {
        console.error("Stats fail", e);
    }
}

async function updateRoadmap() {
    try {
        const res = await fetch(`${API_URL}/roadmap`);
        const roadmap = await res.json();
        const container = document.getElementById('roadmap-container');
        container.innerHTML = '';

        roadmap.forEach((item, index) => {
            const dot = document.createElement('div');
            dot.className = `roadmap-dot ${item.level}`;
            dot.innerText = index + 1;
            dot.setAttribute('data-title', item.title);
            container.appendChild(dot);
        });
    } catch (e) {
        console.error("Roadmap fail", e);
    }
}

async function loadCard() {
    const cardDisplay = document.getElementById('card-display');

    // Reset UI: Hide all steps first
    ['vignette', 'foundation', 'algorithm', 'keys', 'mcq', 'srs'].forEach(s => {
        const el = document.getElementById(`step-${s}`);
        if (el) el.classList.add('hidden', 'locked');
    });
    dom.title.innerText = 'Buscando objetivo...';

    try {
        const res = await fetch(`${API_URL}/card`);
        if (!res.ok) {
            if (res.status === 404) {
                throw new Error('Sincronizando con Base de Datos de Inteligencia... (Generando Cartas Elite)');
            }
            throw new Error('Sin cartas disponibles');
        }

        const data = await res.json();
        currentCard = data;

        renderCard(data);

        // Phase 2: Fade in entire display area (standard)
        cardDisplay.classList.remove('fade-out');
        cardDisplay.classList.add('fade-in');
        setTimeout(() => cardDisplay.classList.remove('fade-in'), 500);

    } catch (e) {
        dom.title.innerText = '📡 SINCRONIZACIÓN ACTIVADA';
        document.getElementById('vignette-content').innerHTML = `
            <div style="text-align:center; padding: 40px;">
                <i class="fas fa-satellite-dish" style="font-size: 3rem; color: var(--accent); margin-bottom: 20px; animation: pulse 2s infinite;"></i>
                <p style="color:var(--accent); font-weight:800; font-size:1.1rem">${e.message}</p>
                <p style="color:#888; margin-top:10px">El sistema está realizando una <strong>Investigación Profunda</strong> en tiempo real. Esto tarda unos minutos por tema para asegurar máxima precisión 2026.</p>
                <button onclick="loadCard()" class="btn-primary" style="margin-top:20px">FORZAR REINTENTO</button>
            </div>
        `;
        cardDisplay.classList.remove('fade-out');
    }
}

function renderCard(data) {
    dom.title.innerText = data.topic;
    const parse = (text) => window.marked ? window.marked.parse(text) : text;

    // 1. Populate all sections
    document.getElementById('vignette-content').innerHTML = parse(data.vignette);
    document.getElementById('foundation-content').innerHTML = parse(data.foundation);

    // Algorithm handling (Check for Mermaid)
    const algorithmContent = document.getElementById('algorithm-content');
    const algorithmMermaid = document.getElementById('algorithm-mermaid');

    if (data.algorithm.includes('```mermaid')) {
        const mermaidMatch = data.algorithm.match(/```mermaid([\s\S]*?)```/);
        if (mermaidMatch) {
            // Senior Fix: Extract and clean the code
            const rawCode = mermaidMatch[1].trim();
            // Clean leading indentation from each line to prevent parser confusion
            const cleanCode = rawCode.split('\n').map(line => line.trim()).join('\n');

            console.log("DEBUG: Optimized Mermaid Code:\n", cleanCode);

            algorithmMermaid.innerHTML = '';
            algorithmMermaid.classList.remove('hidden');
            algorithmContent.innerHTML = parse(data.algorithm.replace(/```mermaid[\s\S]*?```/, ''));

            // Use render API (Async)
            const id = 'mermaid-svg-' + Math.random().toString(36).substr(2, 9);

            if (window.mermaid) {
                mermaid.render(id, cleanCode).then(({ svg }) => {
                    algorithmMermaid.innerHTML = svg;
                    console.log("DEBUG: Mermaid render successful.");
                }).catch(err => {
                    console.error("DEBUG: Mermaid render FAILED:", err);
                    algorithmMermaid.innerHTML = `
                        <div style="border:1px dashed red; padding:10px; font-size:0.8rem; background:rgba(255,0,0,0.1)">
                            <strong>Syntax Error in Decision Tree</strong><br>
                            <pre style="font-size:0.7rem; color:red">${err.message || err}</pre>
                            <details style="margin-top:5px">
                                <summary>Show Code</summary>
                                <pre style="background:#000; color:#0f0; padding:5px">${cleanCode}</pre>
                            </details>
                        </div>`;
                });
            }
        }
    } else {
        algorithmMermaid.classList.add('hidden');
        algorithmContent.innerHTML = parse(data.algorithm);
    }

    document.getElementById('keys-content').innerHTML = parse(data.keys);
    document.getElementById('pearls-content').innerHTML = parse(data.pearls || '*Pendiente de profundización quirúrgica...*');

    // 2. Reset visibility
    const steps = ['vignette', 'foundation', 'algorithm', 'keys', 'mcq', 'srs'];
    steps.forEach(s => {
        const el = document.getElementById(`step-${s}`);
        if (s === 'vignette') {
            el.classList.remove('hidden', 'locked');
        } else {
            el.classList.add('hidden', 'locked');
        }
    });

    // 3. Setup Unlock Buttons
    const setupUnlock = (btnId, nextStepId) => {
        const btn = document.getElementById(btnId);
        if (!btn) return;
        btn.classList.remove('hidden');
        btn.onclick = () => {
            const nextEl = document.getElementById(nextStepId);
            nextEl.classList.remove('hidden');
            setTimeout(() => nextEl.classList.remove('locked'), 50);
            btn.classList.add('hidden'); // Consumed

            setTimeout(() => {
                nextEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }, 100);
        };
    };

    setupUnlock('btn-unlock-foundation', 'step-foundation');
    setupUnlock('btn-unlock-algorithm', 'step-algorithm');
    setupUnlock('btn-unlock-keys', 'step-keys');
    setupUnlock('btn-unlock-mcq', 'step-mcq');

    // 4. MCQ Check Point
    const mcqOptions = document.getElementById('mcq-options');
    const mcqFeedback = document.getElementById('mcq-feedback');
    const mcqQuestion = document.getElementById('mcq-question');
    mcqFeedback.classList.add('hidden');
    mcqOptions.innerHTML = '';

    if (data.mcq) {
        mcqQuestion.innerText = data.mcq.question;
        data.mcq.options.forEach(opt => {
            const btn = document.createElement('button');
            btn.className = 'mcq-option';
            btn.innerText = opt;
            btn.onclick = () => handleMcqSelection(opt, btn, data.mcq);
            mcqOptions.appendChild(btn);
        });

        // Key support for gated MCQ
        const keyHandler = (e) => {
            const mcqStep = document.getElementById('step-mcq');
            if (mcqStep.classList.contains('locked') || mcqStep.classList.contains('hidden')) return;

            const key = e.key.toUpperCase();
            if (['A', 'B', 'C', 'D'].includes(key)) {
                const optIndex = key.charCodeAt(0) - 65;
                const targetBtn = mcqOptions.children[optIndex];
                if (targetBtn && !targetBtn.disabled) {
                    handleMcqSelection(data.mcq.options[optIndex], targetBtn, data.mcq);
                }
            }
        };
        document.addEventListener('keydown', keyHandler, { once: true });
    }

    function handleMcqSelection(opt, btn, mcq) {
        const isCorrect = opt.startsWith(mcq.answer.charAt(0));
        Array.from(mcqOptions.children).forEach(b => b.disabled = true);
        btn.classList.add(isCorrect ? 'correct' : 'wrong');

        mcqFeedback.classList.remove('hidden');
        mcqFeedback.innerHTML = `
            <div class="mcq-result-header ${isCorrect ? 'success' : 'fail'}">
                ${isCorrect ? '✨ ¡EXCELENTE! DOMINAS EL TEMA' : '⚠️ ESTUDIA ESTE PUNTO CLAVE'}
            </div>
            <strong>Respuesta: ${mcq.answer}</strong>
        `;

        // REVEAL SRS CONTROLS
        const srsStep = document.getElementById('step-srs');
        srsStep.classList.remove('hidden');
        setTimeout(() => {
            srsStep.classList.remove('locked');
            srsStep.scrollIntoView({ behavior: 'smooth' });
        }, 600);
    }
}

async function submitReview(rating) {
    if (!currentCard) return;

    // Reset scroll and show loading in vignette area
    document.getElementById('card-display').scrollTop = 0;

    try {
        await fetch(`${API_URL}/review`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                card_filename: currentCard.filename,
                rating: rating
            })
        });

        loadCard();
        updateStats();

    } catch (e) {
        alert("Error guardando progreso: " + e.message);
    }
}
