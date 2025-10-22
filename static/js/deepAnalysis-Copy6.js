/* Artifact ID: d4e5f6g7-8901-2345-d6e7-f89012345678 */
/* Version: z6a7b8c9-0123-4567-z8a9-b01234567890 */
const DeepAnalysisModule = {
    init({ deepAnalysisSessionId, deepAnalysisEmails, setDeepAnalysisSessionId, setDeepAnalysisEmails }) {
        this.deepAnalysisSessionId = deepAnalysisSessionId;
        this.deepAnalysisEmails = deepAnalysisEmails || [];
        this.setDeepAnalysisSessionId = setDeepAnalysisSessionId;
        this.setDeepAnalysisEmails = setDeepAnalysisEmails;

        // DOM elements
        this.deepAnalysisSection = document.getElementById('deep-analysis-section');
        this.themeCheckboxes = document.getElementById('theme-checkboxes');
        this.processDeepAnalysisBtn = document.getElementById('process-deep-analysis');
        this.deepAnalysisInput = document.getElementById('deep-analysis-input');
        this.deepAnalysisPrompt = document.getElementById('deep-analysis-prompt');
        this.submitDeepAnalysisBtn = document.getElementById('submit-deep-analysis');
        this.resetDeepAnalysisContextBtn = document.getElementById('reset-deep-analysis-context');
        this.deepAnalysisResponse = document.getElementById('deep-analysis-response');

        // Debug initialization
        console.log('DeepAnalysisModule init:', {
            deepAnalysisSection: !!this.deepAnalysisSection,
            themeCheckboxes: !!this.themeCheckboxes,
            deepAnalysisResponse: !!this.deepAnalysisResponse,
            processDeepAnalysisBtn: !!this.processDeepAnalysisBtn,
            deepAnalysisInput: !!this.deepAnalysisInput
        });

        // Event listeners
        if (this.processDeepAnalysisBtn) {
            this.processDeepAnalysisBtn.addEventListener('click', () => this.processDeepAnalysis());
        } else {
            console.warn('processDeepAnalysisBtn not found');
        }
        if (this.submitDeepAnalysisBtn) {
            this.submitDeepAnalysisBtn.addEventListener('click', () => this.submitDeepAnalysis());
        }
        if (this.resetDeepAnalysisContextBtn) {
            this.resetDeepAnalysisContextBtn.addEventListener('click', () => this.resetDeepAnalysisContext());
        }
    },

    showTab() {
        if (!this.deepAnalysisSection) {
            console.error('deepAnalysisSection is undefined, cannot show tab');
            return;
        }
        console.log('Showing Análisis Profundo tab');
        document.querySelectorAll('.tab-content').forEach(tab => tab.classList.remove('active'));
        document.querySelectorAll('.tab-link').forEach(tabLink => tabLink.classList.remove('active'));
        this.deepAnalysisSection.classList.add('active');
        const tabLink = document.querySelector('.tab-link[data-tab="deep-analysis"]');
        if (tabLink) {
            tabLink.classList.add('active');
        } else {
            console.warn('Tab link for "deep-analysis" not found');
        }
        this.populateThemeCheckboxes();
    },

    populateThemeCheckboxes(themes = ThemesModule.currentThemes) {
        console.log('Populating theme checkboxes:', themes);
        if (!this.themeCheckboxes) {
            console.error('themeCheckboxes element not found');
            return;
        }
        const selectedThemeIds = Array.from(this.themeCheckboxes.querySelectorAll('input[type="checkbox"]:checked'))
            .map(checkbox => checkbox.value);
        console.log('Preserving selected theme IDs:', selectedThemeIds);

        this.themeCheckboxes.innerHTML = '';
        if (!Array.isArray(themes) || themes.length === 0) {
            console.log('No themes available for checkboxes');
            this.themeCheckboxes.innerHTML = '<p>No hay temas disponibles para seleccionar.</p>';
            return;
        }

        themes.forEach(theme => {
            const checkboxWrapper = document.createElement('label');
            checkboxWrapper.className = 'theme-checkbox';
            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.value = theme.theme_id;
            checkbox.dataset.title = theme.title;
            if (selectedThemeIds.includes(theme.theme_id)) {
                checkbox.checked = true;
            }
            const labelText = document.createTextNode(theme.title);
            checkboxWrapper.appendChild(checkbox);
            checkboxWrapper.appendChild(labelText);
            this.themeCheckboxes.appendChild(checkboxWrapper);
            console.log('Added checkbox for theme:', theme.title, 'with ID:', theme.theme_id, 'checked:', checkbox.checked);
        });
    },

    // Utility to parse summary field
    formatSummary(summary) {
        if (!summary || summary === 'N/A') return 'N/A';
        try {
            if (summary.startsWith('{') && summary.includes('"summary"')) {
                const parsed = JSON.parse(summary);
                return UtilsModule.escapeHtml(parsed.summary || summary);
            }
        } catch (e) {
            console.warn('Failed to parse summary as JSON:', summary, e);
        }
        return UtilsModule.escapeHtml(summary);
    },

    async processDeepAnalysis() {
        console.log('Process deep analysis clicked');
        const selectedThemes = Array.from(this.themeCheckboxes.querySelectorAll('input[type="checkbox"]:checked'))
            .map(checkbox => ({
                theme_id: checkbox.value,
                title: checkbox.dataset.title
            }));
        console.log('Selected themes:', selectedThemes);

        if (selectedThemes.length === 0) {
            alert('Por favor, selecciona al menos un tema para analizar.');
            return;
        }

        if (!this.deepAnalysisSection.classList.contains('active')) {
            this.showTab();
        } else {
            console.log('Deep Analysis tab already active, skipping showTab');
        }

        try {
            const response = await fetch('/api/deep_analysis_init', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ theme_ids: selectedThemes.map(theme => theme.theme_id) })
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            console.log('Deep analysis initialization response:', data);
            if (data.error) {
                throw new Error(data.error);
            }

            this.deepAnalysisSessionId = data.session_id;
            console.log('Local deepAnalysisSessionId set:', this.deepAnalysisSessionId);
            this.setDeepAnalysisSessionId(data.session_id);
            console.log('After external setter, deepAnalysisSessionId:', this.deepAnalysisSessionId);

            this.deepAnalysisEmails = data.email_data || [];
            console.log('Local deepAnalysisEmails set:', this.deepAnalysisEmails);
            this.setDeepAnalysisEmails(data.email_data || []);
            console.log('After external setter, deepAnalysisEmails:', this.deepAnalysisEmails);

            if (!this.deepAnalysisResponse) {
                console.error('deepAnalysisResponse element not found');
                alert('Error: No se encontró el contenedor para mostrar los correos.');
                return;
            }

            if (!this.deepAnalysisInput) {
                console.error('deepAnalysisInput element not found');
            } else {
                this.deepAnalysisInput.style.display = 'block';
                console.log('Set deepAnalysisInput display to block');
            }

            const tableRows = this.deepAnalysisEmails.length > 0
                ? this.deepAnalysisEmails.map((email, index) => {
                    console.log(`Rendering email ${index}:`, {
                        index: email.index,
                        date: email.date,
                        from: email.from,
                        to: email.to,
                        subject: email.subject,
                        summary: email.summary
                    });
                    return `
                        <tr>
                            <td><a href="#" class="deep-analysis-email-link" data-index="${UtilsModule.escapeHtml(email.index || 'N/A')}">${UtilsModule.truncateIndex(email.index || 'N/A')}</a></td>
                            <td>${UtilsModule.escapeHtml(email.date ? new Date(email.date).toLocaleString() : 'N/A')}</td>
                            <td>${UtilsModule.escapeHtml(email.from || 'N/A')}</td>
                            <td>${UtilsModule.escapeHtml(email.to || 'N/A')}</td>
                            <td>${UtilsModule.escapeHtml(email.subject || 'N/A')}</td>
                            <td>${this.formatSummary(email.summary).slice(0, 100)}${email.summary && email.summary.length > 100 ? '...' : ''}</td>
                        </tr>
                    `;
                }).join('')
                : '<tr><td colspan="6">No hay correos disponibles.</td></tr>';

            const tableHtml = `
                <p>Análisis inicializado para los temas seleccionados. Ingresa tu consulta.</p>
                <h3>Correos disponibles para análisis:</h3>
                <div class="table-container">
                    <table>
                        <thead>
                            <tr>
                                <th>Índice</th>
                                <th>Fecha</th>
                                <th>Remitente</th>
                                <th>Destinatario</th>
                                <th>Asunto</th>
                                <th>Resumen</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${tableRows}
                        </tbody>
                    </table>
                </div>
            `;
            console.log('Generated table HTML:', tableHtml);
            console.log('Setting deepAnalysisResponse innerHTML, element:', this.deepAnalysisResponse);
            this.deepAnalysisResponse.innerHTML = tableHtml;
            this.attachDeepAnalysisEmailListeners();
            console.log('Attached email listeners, table rows:', this.deepAnalysisResponse.querySelectorAll('tbody tr').length);
        } catch (error) {
            console.error('Error initializing deep analysis:', error.message);
            alert(`Error al inicializar análisis profundo: ${error.message}`);
        }
    },

    async submitDeepAnalysis() {
        const prompt = this.deepAnalysisPrompt.value.trim();
        console.log('Submitting deep analysis prompt:', prompt);

        if (!prompt) {
            alert('Por favor, ingresa una consulta válida.');
            return;
        }

        if (!this.deepAnalysisSessionId) {
            console.error('No active session, deepAnalysisSessionId:', this.deepAnalysisSessionId);
            alert('No hay una sesión activa. Por favor, inicializa el análisis primero.');
            return;
        }

        try {
            const response = await fetch('/api/deep_analysis_prompt', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: this.deepAnalysisSessionId, prompt })
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            console.log('Deep analysis prompt response:', data);
            if (data.error) {
                throw new Error(data.error);
            }

            const indexRegex = /(?:con índice\s+)?\'([0-9a-f]{64})\'/gi;
            console.log('Reasoning text before processing:', data.reasoning);
            const linkedReasoning = data.reasoning.replace(indexRegex, (match, index) => {
                console.log('Found index in reasoning:', index);
                return `<a href="#" class="deep-analysis-email-link" data-index="${index}">${UtilsModule.truncateIndex(index)}</a>`;
            });
            console.log('Processed reasoning with links:', linkedReasoning);

            if (!this.deepAnalysisResponse) {
                console.error('deepAnalysisResponse element not found for prompt response');
                return;
            }

            this.deepAnalysisResponse.innerHTML = `
                <h3>Respuesta:</h3>
                <p>${UtilsModule.escapeHtml(data.response)}</p>
                <h3>Razonamiento:</h3>
                <p>${linkedReasoning}</p>
                <h3>Alternativas:</h3>
                <ul>${data.alternatives.map(alt => `<li>${UtilsModule.escapeHtml(alt)}</li>`).join('') || '<li>Ninguna</li>'}</ul>
                <h3>Referencias:</h3>
                <div class="table-container">
                    <table>
                        <thead>
                            <tr>
                                <th>Índice</th>
                                <th>Fecha</th>
                                <th>Remitente</th>
                                <th>Destinatario</th>
                                <th>Asunto</th>
                                <th>Resumen</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${data.references.map(ref => `
                                <tr>
                                    <td><a href="#" class="deep-analysis-email-link" data-index="${UtilsModule.escapeHtml(ref.index)}">${UtilsModule.truncateIndex(ref.index)}</a></td>
                                    <td>${UtilsModule.escapeHtml(ref.date ? new Date(ref.date).toLocaleString() : 'N/A')}</td>
                                    <td>${UtilsModule.escapeHtml(ref.from || 'N/A')}</td>
                                    <td>${UtilsModule.escapeHtml(ref.to || 'N/A')}</td>
                                    <td>${UtilsModule.escapeHtml(ref.subject)}</td>
                                    <td>${this.formatSummary(ref.summary).slice(0, 100)}${ref.summary && ref.summary.length > 100 ? '...' : ''}</td>
                                </tr>
                            `).join('') || '<tr><td colspan="6">No hay referencias.</td></tr>'}
                        </tbody>
                    </table>
                </div>
            `;
            this.deepAnalysisPrompt.value = '';
            this.attachDeepAnalysisEmailListeners();
            console.log('Prompt response rendered, table rows:', this.deepAnalysisResponse.querySelectorAll('tbody tr').length);
        } catch (error) {
            console.error('Error processing deep analysis prompt:', error.message);
            alert(`Error al procesar la consulta: ${error.message}`);
        }
    },

    async resetDeepAnalysisContext() {
        console.log('Resetting deep analysis context');
        if (!this.deepAnalysisSessionId) {
            alert('No hay una sesión activa para resetear.');
            return;
        }

        try {
            const response = await fetch('/api/deep_analysis_reset', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: this.deepAnalysisSessionId })
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            console.log('Deep analysis reset response:', data);
            if (data.error) {
                throw new Error(data.error);
            }

            this.deepAnalysisSessionId = null;
            this.setDeepAnalysisSessionId(null);
            this.deepAnalysisEmails = [];
            this.setDeepAnalysisEmails([]);
            if (this.deepAnalysisInput) {
                this.deepAnalysisInput.style.display = 'none';
            }
            this.deepAnalysisPrompt.value = '';
            if (this.deepAnalysisResponse) {
                this.deepAnalysisResponse.innerHTML = '<p>Contexto reseteado. Selecciona nuevos temas para continuar.</p>';
            }
            alert('Contexto reseteado correctamente.');
        } catch (error) {
            console.error('Error resetting deep analysis context:', error.message);
            alert(`Error al resetear el contexto: ${error.message}`);
        }
    },

    attachDeepAnalysisEmailListeners() {
        const links = this.deepAnalysisResponse ? this.deepAnalysisResponse.querySelectorAll('.deep-analysis-email-link') : [];
        console.log('Attaching listeners to', links.length, 'email links');
        links.forEach(link => {
            link.addEventListener('click', async (e) => {
                e.preventDefault();
                const identifier = e.target.dataset.index;
                console.log('Clicked deep analysis email link with identifier:', identifier);
                if (!identifier || identifier === 'N/A') {
                    console.error('No valid identifier found for link:', e.target);
                    alert('Identificador de correo no válido.');
                    return;
                }
                try {
                    console.log('Fetching email details for identifier:', identifier);
                    const response = await fetch(`/api/email?index=${encodeURIComponent(identifier)}`);
                    if (!response.ok) {
                        throw new Error(`HTTP error! status: ${response.status}`);
                    }
                    const email = await response.json();
                    console.log('Email details:', email);
                    const attachmentsContent = Array.isArray(email.attachments_content)
                        ? email.attachments_content.join('\n')
                        : email.attachments_content || '';
                    const detailsElement = document.getElementById('email-details');
                    if (detailsElement) {
                        detailsElement.innerHTML = `
                            <p><strong>Índice:</strong> ${UtilsModule.truncateIndex(email.index)}</p>
                            <p><strong>ID:</strong> ${UtilsModule.escapeHtml(email.message_id || 'N/A', true)}</p>
                            <p><strong>De:</strong> ${UtilsModule.escapeHtml(email.from || 'N/A')}</p>
                            <p><strong>Para:</strong> ${UtilsModule.escapeHtml(email.to || 'N/A')}</p>
                            <p><strong>Asunto:</strong> ${UtilsModule.escapeHtml(email.subject || '')}</p>
                            <p><strong>Fecha:</strong> ${UtilsModule.escapeHtml(email.date || '')}</p>
                            <p><strong>Resumen:</strong> ${this.formatSummary(email.summary)}</p>
                            <p><strong>Cuerpo:</strong> ${UtilsModule.escapeHtml(email.body || '')}</p>
                            <p><strong>Adjuntos:</strong> ${UtilsModule.escapeHtml(attachmentsContent)}</p>
                        `;
                    }
                    const modal = document.getElementById('email-modal');
                    if (modal) {
                        modal.style.display = 'flex';
                    }
                    const notRelevantBtn = document.getElementById('not-relevant');
                    if (notRelevantBtn) {
                        notRelevantBtn.dataset.id = email.message_id || email.index;
                    }
                } catch (err) {
                    console.error('Error fetching email:', err);
                    alert('Error al cargar los detalles del correo: ' + err.message);
                }
            });
        });
    }
};