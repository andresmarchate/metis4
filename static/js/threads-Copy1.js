/* Artifact ID: 96e670cb-1a3b-4c8d-9f18-7a2fe345d1c0 */
/* Version: c1d2e3f4-g5h6-i7j8-k9l0-m1n2o3p4 */
const ThreadsModule = {
    init() {
        console.log('ThreadsModule initializing');
        this.section = document.getElementById('threads-section');
        this.form = document.getElementById('threads-form');
        this.queryInput = document.getElementById('threads-query');
        this.errorDiv = document.getElementById('threads-error');
        this.results = document.getElementById('threads-results');
        console.log('DOM elements:', {
            section: !!this.section,
            form: !!this.form,
            queryInput: !!this.queryInput,
            errorDiv: !!this.errorDiv,
            results: !!this.results
        });
        if (!this.section || !this.form || !this.queryInput || !this.results || !this.errorDiv) {
            console.error('ThreadsModule initialization failed: missing DOM elements');
            return;
        }
        this.form.addEventListener('submit', (e) => {
            e.preventDefault();
            this.analyzeThreads();
        });
    },

    showTab() {
        console.log('Showing Threads tab');
        if (!this.section) {
            console.error('Cannot show Threads tab: section is null');
            return;
        }
        this.section.classList.add('active');
        this.section.style.display = 'block'; // Force visibility for testing
        if (this.results) {
            this.results.innerHTML = '<p>Introduce una consulta para analizar hilos temáticos.</p>';
            console.log('Set placeholder text in threads-results');
        } else {
            console.error('threads-results element not found');
        }
        if (this.errorDiv) {
            this.errorDiv.style.display = 'none';
        }
        console.log('Threads tab visibility:', {
            display: window.getComputedStyle(this.section).display,
            classList: this.section.className
        });
    },

    async analyzeThreads() {
        console.log('Analyzing threads');
        const query = this.queryInput.value.trim();
        if (!query) {
            console.warn('Empty query provided');
            this.errorDiv.textContent = 'Por favor, introduce una consulta válida.';
            this.errorDiv.style.display = 'block';
            return;
        }
        try {
            this.errorDiv.style.display = 'none';
            this.results.innerHTML = '<p>Procesando hilos temáticos...</p>';
            const response = await fetch('/api/threads', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query })
            });
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const data = await response.json();
            console.log('Threads response:', data);
            if (data.error) {
                throw new Error(data.error);
            }
            this.renderThreads(data.threads);
        } catch (error) {
            console.error('Error analyzing threads:', error.message);
            this.errorDiv.textContent = `Error: ${error.message}`;
            this.errorDiv.style.display = 'block';
            this.results.innerHTML = '';
        }
    },

    renderThreads(threads) {
        console.log('Rendering threads:', threads);
        this.results.innerHTML = '';
        if (!threads || threads.length === 0) {
            this.results.innerHTML = '<p>No se encontraron hilos temáticos.</p>';
            return;
        }
        this.results.innerHTML = '<p>Hilos temáticos encontrados. Implementación de renderizado pendiente.</p>';
    }
};

console.log('threads.js loaded successfully');