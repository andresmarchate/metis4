/* Artifact ID: f6g7h8i9-0123-4567-f8g9-h01234567890 */
/* Version: f6g7h8i9-0123-4567-f8g9-h01234567890 */
const DeepConversationAnalysisModule = {
    init({ deepConversationAnalysisSessionId, deepConversationAnalysisEmails, setDeepConversationAnalysisSessionId, setDeepConversationAnalysisEmails }) {
        this.deepConversationAnalysisSessionId = deepConversationAnalysisSessionId;
        this.deepConversationAnalysisEmails = deepConversationAnalysisEmails;
        this.setDeepConversationAnalysisSessionId = setDeepConversationAnalysisSessionId;
        this.setDeepConversationAnalysisEmails = setDeepConversationAnalysisEmails;

        // DOM elements
        this.deepConversationAnalysisSection = document.getElementById('deep-conversation-analysis-section');
        this.conversationThemeCheckboxes = document.getElementById('conversation-theme-checkboxes');
        this.processDeepConversationAnalysisBtn = document.getElementById('process-deep-conversation-analysis');
        this.deepConversationAnalysisInput = document.getElementById('deep-conversation-analysis-input');
        this.deepConversationAnalysisPrompt = document.getElementById('deep-conversation-analysis-prompt');
        this.submitDeepConversationAnalysisBtn = document.getElementById('submit-deep-conversation-analysis');
        this.resetDeepConversationAnalysisContextBtn = document.getElementById('reset-deep-conversation-analysis-context');
        this.deepConversationAnalysisResponse = document.getElementById('deep-conversation-analysis-response');

        // Event listeners
        this.processDeepConversationAnalysisBtn.addEventListener('click', () => this.processDeepConversationAnalysis());
        this.submitDeepConversationAnalysisBtn.addEventListener('click', () => this.submitDeepConversationAnalysis());
        this.resetDeepConversationAnalysisContextBtn.addEventListener('click', () => this.resetDeepConversationAnalysisContext());
    },

    showTab() {
        this.deepConversationAnalysisSection.classList.add('active');
        document.querySelector('.tab-link[data-tab="deep-conversation-analysis"]').classList.add('active');
        this.populateConversationThemeCheckboxes();
    },

    populateConversationThemeCheckboxes() {
        console.log('Populating conversation theme checkboxes:', ConversationsModule.currentConversationThemes);
        this.conversationThemeCheckboxes.innerHTML = '';
        if (!Array.isArray(ConversationsModule.currentConversationThemes) || ConversationsModule.currentConversationThemes.length === 0) {
            this.conversationThemeCheckboxes.innerHTML = '<p>No hay temas de conversaciones disponibles para seleccionar.</p>';
            return;
        }

        ConversationsModule.currentConversationThemes.forEach(theme => {
            const checkboxWrapper = document.createElement('label');
            checkboxWrapper.className = 'theme-checkbox';
            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.value = theme.theme_id;
            checkbox.dataset.title = theme.title;
            const labelText = document.createTextNode(theme.title);
            checkboxWrapper.appendChild(checkbox);
            checkboxWrapper.appendChild(labelText);
            this.conversationThemeCheckboxes.appendChild(checkboxWrapper);
        });
    },

    async processDeepConversationAnalysis() {
        console.log('Process deep conversation analysis clicked');
        const selectedThemes = Array.from(this.conversationThemeCheckboxes.querySelectorAll('input[type="checkbox"]:checked'))
            .map(checkbox => ({
                theme_id: checkbox.value,
                title: checkbox.dataset.title
            }));
        console.log('Selected conversation themes:', selectedThemes);

        if (selectedThemes.length === 0) {
            alert('Por favor, selecciona al menos un tema de conversación para analizar.');
            return;
        }

        try {
            const response = await fetch('/api/deep_conversation_analysis_init', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ theme_ids: selectedThemes.map(theme => theme.theme_id) })
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            console.log('Deep conversation analysis initialization response:', data);
            if (data.error) {
                throw new Error(data.error);
            }

            this.setDeepConversationAnalysisSessionId(data.session_id);
            this.setDeepConversationAnalysisEmails(data.email_data || []);
            this.deepConversationAnalysisInput.style.display = 'block';
            this.deepConversationAnalysisResponse.innerHTML = `
                <p>Análisis inicializado para los temas de conversación seleccionados. Ingresa tu consulta.</p>
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
                            ${this.deepConversationAnalysisEmails.map(email => `
                                <tr>
                                    <td><a href="#" class="deep-conversation-email-link" data-index="${UtilsModule.escapeHtml(email.index)}">${UtilsModule.truncateIndex(email.index)}</a></td>
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
            this.attachDeepConversationEmailListeners();
        } catch (error) {
            console.error('Error initializing deep conversation analysis:', error.message);
            alert(`Error al inicializar análisis profundo de conversaciones: ${error.message}`);
        }
    },

    async submitDeepConversationAnalysis() {
        const prompt = this.deepConversationAnalysisPrompt.value.trim();
        console.log('Submitting deep conversation analysis prompt:', prompt);

        if (!prompt) {
            alert('Por favor, ingresa una consulta válida.');
            return;
        }

        if (!this.deepConversationAnalysisSessionId) {
            alert('No hay una sesión activa. Por favor, inicializa el análisis primero.');
            return;
        }

        try {
            const response = await fetch('/api/deep_conversation_analysis_prompt', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: this.deepConversationAnalysisSessionId, prompt })
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            console.log('Deep conversation analysis prompt response:', data);
            if (data.error) {
                throw new Error(data.error);
            }

            const indexRegex = /(?:con índice\s+)?\'([0-9a-f]{64})\'/gi;
            console.log('Reasoning text before processing:', data.reasoning);
            const linkedReasoning = data.reasoning.replace(indexRegex, (match, index) => {
                console.log('Found index in reasoning:', index);
                return `<a href="#" class="deep-conversation-email-link" data-index="${index}">${UtilsModule.truncateIndex(index)}</a>`;
            });
            console.log('Processed reasoning with links:', linkedReasoning);

            this.deepConversationAnalysisResponse.innerHTML = `
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
                                    <td><a href="#" class="deep-conversation-email-link" data-index="${UtilsModule.escapeHtml(ref.index)}">${UtilsModule.truncateIndex(ref.index)}</a></td>
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
            this.deepConversationAnalysisPrompt.value = '';
            this.attachDeepConversationEmailListeners();
        } catch (error) {
            console.error('Error processing deep conversation analysis prompt:', error.message);
            alert(`Error al procesar la consulta: ${error.message}`);
        }
    },

    async resetDeepConversationAnalysisContext() {
        console.log('Resetting deep conversation analysis context');
        if (!this.deepConversationAnalysisSessionId) {
            alert('No hay una sesión activa para resetear.');
            return;
        }

        try {
            const response = await fetch('/api/deep_conversation_analysis_reset', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: this.deepConversationAnalysisSessionId })
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            console.log('Deep conversation analysis reset response:', data);
            if (data.error) {
                throw new Error(data.error);
            }

            this.setDeepConversationAnalysisSessionId(null);
            this.setDeepConversationAnalysisEmails([]);
            this.deepConversationAnalysisInput.style.display = 'none';
            this.deepConversationAnalysisPrompt.value = '';
            this.deepConversationAnalysisResponse.innerHTML = '<p>Contexto reseteado. Selecciona nuevos temas para continuar.</p>';
            alert('Contexto reseteado correctamente.');
        } catch (error) {
            console.error('Error resetting deep conversation analysis context:', error.message);
            alert(`Error al resetear el contexto: ${error.message}`);
        }
    },

    attachDeepConversationEmailListeners() {
        document.querySelectorAll('.deep-conversation-email-link').forEach(link => {
            link.addEventListener('click', async (e) => {
                e.preventDefault();
                const identifier = e.target.dataset.index;
                console.log('Clicked deep conversation email link with identifier:', identifier);
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