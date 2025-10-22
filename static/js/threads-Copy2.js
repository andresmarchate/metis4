/* Artifact ID: 96e670cb-1a3b-4c8d-9f18-7a2fe345d1c0 */
/* Version: e3f4g5h6-i7j8-k9l0-m1n2-o3p4q5r6 */
const ThreadsModule = {
    threadsData: [], // Store threads for export

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
        this.section.style.display = 'block';
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
            this.threadsData = data.threads; // Store for export
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

        // Global export buttons
        const globalExportDiv = document.createElement('div');
        globalExportDiv.className = 'button-container';
        globalExportDiv.innerHTML = `
            <button class="button" onclick="ThreadsModule.exportThreads('excel', null)">Exportar Todos (Excel)</button>
            <button class="button" onclick="ThreadsModule.exportThreads('pdf', null)">Exportar Todos (PDF)</button>
        `;
        this.results.appendChild(globalExportDiv);

        // Render each thread
        threads.forEach((thread, threadIndex) => {
            const details = document.createElement('details');
            details.className = 'thread-details';
            details.style.marginBottom = '10px';
            const summary = document.createElement('summary');
            summary.textContent = thread.label || 'Hilo Sin Etiqueta';
            summary.className = 'thread-summary';
            details.appendChild(summary);

            // Thread export buttons
            const threadExportDiv = document.createElement('div');
            threadExportDiv.className = 'button-container';
            threadExportDiv.innerHTML = `
                <button class="button" onclick="ThreadsModule.exportThreads('excel', ${threadIndex})">Exportar Hilo (Excel)</button>
                <button class="button" onclick="ThreadsModule.exportThreads('pdf', ${threadIndex})">Exportar Hilo (PDF)</button>
            `;
            details.appendChild(threadExportDiv);

            // Thread table
            const tableContainer = document.createElement('div');
            tableContainer.className = 'table-container';
            const table = document.createElement('table');
            table.className = 'data-table';
            table.innerHTML = `
                <thead>
                    <tr>
                        <th>Índice</th>
                        <th>Fecha</th>
                        <th>Remitente</th>
                        <th>Destinatarios</th>
                        <th>Asunto</th>
                        <th>Resumen</th>
                        <th>Puntos Resueltos</th>
                        <th>Puntos Pendientes</th>
                    </tr>
                </thead>
                <tbody>
                    ${thread.emails.map(email => `
                        <tr>
                            <td><a href="#" class="email-link" data-index="${email.index}">${email.index.substring(0, 8)}</a></td>
                            <td>${email.date}</td>
                            <td>${email.from}</td>
                            <td>${email.to}</td>
                            <td>${email.subject}</td>
                            <td>${email.summary}</td>
                            <td>${email.resolved_points}</td>
                            <td>${email.pending_points}</td>
                        </tr>
                    `).join('')}
                </tbody>
            `;
            tableContainer.appendChild(table);
            details.appendChild(tableContainer);
            this.results.appendChild(details);

            // Add click handlers for email links
            table.querySelectorAll('.email-link').forEach(link => {
                link.addEventListener('click', (e) => {
                    e.preventDefault();
                    const index = link.dataset.index;
                    console.log('Opening email details for index:', index);
                    SearchModule.showEmailDetails(index, true);
                });
            });
        });
    },

    async exportThreads(format, threadIndex) {
        console.log(`Exporting threads as ${format}, threadIndex: ${threadIndex}`);
        try {
            const threadsToExport = threadIndex === null ? this.threadsData : [this.threadsData[threadIndex]];
            const response = await fetch('/api/export_threads', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ threads: threadsToExport, format })
            });
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `threads_export.${format}`;
            document.body.appendChild(a);
            a.click();
            a.remove();
            window.URL.revokeObjectURL(url);
            console.log(`Exported threads as ${format}`);
        } catch (error) {
            console.error(`Error exporting threads as ${format}:`, error.message);
            this.errorDiv.textContent = `Error al exportar: ${error.message}`;
            this.errorDiv.style.display = 'block';
        }
    }
};

console.log('threads.js loaded successfully');