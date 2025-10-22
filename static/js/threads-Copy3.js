/* Artifact ID: 96e670cb-1a3b-4c8d-9f18-7a2fe345d1c0 */
/* Version: g9h0i1j2-k3l4-m5n6-o7p8-q9r0s1t2 */
const ThreadsModule = {
    threadsData: [],
    currentQuery: '',

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
            this.currentQuery = query;
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
            this.threadsData = data.threads;
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

        // Botones de exportación globales
        const globalExportDiv = document.createElement('div');
        globalExportDiv.className = 'button-container';
        globalExportDiv.innerHTML = `
            <button class="button" onclick="ThreadsModule.exportThreads('excel', null)">Exportar Todos (Excel)</button>
            <button class="button" onclick="ThreadsModule.exportThreads('pdf', null)">Exportar Todos (PDF)</button>
        `;
        this.results.appendChild(globalExportDiv);

        // Renderizar cada hilo
        threads.forEach((thread, threadIndex) => {
            const details = document.createElement('details');
            details.className = 'thread-details';
            details.style.marginBottom = '10px';
            const summary = document.createElement('summary');
            summary.textContent = thread.label || 'Hilo Sin Etiqueta';
            summary.className = 'thread-summary';
            details.appendChild(summary);

            // Botones de exportación por hilo
            const threadExportDiv = document.createElement('div');
            threadExportDiv.className = 'button-container';
            threadExportDiv.innerHTML = `
                <button class="button" onclick="ThreadsModule.exportThreads('excel', ${threadIndex})">Exportar Hilo (Excel)</button>
                <button class="button" onclick="ThreadsModule.exportThreads('pdf', ${threadIndex})">Exportar Hilo (PDF)</button>
            `;
            details.appendChild(threadExportDiv);

            // Tabla del hilo
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
                        <th>Confianza</th>
                        <th>Acciones</th>
                    </tr>
                </thead>
                <tbody>
                    ${thread.emails.map(email => `
                        <tr>
                            <td><a href="#" class="email-link" data-index="${UtilsModule.escapeHtml(email.index)}">${UtilsModule.escapeHtml(email.index.substring(0, 8))}</a></td>
                            <td>${UtilsModule.escapeHtml(email.date)}</td>
                            <td>${UtilsModule.escapeHtml(email.from)}</td>
                            <td>${UtilsModule.escapeHtml(email.to)}</td>
                            <td>${UtilsModule.escapeHtml(email.subject)}</td>
                            <td>${UtilsModule.escapeHtml(email.summary)}</td>
                            <td>${UtilsModule.escapeHtml(email.resolved_points)}</td>
                            <td>${UtilsModule.escapeHtml(email.pending_points)}</td>
                            <td>${email.confidence_score.toFixed(2)}</td>
                            <td>
                                <button class="validate-button" onclick="ThreadsModule.validateEmail('${UtilsModule.escapeHtml(email.index)}')">Validar</button>
                                <button class="reject-button" onclick="ThreadsModule.rejectEmail('${UtilsModule.escapeHtml(email.index)}')">Rechazar</button>
                            </td>
                        </tr>
                    `).join('')}
                </tbody>
            `;
            tableContainer.appendChild(table);
            details.appendChild(tableContainer);
            this.results.appendChild(details);

            // Manejadores de clics para los enlaces de correo
            table.querySelectorAll('.email-link').forEach(link => {
                link.addEventListener('click', (e) => {
                    e.preventDefault();
                    const index = link.dataset.index;
                    console.log('Opening email details for index:', index);
                    SearchModule.showEmailDetails(index);
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
    },

    async validateEmail(emailIndex) {
        console.log(`Validating email: ${emailIndex}`);
        try {
            const response = await fetch('/api/feedback/validate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email_index: emailIndex, query: this.currentQuery })
            });
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            this.errorDiv.textContent = 'Feedback enviado: Correo validado.';
            this.errorDiv.style.display = 'block';
            this.errorDiv.style.color = 'green';
        } catch (error) {
            console.error(`Error validating email: ${error.message}`);
            this.errorDiv.textContent = `Error: ${error.message}`;
            this.errorDiv.style.display = 'block';
            this.errorDiv.style.color = 'red';
        }
    },

    async rejectEmail(emailIndex) {
        console.log(`Rejecting email: ${emailIndex}`);
        try {
            const response = await fetch('/api/feedback/reject', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email_index: emailIndex, query: this.currentQuery })
            });
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            this.errorDiv.textContent = 'Feedback enviado: Correo rechazado.';
            this.errorDiv.style.display = 'block';
            this.errorDiv.style.color = 'green';
        } catch (error) {
            console.error(`Error rejecting email: ${error.message}`);
            this.errorDiv.textContent = `Error: ${error.message}`;
            this.errorDiv.style.display = 'block';
            this.errorDiv.style.color = 'red';
        }
    }
};

console.log('threads.js loaded successfully');