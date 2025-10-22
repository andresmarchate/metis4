/* Artifact ID: e5f6g7h8-9012-3456-e7f8-g90123456789 */
/* Version: e5f6g7h8-9012-3456-e7f8-g90123456789 */
const ConversationsModule = {
    init({ currentConversationEmails, currentConversationThemes, setCurrentConversationEmails, setCurrentConversationThemes }) {
        this.currentConversationEmails = currentConversationEmails;
        this.currentConversationThemes = currentConversationThemes;
        this.setCurrentConversationEmails = setCurrentConversationEmails;
        this.setCurrentConversationThemes = setCurrentConversationThemes;

        // DOM elements
        this.conversationsSection = document.getElementById('conversations-section');
        this.conversationsForm = document.getElementById('conversations-form');
        this.email1Input = document.getElementById('email1');
        this.email2Input = document.getElementById('email2');
        this.startDateInput = document.getElementById('start-date');
        this.endDateInput = document.getElementById('end-date');
        this.errorMessageConversations = document.getElementById('error-message-conversations');
        this.conversationsCount = document.getElementById('conversations-count');
        this.conversationsTable = document.getElementById('conversations-table');
        this.conversationsBody = document.getElementById('conversations-body');
        this.analyzeConversationThemesBtn = document.getElementById('analyze-conversation-themes');
        this.conversationsThemesSection = document.getElementById('conversations-themes-section');
        this.conversationsThemesList = document.getElementById('conversations-themes-list');

        // Initialize autocomplete
        this.initializeAutocomplete(this.email1Input);
        this.initializeAutocomplete(this.email2Input);

        // Event listeners
        this.conversationsForm.addEventListener('submit', (e) => {
            e.preventDefault();
            this.performConversationSearch();
        });

        this.analyzeConversationThemesBtn.addEventListener('click', () => this.analyzeConversationThemes());
    },

    showTab() {
        this.conversationsSection.classList.add('active');
        document.querySelector('.tab-link[data-tab="conversations"]').classList.add('active');
    },

    showThemesTab() {
        this.conversationsThemesSection.classList.add('active');
        document.querySelector('.tab-link[data-tab="conversations-themes"]').classList.add('active');
    },

    initializeAutocomplete(inputElement) {
        $(inputElement).autocomplete({
            source: function(request, response) {
                console.log('Fetching autocomplete suggestions for:', request.term);
                fetch(`/api/email_addresses?prefix=${encodeURIComponent(request.term)}&limit=50`)
                    .then(res => {
                        if (!res.ok) {
                            throw new Error(`HTTP error! status: ${res.status}`);
                        }
                        return res.json();
                    })
                    .then(data => {
                        console.log('Autocomplete suggestions received:', data.addresses);
                        response(data.addresses || []);
                    })
                    .catch(err => {
                        console.error('Error fetching autocomplete suggestions:', err);
                        this.errorMessageConversations.textContent = 'Error al cargar sugerencias de correo.';
                        this.errorMessageConversations.style.display = 'block';
                        response([]);
                    });
            },
            minLength: 2,
            select: function(event, ui) {
                console.log('Selected autocomplete item:', ui.item.value);
                $(this).val(ui.item.value);
                return false;
            }
        });
    },

    async performConversationSearch() {
        const email1 = this.email1Input.value.trim();
        const email2 = this.email2Input.value.trim();
        const startDate = this.startDateInput.value;
        const endDate = this.endDateInput.value;

        console.log('Performing conversation search:', { email1, email2, startDate, endDate });

        if (!email1 || !email2 || !startDate || !endDate) {
            console.warn('Missing required conversation fields');
            this.errorMessageConversations.textContent = 'Por favor, completa todos los campos.';
            this.errorMessageConversations.style.display = 'block';
            return;
        }

        this.errorMessageConversations.style.display = 'none';
        this.conversationsBody.innerHTML = '';
        this.conversationsTable.style.display = 'none';
        this.conversationsCount.style.display = 'none';
        this.analyzeConversationThemesBtn.style.display = 'none';
        this.conversationsThemes.innerHTML = '';

        try {
            console.log('Sending POST request to /api/conversation_emails', { email1, email2, startDate, endDate });
            const response = await fetch('/api/conversation_emails', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    email1,
                    email2,
                    start_date: startDate,
                    end_date: endDate
                })
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            console.log('Conversation search response:', data);

            if (data.error) {
                throw new Error(data.error);
            }

            const results = data.results || [];
            const totalResults = data.totalResults || 0;

            if (results.length === 0) {
                console.log('No conversation emails found');
                this.errorMessageConversations.textContent = 'No se encontraron correos para los criterios seleccionados.';
                this.errorMessageConversations.style.display = 'block';
                return;
            }

            this.conversationsCount.textContent = `Se encontraron ${totalResults} correos`;
            this.conversationsCount.style.display = 'block';
            this.conversationsTable.style.display = 'table';
            this.analyzeConversationThemesBtn.style.display = 'block';

            this.setCurrentConversationEmails(results.map(result => ({
                message_id: result.message_id,
                index: result.index
            })).filter(email => email.index || email.message_id));

            results.forEach(result => {
                console.log('Rendering conversation result:', { index: result.index, message_id: result.message_id });
                const row = document.createElement('tr');
                row.innerHTML = `
                    <td><a href="#" class="index-link" data-index="${UtilsModule.escapeHtml(result.index)}">${UtilsModule.truncateIndex(result.index)}</a></td>
                    <td>${UtilsModule.escapeHtml(result.date ? new Date(result.date).toLocaleString() : 'N/A')}</td>
                    <td>${UtilsModule.escapeHtml(result.from || 'N/A')}</td>
                    <td>${UtilsModule.escapeHtml(result.to || 'N/A')}</td>
                    <td>${UtilsModule.escapeHtml(result.subject || '')}</td>
                    <td>${UtilsModule.escapeHtml((result.description || '').slice(0, 100))}${result.description && result.description.length > 100 ? '...' : ''}</td>
                `;
                this.conversationsBody.appendChild(row);
            });

            this.conversationsBody.querySelectorAll('.index-link').forEach(link => {
                link.addEventListener('click', async (e) => {
                    e.preventDefault();
                    const identifier = e.target.dataset.index;
                    console.log('Clicked conversation index link with identifier:', identifier);
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
        } catch (err) {
            console.error('Error during conversation search:', err);
            this.errorMessageConversations.textContent = 'Error al buscar correos: ' + err.message;
            this.errorMessageConversations.style.display = 'block';
        }
    },

    async analyzeConversationThemes() {
        console.log('Analyze conversation themes clicked');
        if (!this.currentConversationEmails || !Array.isArray(this.currentConversationEmails) || this.currentConversationEmails.length === 0) {
            console.warn('No valid conversation emails to analyze', { currentConversationEmails: this.currentConversationEmails });
            this.errorMessageConversations.textContent = 'No hay correos válidos para analizar temas.';
            this.errorMessageConversations.style.display = 'block';
            return;
        }

        const emailIds = this.currentConversationEmails.map(email => email.index || email.message_id).filter(id => id && id !== 'N/A');
        if (emailIds.length === 0) {
            console.warn('No valid email identifiers for theme analysis', { emailIds });
            this.errorMessageConversations.textContent = 'No hay identificadores de correos válidos para analizar.';
            this.errorMessageConversations.style.display = 'block';
            return;
        }

        try {
            console.log('Sending theme analysis request for conversation emails:', emailIds);
            const response = await fetch('/api/analyze_themes', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email_ids: emailIds })
            });

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({ error: `HTTP error: ${response.status}` }));
                throw new Error(errorData.error || `HTTP error: ${response.status}`);
            }

            const data = await response.json();
            console.log('Conversation theme analysis response:', data);
            if (data.error) {
                throw new Error(data.error);
            }

            ThemesModule.renderThemes(data.themes || [], this.conversationsThemesList);
            this.errorMessageConversations.style.display = 'none';
            this.showThemesTab();
        } catch (error) {
            console.error('Error analyzing conversation themes:', error.message);
            this.errorMessageConversations.textContent = `Error al analizar temas: ${error.message}`;
            this.errorMessageConversations.style.display = 'block';
            this.conversationsThemesList.innerHTML = '<p id="no-results-message">No se identificaron temas.</p>';
        }
    },

    populateConversationThemeCheckboxes() {
        DeepConversationAnalysisModule.populateConversationThemeCheckboxes();
    }
};