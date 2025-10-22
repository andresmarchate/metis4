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
            const coherence = thread.coherence !== undefined ? thread.coherence.toFixed(2) : 'N/A';
            const avgConcordance = thread.emails.length > 0 
                ? (thread.emails.reduce((sum, email) => sum + (email.concordance || 0), 0) / thread.emails.length).toFixed(2) 
                : 'N/A';
            summary.textContent = `${thread.label || 'Hilo Sin Etiqueta'} (Coherencia: ${coherence}, Concordancia Promedio: ${avgConcordance})`;
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

            // Encabezado
            const thead = document.createElement('thead');
            const headerRow = document.createElement('tr');
            ['Índice', 'Fecha', 'Remitente', 'Destinatarios', 'Asunto', 'Resumen', 'Puntos Resueltos', 'Puntos Pendientes', 'Confianza', 'Concordancia', 'Acciones'].forEach(header => {
                const th = document.createElement('th');
                th.textContent = header;
                headerRow.appendChild(th);
            });
            thead.appendChild(headerRow);
            table.appendChild(thead);

            // Cuerpo
            const tbody = document.createElement('tbody');
            thread.emails.forEach(email => {
                const row = document.createElement('tr');

                // Índice
                const indexCell = document.createElement('td');
                const indexLink = document.createElement('a');
                indexLink.href = '#';
                indexLink.className = 'email-link';
                indexLink.dataset.index = UtilsModule.escapeHtml(email.index);
                indexLink.textContent = UtilsModule.truncateIndex(email.index);
                indexCell.appendChild(indexLink);
                row.appendChild(indexCell);

                // Fecha
                const dateCell = document.createElement('td');
                dateCell.textContent = UtilsModule.escapeHtml(email.date || 'N/A');
                row.appendChild(dateCell);

                // Remitente
                const fromCell = document.createElement('td');
                fromCell.textContent = UtilsModule.escapeHtml(email.from || 'N/A');
                row.appendChild(fromCell);

                // Destinatarios
                const toCell = document.createElement('td');
                toCell.textContent = UtilsModule.escapeHtml(email.to || 'N/A');
                row.appendChild(toCell);

                // Asunto
                const subjectCell = document.createElement('td');
                subjectCell.textContent = UtilsModule.escapeHtml(email.subject || 'N/A');
                row.appendChild(subjectCell);

                // Resumen
                const summaryCell = document.createElement('td');
                summaryCell.textContent = UtilsModule.escapeHtml(email.summary || 'N/A');
                row.appendChild(summaryCell);

                // Puntos Resueltos
                const resolvedCell = document.createElement('td');
                resolvedCell.textContent = UtilsModule.escapeHtml(email.resolved_points || 'N/A');
                row.appendChild(resolvedCell);

                // Puntos Pendientes
                const pendingCell = document.createElement('td');
                pendingCell.textContent = UtilsModule.escapeHtml(email.pending_points || 'N/A');
                row.appendChild(pendingCell);

                // Confianza
                const confidenceCell = document.createElement('td');
                confidenceCell.textContent = email.confidence_score !== undefined ? email.confidence_score.toFixed(2) : '0.00';
                row.appendChild(confidenceCell);

                // Concordancia
                const concordanceCell = document.createElement('td');
                concordanceCell.textContent = email.concordance !== undefined ? email.concordance.toFixed(2) : '0.00';
                row.appendChild(concordanceCell);

                // Acciones
                const actionsCell = document.createElement('td');
                const validateButton = document.createElement('button');
                validateButton.className = 'validate-button';
                validateButton.textContent = 'Validar';
                validateButton.onclick = () => ThreadsModule.validateEmail(email.index);
                const rejectButton = document.createElement('button');
                rejectButton.className = 'reject-button';
                rejectButton.textContent = 'Rechazar';
                rejectButton.onclick = () => ThreadsModule.rejectEmail(email.index);
                actionsCell.appendChild(validateButton);
                actionsCell.appendChild(rejectButton);
                row.appendChild(actionsCell);

                tbody.appendChild(row);
            });
            table.appendChild(tbody);
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