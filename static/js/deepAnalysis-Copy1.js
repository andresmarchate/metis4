/* Artifact ID: d4e5f6g7-8901-2345-d6e7-f89012345678 */
/* Version: d4e5f6g7-8901-2345-d6e7-f89012345678 */
const DeepAnalysisModule = {
    init({ deepAnalysisSessionId, deepAnalysisEmails, setDeepAnalysisSessionId, setDeepAnalysisEmails }) {
        this.deepAnalysisSessionId = deepAnalysisSessionId;
        this.deepAnalysisEmails = deepAnalysisEmails;
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

        // Event listeners
        this.processDeepAnalysisBtn.addEventListener('click', () => this.processDeepAnalysis());
        this.submitDeepAnalysisBtn.addEventListener('click', () => this.submitDeepAnalysis());
        this.resetDeepAnalysisContextBtn.addEventListener('click', () => this.resetDeepAnalysisContext());
    },

    showTab() {
        this.deepAnalysisSection.classList.add('active');
        document.querySelector('.tab-link[data-tab="deep-analysis"]').classList.add('active');
        this.populateThemeCheckboxes();
    },

    populateThemeCheckboxes() {
        console.log('Populating theme checkboxes:', ThemesModule.currentThemes);
        this.themeCheckboxes.innerHTML = '';
        if (!Array.isArray(ThemesModule.currentThemes) || ThemesModule.currentThemes.length === 0) {
            this.themeCheckboxes.innerHTML = '<p>No hay temas disponibles para seleccionar.</p>';
            return;
        }

        ThemesModule.currentThemes.forEach(theme => {
            const checkboxWrapper = document.createElement('label');
            checkboxWrapper.className = 'theme-checkbox';
            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.value = theme.theme_id;
            checkbox.dataset.title = theme.title;
            const labelText = document.createTextNode(theme.title);
            checkboxWrapper.appendChild(checkbox);
            checkboxWrapper.appendChild(labelText);
            this.themeCheckboxes.appendChild(checkboxWrapper);
        });
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

            this.setDeepAnalysisSessionId(data.session_id);
            this.setDeepAnalysisEmails(data.email_data || []);
            this.deepAnalysisInput.style.display = 'block';
            this.deepAnalysisResponse.innerHTML = `
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
                            ${this.deepAnalysisEmails.map(email => `
                                <tr>
                                    <td><a href="#" class="deep-analysis-email-link" data-index="${UtilsModule.escapeHtml(email.index)}">${UtilsModule.truncateIndex(email.index)}</a></td>
                                    <td>${UtilsModule.escapeHtml(email.date ? new Date(email.date).toLocaleString() : 'N/A')}</td>
                                    <td>${UtilsModule.escapeHtml(email.from)}</td>
                                    <td>${UtilsModule.escapeHtml(email.to)}</td>
                                    <td>${UtilsModule.escapeHtml(email.subject)}</td>
                                    <td>${UtilsModule.escapeHtml(email.summary.slice(0, 100))}${email.summary.length > 100 ? '...' : ''}</td>
                                </tr>
                            `).join('') || '<tr><td colspan="6">No hay correos disponibles.</td></tr>'}
                        </tbody>
                    </table>
                </div>
            `;
            this.attachDeepAnalysisEmailListeners();
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
                                    <td>${UtilsModule.escapeHtml(ref.from)}</td>
                                    <td>${UtilsModule.escapeHtml(ref.to)}</td>
                                    <td>${UtilsModule.escapeHtml(ref.subject)}</td>
                                    <td>${UtilsModule.escapeHtml(ref.summary.slice(0, 100))}${ref.summary.length > 100 ? '...' : ''}</td>
                                </tr>
                            `).join('') || '<tr><td colspan="6">No hay referencias.</td></tr>'}
                        </tbody>
                    </table>
                </div>
            `;
            this.deepAnalysisPrompt.value = '';
            this.attachDeepAnalysisEmailListeners();
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

            this.setDeepAnalysisSessionId(null);
            this.setDeepAnalysisEmails([]);
            this.deepAnalysisInput.style.display = 'none';
            this.deepAnalysisPrompt.value = '';
            this.deepAnalysisResponse.innerHTML = '<p>Contexto reseteado. Selecciona nuevos temas para continuar.</p>';
            alert('Contexto reseteado correctamente.');
        } catch (error) {
            console.error('Error resetting deep analysis context:', error.message);
            alert(`Error al resetear el contexto: ${error.message}`);
        }
    },

    attachDeepAnalysisEmailListeners() {
        document.querySelectorAll('.deep-analysis-email-link').forEach(link => {
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
                    document.getElementById('email-details').innerHTML = `
                        <p><strong>Índice:</strong> ${UtilsModule.truncateIndex(email.index)}</p>
                        <p><strong>ID:</strong> ${UtilsModule.escapeHtml(email.message_id || 'N/A', true)}</p>
                        <p><strong>De:</strong> ${UtilsModule.escapeHtml(email.from || 'N/A')}</p>
                        <p><strong>Para:</strong> ${UtilsModule.escapeHtml(email.to || 'N/A')}</p>
                        <p><strong>Asunto:</strong> ${UtilsModule.escapeHtml(email.subject || '')}</p>
                        <p><strong>Fecha:</strong> ${UtilsModule.escapeHtml(email.date || '')}</p>
                        <p><strong>Resumen:</strong> ${UtilsModule.escapeHtml(email.summary || 'N/A')}</p>
                        <p><strong>Cuerpo:</strong> ${UtilsModule.escapeHtml(email.body || '')}</p>
                        <p><strong>Adjuntos:</strong> ${UtilsModule.escapeHtml(attachmentsContent)}</p>
                    `;
                    document.getElementById('email-modal').style.display = 'flex';
                    document.getElementById('not-relevant').dataset.id = email.message_id || email.index;
                } catch (err) {
                    console.error('Error fetching email:', err);
                    alert('Error al cargar los detalles del correo: ' + err.message);
                }
            });
        });
    }
};